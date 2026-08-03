"""Read f1_prod (OLTP) and f1_dw (warehouse) for the OLTP -> OLAP pipeline.

Every function returns plain Python data and never writes. `conn` is always the
first argument and is never opened or closed here -- the caller owns the
connection lifecycle, which is what lets the same functions run from a script
now and from an Airflow task later.

Dimension queries extract participating entities only: a row is returned only if
it joins to at least one result. The OLTP reference tables are all-time (1950+),
so this drops entities whose whole career falls outside the 1994-2026 scope.
"""
from psycopg2.extras import RealDictCursor
import logging
from datetime import date

logger = logging.getLogger(__name__)


def extract(conn, sql, params=None):
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as curr:
            curr.execute(sql, params)
            rows = curr.fetchall()
            logger.info(f"Extracted {len(rows)} from the table")
        return rows
    except Exception as e:
        logger.error(str(e))
        raise


def extract_driver(conn):
    extract_driver_sql = """
    SELECT
        d.driver_ref,
        d.forename,
        d.surname,
        d.forename || ' ' || d.surname AS full_name,
        d.code,
        d.permanent_number,
        d.date_of_birth,
        d.nationality
    FROM drivers d
    WHERE EXISTS (
        SELECT 1 FROM results r WHERE r.driver_id = d.driver_id
    )
    ORDER BY d.driver_ref;
    """
    return extract(conn, extract_driver_sql)


def extract_constructor(conn):
    # No first_season: f1_prod starts at 1994, so MIN(season) would report 1994
    # for Ferrari (really 1950) and 13 other teams. last_season is safe -- the
    # right-hand edge of the data is real.
    extract_constructor_sql = """
    SELECT
        c.constructor_ref,
        c.name,
        c.nationality,
        (
            SELECT MAX(ra.season)
            FROM results r
            JOIN races ra ON ra.race_id = r.race_id
            WHERE r.constructor_id = c.constructor_id
        ) AS last_season
    FROM constructors c
    WHERE EXISTS (
        SELECT 1 FROM results r WHERE r.constructor_id = c.constructor_id
    )
    ORDER BY c.constructor_ref;
    """
    return extract(conn, extract_constructor_sql)


def extract_circuit(conn):
    # A circuit participates through its races, hence the two-level EXISTS.
    extract_circuit_sql = """
    SELECT
        ci.circuit_ref,
        ci.name,
        ci.locality,
        ci.country,
        ci.latitude,
        ci.longitude
    FROM circuits ci
    WHERE EXISTS (
        SELECT 1
        FROM races ra
        JOIN results r ON r.race_id = ra.race_id
        WHERE ra.circuit_id = ci.circuit_id
    )
    ORDER BY ci.circuit_ref;
    """
    return extract(conn, extract_circuit_sql)


def extract_status(conn):
    # The junk dimension: 109 status strings are unusable as a chart axis, five
    # groups are what the reliability trend needs. Verified against live data --
    # the groups reconcile to 5682 / 3805 / 1891 / 1249 / 379, summing to 13006.
    #
    # starts_with() rather than LIKE '+%' so the query carries no % character:
    # extract() hands every SQL string to psycopg2 with a params slot.
    extract_status_sql = """
    SELECT
        s.status_text,
        s.status_code,
        CASE
            WHEN s.status_text = 'Finished' THEN 'Finished'
            WHEN s.status_text = 'Lapped'
              OR starts_with(s.status_text, '+') THEN 'Lapped'
            WHEN s.status_text IN (
                'Collision', 'Spun off', 'Accident', 'Collision damage',
                'Puncture', 'Damage'
            ) THEN 'Accident DNF'
            WHEN s.status_text IN (
                'Retired', 'Disqualified', 'Withdrew', 'Did not start',
                'Injury', 'Not classified', 'Excluded'
            ) THEN 'Other'
            ELSE 'Mechanical DNF'
        END AS status_group,
        (
            s.status_text = 'Finished'
            OR s.status_text = 'Lapped'
            OR starts_with(s.status_text, '+')
        ) AS is_classified
    FROM statuses s
    WHERE EXISTS (
        SELECT 1 FROM results r WHERE r.status_id = s.status_id
    )
    ORDER BY s.status_text;
    """
    return extract(conn, extract_status_sql)


