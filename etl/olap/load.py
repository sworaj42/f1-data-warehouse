"""Load dimension and fact rows into f1_dw with idempotent upserts.

Every conflict target is a natural or source key, and every conflict does
DO UPDATE rather than DO NOTHING -- so a second run updates in place and lands
on identical row counts, and a result the FIA restates weeks later actually
corrects the warehouse row instead of being ignored.

This module also owns the two things the migrations deliberately do not: the -1
unknown members and the dim_date populate. Migrations run once and are then
skipped by the ledger, so anything they INSERT is unrecoverable after a
TRUNCATE -- and truncate-and-reload is the reset path. Every row therefore
comes from here.
"""
import logging

from psycopg2.extras import execute_values

from etl import db

logger = logging.getLogger(__name__)


def _upsert(conn, name, sql, cols, rows):
    """execute_values in one round-trip per batch, inside one transaction."""
    if not rows:
        logger.info(f"No rows to load -- skipping {name}")
        return 0
    values = [tuple(r.get(c) for c in cols) for r in rows]
    with db.transaction(conn), conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)
    logger.info(f"{len(values)} upserted to {name}")
    return len(values)


# --- seeds -----------------------------------------------------------------

_UNKNOWN_MEMBERS_SQL = """
INSERT INTO dim_date (date_key, full_date, year, quarter, month, month_name,
                      week_of_year, day_of_week, day_name, is_weekend)
VALUES (-1, DATE '1900-01-01', 1900, 1, 1, 'Unknown', 1, 0, 'Unknown', FALSE)
ON CONFLICT (date_key) DO NOTHING;

INSERT INTO dim_driver (driver_key, driver_ref, forename, surname, full_name)
VALUES (-1, 'unknown', 'Unknown', 'Unknown', 'Unknown')
ON CONFLICT (driver_key) DO NOTHING;

INSERT INTO dim_constructor (constructor_key, constructor_ref, name)
VALUES (-1, 'unknown', 'Unknown')
ON CONFLICT (constructor_key) DO NOTHING;

INSERT INTO dim_circuit (circuit_key, circuit_ref, name)
VALUES (-1, 'unknown', 'Unknown')
ON CONFLICT (circuit_key) DO NOTHING;

INSERT INTO dim_race (race_key, season, round, race_name, race_date, points_era)
VALUES (-1, -1, -1, 'Unknown', DATE '1900-01-01', 'Unknown')
ON CONFLICT (race_key) DO NOTHING;

INSERT INTO dim_status (status_key, status_text, status_group)
VALUES (-1, 'Unknown', 'Unknown')
ON CONFLICT (status_key) DO NOTHING;
"""


def seed_unknown_members(conn):
    """The -1 row in every dimension, so a fact never needs a NULL foreign key.

    Explicit negative keys do not consume the SERIAL sequence. Row counts that
    describe a dimension must exclude them.
    """
    with db.transaction(conn), conn.cursor() as cur:
        cur.execute(_UNKNOWN_MEMBERS_SQL)
    logger.info("Seeded 6 unknown members")


# FM suppresses to_char's blank padding. Without it 'Sunday' is stored as
# 'Sunday   ' and every equality filter on day_name silently matches nothing.
_DIM_DATE_SQL = """
INSERT INTO dim_date (date_key, full_date, year, quarter, month, month_name,
                      week_of_year, day_of_week, day_name, is_weekend)
SELECT to_char(d, 'YYYYMMDD')::INTEGER,
       d::DATE,
       EXTRACT(YEAR    FROM d)::SMALLINT,
       EXTRACT(QUARTER FROM d)::SMALLINT,
       EXTRACT(MONTH   FROM d)::SMALLINT,
       to_char(d, 'FMMonth'),
       EXTRACT(WEEK    FROM d)::SMALLINT,
       EXTRACT(DOW     FROM d)::SMALLINT,
       to_char(d, 'FMDay'),
       EXTRACT(DOW FROM d) IN (0, 6)
FROM generate_series(
    make_date(%(start)s, 1, 1),
    make_date(%(end)s, 12, 31),
    INTERVAL '1 day'
) AS d
ON CONFLICT (date_key) DO NOTHING
"""


