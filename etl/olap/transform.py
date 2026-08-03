"""Turn f1_prod rows into fact_race_result / fact_qualifying rows.

Two jobs only: resolve surrogate keys from the warehouse lookups, and compute the
derived measures and flags.

Dimensions do not pass through here. extract.py already derives every dimension
attribute in SQL, so dimension rows go straight from extract to load.
"""
import logging

logger = logging.getLogger(__name__)


def _date_key(race_date):
    """DATE -> YYYYMMDD integer, the dim_date primary key."""
    return int(race_date.strftime("%Y%m%d"))


def _quali_position_map(quali_rows):
    """{(season, round, driver_ref): quali_position}

    Denormalises quali_position onto the race fact so "grid penalties applied"
    (quali_position - grid_position) is a single-table read.
    """
    return {
        (row["season"], row["round"], row["driver_ref"]): row["quali_position"]
        for row in quali_rows
    }


def _best_quali_ms(row):
    """COALESCE(q3_ms, q2_ms, q1_ms) -- the last segment the driver reached.

    Deliberately not the fastest of the three: a Q2 time is sometimes quicker
    than the same driver's Q3 time. Returns None when no time was set at all.
    """
    for segment in ("q3_ms", "q2_ms", "q1_ms"):
        if row[segment] is not None:
            return row[segment]
    return None


def _pole_ms_by_race(quali_rows):
    """{(season, round): MIN(best_quali_ms)}, for gap_to_pole_ms.

    Built from timed rows only, so a race where nobody set a time is simply
    absent -- callers .get() it and fall back to None. One race in the data is
    exactly that, and min() over an empty sequence would raise ValueError.
    """
    pole = {}
    for row in quali_rows:
        best = _best_quali_ms(row)
        if best is None:
            continue
        race = (row["season"], row["round"])
        if race not in pole or best < pole[race]:
            pole[race] = best
    return pole


def transform_results(result_rows, quali_rows, lookups):
    """f1_prod result rows -> fact_race_result rows.

    quali_rows must be the FULL qualifying set even on an incremental run. The
    two facts have independent watermarks, so a result row could otherwise be
    re-processed while its qualifying row sits outside the window, and the
    upsert would overwrite a correct quali_position with NULL.
    """
    quali_positions = _quali_position_map(quali_rows)
    fact_rows = []
    skipped = 0

    for row in result_rows:
        source_id = row["source_result_id"]

        date_key = _date_key(row["race_date"])
        if date_key not in lookups["date"]:
            logger.warning(f"result {source_id}: date_key {date_key} not in dim_date -- skipped")
            skipped += 1
            continue

        race_key = lookups["race"].get((row["season"], row["round"]))
        driver_key = lookups["driver"].get(row["driver_ref"])
        constructor_key = lookups["constructor"].get(row["constructor_ref"])
        circuit_key = lookups["circuit"].get(row["circuit_ref"])
        status_key = lookups["status"].get(row["status_text"])
        if None in (race_key, driver_key, constructor_key, circuit_key, status_key):
            logger.warning(
                f"result {source_id}: missing fk -- skipped "
                f"(race={race_key} driver={driver_key} constructor={constructor_key} "
                f"circuit={circuit_key} status={status_key})"
            )
            skipped += 1
            continue

        grid = row["grid_position"]
        finish = row["finish_position"]

        # NULL twice over, and the two conditions overlap (28 rows are both).
        # A pit-lane start is recorded as grid 0, so a driver starting from the
        # pit lane and finishing fifth would compute 0 - 5 = -5 -- a five-place
        # loss for what was actually a strong drive. AVG() ignores NULL, so the
        # KPI stays correct with no filter in the dashboard query.
        positions_gained = None
        if finish is not None and grid != 0:
            positions_gained = grid - finish

        fact_rows.append({
            "source_result_id":      source_id,
            "date_key":              date_key,
            "race_key":              race_key,
            "driver_key":            driver_key,
            "constructor_key":       constructor_key,
            "circuit_key":           circuit_key,
            "status_key":            status_key,
            "race_date":             row["race_date"],
            "points":                row["points"],
            "laps_completed":        row["laps_completed"],
            "grid_position":         grid,
            "finish_position":       finish,
            "positions_gained":      positions_gained,
            "race_time_ms":          row["race_time_ms"],
            "fastest_lap_time_ms":   row["fastest_lap_time_ms"],
            "fastest_lap_speed_kph": row["fastest_lap_speed_kph"],
            "quali_position": quali_positions.get(
                (row["season"], row["round"], row["driver_ref"])
            ),
            # The flags are NOT NULL DEFAULT FALSE in the DDL, so every one of
            # these has to be a real boolean. is_podium needs the None guard --
            # None <= 3 raises TypeError -- while is_winner does not, because
            # None == 1 is legally False.
            "is_winner":             finish == 1,
            "is_podium":             finish is not None and finish <= 3,
            "is_points_finish":      row["points"] > 0,
            "is_dnf":                finish is None,
            "is_pole_start":         grid == 1,
            "is_fastest_lap":        row["fastest_lap_rank"] == 1,
            "is_pitlane_start":      grid == 0,
        })

    logger.info(f"Transformed {len(fact_rows)} race result rows, skipped {skipped}")
    return fact_rows


def transform_qualifying(quali_rows, lookups):
    """f1_prod qualifying rows -> fact_qualifying rows.

    Five dimension keys, not six: qualifying has no finishing status.
    """
    pole_ms = _pole_ms_by_race(quali_rows)
    fact_rows = []
    skipped = 0

    for row in quali_rows:
        source_id = row["source_qualifying_id"]

        date_key = _date_key(row["race_date"])
        if date_key not in lookups["date"]:
            logger.warning(f"qualifying {source_id}: date_key {date_key} not in dim_date -- skipped")
            skipped += 1
            continue

        race_key = lookups["race"].get((row["season"], row["round"]))
        driver_key = lookups["driver"].get(row["driver_ref"])
        constructor_key = lookups["constructor"].get(row["constructor_ref"])
        circuit_key = lookups["circuit"].get(row["circuit_ref"])
        if None in (race_key, driver_key, constructor_key, circuit_key):
            logger.warning(
                f"qualifying {source_id}: missing fk -- skipped "
                f"(race={race_key} driver={driver_key} "
                f"constructor={constructor_key} circuit={circuit_key})"
            )
            skipped += 1
            continue

        best = _best_quali_ms(row)

        # Both sides can be absent: `best` is None for the 161 rows that set no
        # time, and pole_ms has no entry for the one race where nobody did.
        gap_to_pole_ms = None
        race_pole = pole_ms.get((row["season"], row["round"]))
        if best is not None and race_pole is not None:
            gap_to_pole_ms = best - race_pole

        fact_rows.append({
            "source_qualifying_id": source_id,
            "date_key":             date_key,
            "race_key":             race_key,
            "driver_key":           driver_key,
            "constructor_key":      constructor_key,
            "circuit_key":          circuit_key,
            "race_date":            row["race_date"],
            "quali_position":       row["quali_position"],
            "q1_ms":                row["q1_ms"],
            "q2_ms":                row["q2_ms"],
            "q3_ms":                row["q3_ms"],
            "best_quali_ms":        best,
            "gap_to_pole_ms":       gap_to_pole_ms,
            "is_pole":              row["quali_position"] == 1,
            "reached_q2":           row["q2_ms"] is not None,
            "reached_q3":           row["q3_ms"] is not None,
        })

    logger.info(f"Transformed {len(fact_rows)} qualifying rows, skipped {skipped}")
    return fact_rows