def extract_race(conn):
    # The JOIN to results holds back scheduled-but-unrun 2026 rounds.
    # race_laps is the race distance = MAX(laps_completed), i.e. the distance
    # ACTUALLY run, so a red-flagged race sits below its scheduled distance.
    # That is the right basis for the laps_completed <= race_laps quality check,
    # and the source exposes no scheduled distance.
    extract_race_sql = """
    SELECT
        ra.season,
        ra.round,
        ra.race_name,
        ra.race_date,
        ra.qualifying_date,
        MAX(r.laps_completed) AS race_laps,
        (ra.round = MAX(ra.round) OVER (PARTITION BY ra.season)) AS is_season_finale,
        CASE
            WHEN ra.season <= 2009 THEN '1994-2009'
            WHEN ra.season <= 2018 THEN '2010-2018'
            WHEN ra.season <= 2024 THEN '2019-2024'
            ELSE '2025+'
        END AS points_era,
        (ra.season >= 2004) AS has_fastest_lap_data,
        (ra.season >= 2006) AS has_quali_knockout
    FROM races ra
    JOIN results r ON r.race_id = ra.race_id
    GROUP BY
        ra.race_id, ra.season, ra.round, ra.race_name,
        ra.race_date, ra.qualifying_date
    ORDER BY ra.season, ra.round;
    """
    return extract(conn, extract_race_sql)


# The fact queries join out to the natural keys. The warehouse dimensions are
# keyed on driver_ref / constructor_ref / circuit_ref / status_text /
# (season, round), but OLTP transaction rows carry SERIAL ids -- so the natural
# keys have to travel with the row for transform.py to resolve them.
#
# The incremental variants use a 30-day lookback rather than a strict `>`: a
# result restated weeks after the race (a disqualification) would otherwise
# never be picked up. Re-reading a handful of races is free because the load
# upserts on source_result_id.

def extract_results_full(conn):
    extract_results_sql = """
    SELECT
        r.result_id AS source_result_id,
        ra.season,
        ra.round,
        ra.race_date,
        d.driver_ref,
        c.constructor_ref,
        ci.circuit_ref,
        s.status_text,
        r.grid_position,
        r.finish_position,
        r.position_text,
        r.position_order,
        r.points,
        r.laps_completed,
        r.race_time_ms,
        r.fastest_lap_rank,
        r.fastest_lap_time_ms,
        r.fastest_lap_speed_kph
    FROM results r
    JOIN races        ra ON ra.race_id       = r.race_id
    JOIN circuits     ci ON ci.circuit_id    = ra.circuit_id
    JOIN drivers      d  ON d.driver_id      = r.driver_id
    JOIN constructors c  ON c.constructor_id = r.constructor_id
    JOIN statuses     s  ON s.status_id      = r.status_id
    ORDER BY ra.race_date, r.result_id;
    """
    return extract(conn, extract_results_sql)


def extract_results_incremental(conn, watermark):
    extract_results_sql = """
    SELECT
        r.result_id AS source_result_id,
        ra.season,
        ra.round,
        ra.race_date,
        d.driver_ref,
        c.constructor_ref,
        ci.circuit_ref,
        s.status_text,
        r.grid_position,
        r.finish_position,
        r.position_text,
        r.position_order,
        r.points,
        r.laps_completed,
        r.race_time_ms,
        r.fastest_lap_rank,
        r.fastest_lap_time_ms,
        r.fastest_lap_speed_kph
    FROM results r
    JOIN races        ra ON ra.race_id       = r.race_id
    JOIN circuits     ci ON ci.circuit_id    = ra.circuit_id
    JOIN drivers      d  ON d.driver_id      = r.driver_id
    JOIN constructors c  ON c.constructor_id = r.constructor_id
    JOIN statuses     s  ON s.status_id      = r.status_id
    WHERE ra.race_date > %(watermark)s::DATE - INTERVAL '30 days'
    ORDER BY ra.race_date, r.result_id;
    """
    return extract(conn, extract_results_sql, {"watermark": watermark})