def populate_dim_date(conn, start_year, end_year):
    """Generate dim_date from the season scope. The only dimension with no
    source table -- every column is computed from the date itself."""
    with db.transaction(conn), conn.cursor() as cur:
        cur.execute(_DIM_DATE_SQL, {"start": start_year, "end": end_year})
        n = cur.rowcount
    logger.info(f"dim_date: {n} rows inserted ({start_year}-01-01 to {end_year}-12-31)")
    return n


# --- dimensions ------------------------------------------------------------

_DRIVER_COLS = ["driver_ref", "forename", "surname", "full_name", "code",
                "permanent_number", "date_of_birth", "nationality"]
_DRIVER_SQL = """
INSERT INTO dim_driver (driver_ref, forename, surname, full_name, code,
                        permanent_number, date_of_birth, nationality)
VALUES %s
ON CONFLICT (driver_ref) DO UPDATE SET
    forename = EXCLUDED.forename, surname = EXCLUDED.surname,
    full_name = EXCLUDED.full_name, code = EXCLUDED.code,
    permanent_number = EXCLUDED.permanent_number,
    date_of_birth = EXCLUDED.date_of_birth, nationality = EXCLUDED.nationality
"""


def load_dim_driver(conn, rows):
    return _upsert(conn, "dim_driver", _DRIVER_SQL, _DRIVER_COLS, rows)


_CONSTRUCTOR_COLS = ["constructor_ref", "name", "nationality", "last_season"]
_CONSTRUCTOR_SQL = """
INSERT INTO dim_constructor (constructor_ref, name, nationality, last_season)
VALUES %s
ON CONFLICT (constructor_ref) DO UPDATE SET
    name = EXCLUDED.name, nationality = EXCLUDED.nationality,
    last_season = EXCLUDED.last_season
"""


def load_dim_constructor(conn, rows):
    return _upsert(conn, "dim_constructor", _CONSTRUCTOR_SQL, _CONSTRUCTOR_COLS, rows)


_CIRCUIT_COLS = ["circuit_ref", "name", "locality", "country", "latitude", "longitude"]
_CIRCUIT_SQL = """
INSERT INTO dim_circuit (circuit_ref, name, locality, country, latitude, longitude)
VALUES %s
ON CONFLICT (circuit_ref) DO UPDATE SET
    name = EXCLUDED.name, locality = EXCLUDED.locality,
    country = EXCLUDED.country, latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude
"""


def load_dim_circuit(conn, rows):
    return _upsert(conn, "dim_circuit", _CIRCUIT_SQL, _CIRCUIT_COLS, rows)


_STATUS_COLS = ["status_text", "status_code", "status_group", "is_classified"]
_STATUS_SQL = """
INSERT INTO dim_status (status_text, status_code, status_group, is_classified)
VALUES %s
ON CONFLICT (status_text) DO UPDATE SET
    status_code = EXCLUDED.status_code, status_group = EXCLUDED.status_group,
    is_classified = EXCLUDED.is_classified
"""


def load_dim_status(conn, rows):
    return _upsert(conn, "dim_status", _STATUS_SQL, _STATUS_COLS, rows)


_RACE_COLS = ["season", "round", "race_name", "race_date", "qualifying_date",
              "race_laps", "is_season_finale", "points_era",
              "has_fastest_lap_data", "has_quali_knockout"]
_RACE_SQL = """
INSERT INTO dim_race (season, round, race_name, race_date, qualifying_date,
                      race_laps, is_season_finale, points_era,
                      has_fastest_lap_data, has_quali_knockout)
VALUES %s
ON CONFLICT (season, round) DO UPDATE SET
    race_name = EXCLUDED.race_name, race_date = EXCLUDED.race_date,
    qualifying_date = EXCLUDED.qualifying_date, race_laps = EXCLUDED.race_laps,
    is_season_finale = EXCLUDED.is_season_finale,
    points_era = EXCLUDED.points_era,
    has_fastest_lap_data = EXCLUDED.has_fastest_lap_data,
    has_quali_knockout = EXCLUDED.has_quali_knockout
"""


def load_dim_race(conn, rows):
    return _upsert(conn, "dim_race", _RACE_SQL, _RACE_COLS, rows)


# --- facts -----------------------------------------------------------------
# The conflict target is the source id, not (race_key, driver_key): surrogate
# keys are reassigned if a dimension is ever rebuilt, while the source id is
# stable. It is also the lineage trail back to f1_prod.

_FACT_RESULT_COLS = [
    "date_key", "race_key", "driver_key", "constructor_key", "circuit_key",
    "status_key", "source_result_id", "race_date", "points", "laps_completed",
    "grid_position", "finish_position", "positions_gained", "race_time_ms",
    "fastest_lap_time_ms", "fastest_lap_speed_kph", "quali_position",
    "is_winner", "is_podium", "is_points_finish", "is_dnf", "is_pole_start",
    "is_fastest_lap", "is_pitlane_start",
]
_FACT_RESULT_SQL = """
INSERT INTO fact_race_result (
    date_key, race_key, driver_key, constructor_key, circuit_key, status_key,
    source_result_id, race_date, points, laps_completed, grid_position,
    finish_position, positions_gained, race_time_ms, fastest_lap_time_ms,
    fastest_lap_speed_kph, quali_position, is_winner, is_podium,
    is_points_finish, is_dnf, is_pole_start, is_fastest_lap, is_pitlane_start
)
VALUES %s
ON CONFLICT (source_result_id) DO UPDATE SET
    date_key = EXCLUDED.date_key, race_key = EXCLUDED.race_key,
    driver_key = EXCLUDED.driver_key,
    constructor_key = EXCLUDED.constructor_key,
    circuit_key = EXCLUDED.circuit_key, status_key = EXCLUDED.status_key,
    race_date = EXCLUDED.race_date, points = EXCLUDED.points,
    laps_completed = EXCLUDED.laps_completed,
    grid_position = EXCLUDED.grid_position,
    finish_position = EXCLUDED.finish_position,
    positions_gained = EXCLUDED.positions_gained,
    race_time_ms = EXCLUDED.race_time_ms,
    fastest_lap_time_ms = EXCLUDED.fastest_lap_time_ms,
    fastest_lap_speed_kph = EXCLUDED.fastest_lap_speed_kph,
    quali_position = EXCLUDED.quali_position,
    is_winner = EXCLUDED.is_winner, is_podium = EXCLUDED.is_podium,
    is_points_finish = EXCLUDED.is_points_finish, is_dnf = EXCLUDED.is_dnf,
    is_pole_start = EXCLUDED.is_pole_start,
    is_fastest_lap = EXCLUDED.is_fastest_lap,
    is_pitlane_start = EXCLUDED.is_pitlane_start
"""


def load_fact_race_result(conn, rows):
    return _upsert(conn, "fact_race_result", _FACT_RESULT_SQL, _FACT_RESULT_COLS, rows)


_FACT_QUALI_COLS = [
    "date_key", "race_key", "driver_key", "constructor_key", "circuit_key",
    "source_qualifying_id", "race_date", "quali_position", "q1_ms", "q2_ms",
    "q3_ms", "best_quali_ms", "gap_to_pole_ms", "is_pole", "reached_q2",
    "reached_q3",
]
_FACT_QUALI_SQL = """
INSERT INTO fact_qualifying (
    date_key, race_key, driver_key, constructor_key, circuit_key,
    source_qualifying_id, race_date, quali_position, q1_ms, q2_ms, q3_ms,
    best_quali_ms, gap_to_pole_ms, is_pole, reached_q2, reached_q3
)
VALUES %s
ON CONFLICT (source_qualifying_id) DO UPDATE SET
    date_key = EXCLUDED.date_key, race_key = EXCLUDED.race_key,
    driver_key = EXCLUDED.driver_key,
    constructor_key = EXCLUDED.constructor_key,
    circuit_key = EXCLUDED.circuit_key, race_date = EXCLUDED.race_date,
    quali_position = EXCLUDED.quali_position, q1_ms = EXCLUDED.q1_ms,
    q2_ms = EXCLUDED.q2_ms, q3_ms = EXCLUDED.q3_ms,
    best_quali_ms = EXCLUDED.best_quali_ms,
    gap_to_pole_ms = EXCLUDED.gap_to_pole_ms, is_pole = EXCLUDED.is_pole,
    reached_q2 = EXCLUDED.reached_q2, reached_q3 = EXCLUDED.reached_q3
"""


def load_fact_qualifying(conn, rows):
    return _upsert(conn, "fact_qualifying", _FACT_QUALI_SQL, _FACT_QUALI_COLS, rows)