def extract_qualifying_full(conn):
    extract_qualifying_sql = """
    SELECT
        q.qualifying_id AS source_qualifying_id,
        ra.season,
        ra.round,
        ra.race_date,
        d.driver_ref,
        c.constructor_ref,
        ci.circuit_ref,
        q.quali_position,
        q.q1_ms,
        q.q2_ms,
        q.q3_ms
    FROM qualifying q
    JOIN races        ra ON ra.race_id       = q.race_id
    JOIN circuits     ci ON ci.circuit_id    = ra.circuit_id
    JOIN drivers      d  ON d.driver_id      = q.driver_id
    JOIN constructors c  ON c.constructor_id = q.constructor_id
    ORDER BY ra.race_date, q.qualifying_id;
    """
    return extract(conn, extract_qualifying_sql)


def extract_qualifying_incremental(conn, watermark):
    extract_qualifying_sql = """
    SELECT
        q.qualifying_id AS source_qualifying_id,
        ra.season,
        ra.round,
        ra.race_date,
        d.driver_ref,
        c.constructor_ref,
        ci.circuit_ref,
        q.quali_position,
        q.q1_ms,
        q.q2_ms,
        q.q3_ms
    FROM qualifying q
    JOIN races        ra ON ra.race_id       = q.race_id
    JOIN circuits     ci ON ci.circuit_id    = ra.circuit_id
    JOIN drivers      d  ON d.driver_id      = q.driver_id
    JOIN constructors c  ON c.constructor_id = q.constructor_id
    WHERE ra.race_date > %(watermark)s::DATE - INTERVAL '30 days'
    ORDER BY ra.race_date, q.qualifying_id;
    """
    return extract(conn, extract_qualifying_sql, {"watermark": watermark})


def extract_lookup_dim(conn):
    """Build {natural_key: surrogate_key} maps from the warehouse, so transform
    resolves foreign keys with dictionary lookups instead of a query per row."""
    logger.info("Loading lookup table into memmory")
    lookup = {}
    with conn.cursor() as curr:
        curr.execute("SELECT driver_ref, driver_key FROM dim_driver")
        lookup["driver"] = {r[0]: r[1] for r in curr.fetchall()}

        curr.execute("SELECT constructor_ref, constructor_key FROM dim_constructor")
        lookup["constructor"] = {r[0]: r[1] for r in curr.fetchall()}

        curr.execute("SELECT circuit_ref, circuit_key FROM dim_circuit")
        lookup["circuit"] = {r[0]: r[1] for r in curr.fetchall()}

        curr.execute("SELECT status_text, status_key FROM dim_status")
        lookup["status"] = {r[0]: r[1] for r in curr.fetchall()}

        # (season, round) is the composite natural key of a race.
        curr.execute("SELECT season, round, race_key FROM dim_race")
        lookup["race"] = {(r[0], r[1]): r[2] for r in curr.fetchall()}

        # date_key IS the key (YYYYMMDD), so this is a membership test, not a map.
        curr.execute("SELECT date_key FROM dim_date")
        lookup["date"] = {r[0] for r in curr.fetchall()}
    return lookup


def get_race_result_watermark(conn) -> date:
    """
    Return the most recent race_date already loaded in fact_race_result.
    Falls back to 1900-01-01 on an empty fact table so the first run
    behaves as a full load without special-casing.
    """
    with conn.cursor() as curr:
        curr.execute("""
            SELECT COALESCE(
                MAX(race_date),
                '1900-01-01'::DATE
            )
            FROM fact_race_result
        """)
        watermark = curr.fetchone()[0]
    logger.info(f"Watermark [fact_race_result]: {watermark}")
    return watermark


def get_qualifying_watermark(conn) -> date:
    """
    Return the most recent race_date already loaded in fact_qualifying.
    Falls back to 1900-01-01 on an empty fact table so the first run
    behaves as a full load without special-casing.
    """
    with conn.cursor() as curr:
        curr.execute("""
            SELECT COALESCE(
                MAX(race_date),
                '1900-01-01'::DATE
            )
            FROM fact_qualifying
        """)
        watermark = curr.fetchone()[0]
    logger.info(f"Watermark [fact_qualifying]: {watermark}")
    return watermark
