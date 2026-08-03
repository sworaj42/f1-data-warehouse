"""Quality gate. Runs on transformed rows BEFORE anything is written to f1_dw.

A check returns a verdict; it never repairs. A gate that drops a bad row makes
its own check unfalsifiable and quietly moves transform's job into the wrong
module -- so run_quality_checks raises and the load never starts.

FAIL halts the pipeline. WARN is logged and continues: the three WARN
conditions below are real, documented quirks of the Ergast/Jolpica source that
are stored faithfully, and failing on them would mean the pipeline could never
run at all.
"""
import logging
from collections import Counter

logger = logging.getLogger(__name__)

_RESULT_KEYS = ("date_key", "race_key", "driver_key",
                "constructor_key", "circuit_key", "status_key")
_QUALIFYING_KEYS = ("date_key", "race_key", "driver_key",
                    "constructor_key", "circuit_key")
_FLAGS = ("is_winner", "is_podium", "is_points_finish", "is_dnf",
          "is_pole_start", "is_fastest_lap", "is_pitlane_start")


class DataQualityError(Exception):
    """Raised when a FAIL check does not pass. Signals the pipeline to halt --
    nothing gets loaded.

    A dedicated type so a caller (or an Airflow task) can tell "the data was
    bad" apart from "the database was down".
    """
    pass


def _verdict(check, passed, detail):
    return {"check": check, "passed": passed, "detail": detail}


# --- FAIL checks -----------------------------------------------------------

def check_no_null_keys(rows, keys, label):
    """Every dimension foreign key is populated. All are NOT NULL in the DDL,
    so a None here would fail the insert -- catch it before the write."""
    bad = [r for r in rows if any(r[k] is None for k in keys)]
    return _verdict(f"no_null_keys[{label}]", len(bad) == 0,
                    f"{len(bad)} rows with a NULL dimension key")


def check_unique_finish_position(rows):
    """No two drivers share a finishing position within a race. Verified 0
    violations in the source, so this is a genuine FAIL condition."""
    seen = Counter(
        (r["race_key"], r["finish_position"])
        for r in rows if r["finish_position"] is not None
    )
    bad = [k for k, n in seen.items() if n > 1]
    return _verdict("unique_finish_position", len(bad) == 0,
                    f"{len(bad)} (race, finish_position) pairs used more than once")


def check_laps_within_race(rows, race_laps_by_key):
    """No driver completes more laps than the race distance. race_laps is
    MAX(laps_completed) for the race, so a violation means the dimension and
    the fact disagree about which race a row belongs to."""
    bad = [
        r for r in rows
        if race_laps_by_key.get(r["race_key"]) is not None
        and r["laps_completed"] > race_laps_by_key[r["race_key"]]
    ]
    return _verdict("laps_within_race", len(bad) == 0,
                    f"{len(bad)} rows with laps_completed above the race distance")


def check_positions_gained_rule(rows):
    """positions_gained is NULL exactly when the driver did not finish or
    started from the pit lane -- the one derivation whose two NULL conditions
    overlap, and the easiest to get wrong."""
    bad = [
        r for r in rows
        if (r["positions_gained"] is None)
        != (r["finish_position"] is None or r["grid_position"] == 0)
    ]
    return _verdict("positions_gained_rule", len(bad) == 0,
                    f"{len(bad)} rows where the NULL rule does not hold")


def check_flags_are_boolean(rows):
    """The is_* columns are NOT NULL DEFAULT FALSE. A None would be rejected by
    the insert; a non-boolean would be silently coerced."""
    bad = [r for r in rows if any(not isinstance(r[f], bool) for f in _FLAGS)]
    return _verdict("flags_are_boolean", len(bad) == 0,
                    f"{len(bad)} rows with a non-boolean flag")


def check_gap_to_pole_non_negative(rows):
    """The pole sitter's gap is zero by construction, so a negative value means
    the per-race minimum was taken over the wrong grouping. The DDL enforces
    this too, but failing here names the check instead of the constraint."""
    bad = [r for r in rows
           if r["gap_to_pole_ms"] is not None and r["gap_to_pole_ms"] < 0]
    return _verdict("gap_to_pole_non_negative", len(bad) == 0,
                    f"{len(bad)} rows with a negative gap_to_pole_ms")


def check_every_race_has_facts(rows, race_keys):
    """Every race in dim_race produced at least one fact row. Full reloads
    only -- on an incremental run the fact is deliberately a subset."""
    missing = set(race_keys) - {r["race_key"] for r in rows}
    return _verdict("every_race_has_facts", len(missing) == 0,
                    f"{len(missing)} races in dim_race with no fact row")


def check_rows_present(rows, label):
    """Full reloads only. An incremental run with nothing to do is normal --
    races are two weeks apart -- so this must never gate an empty batch."""
    return _verdict(f"rows_present[{label}]", len(rows) > 0,
                    f"{len(rows)} rows")


# --- WARN checks -----------------------------------------------------------
# Real source anomalies. Logged, never fatal.

def warn_races_without_qualifying(result_rows, qualifying_rows):
    """Pre-2003 seasons where Ergast qualifying coverage is patchy or absent.
    Expected: 83 races."""
    missing = {r["race_key"] for r in result_rows} - {q["race_key"] for q in qualifying_rows}
    return _verdict("races_without_qualifying", len(missing) == 0,
                    f"{len(missing)} races with results but no qualifying")


def warn_duplicate_grid_positions(rows):
    """Grid-penalty renumbering, e.g. the 2015 Italian GP. Position 0 is the
    pit lane and is legitimately shared. Expected: 4."""
    seen = Counter((r["race_key"], r["grid_position"])
                   for r in rows if r["grid_position"] != 0)
    dupes = [k for k, n in seen.items() if n > 1]
    return _verdict("duplicate_grid_positions", len(dupes) == 0,
                    f"{len(dupes)} (race, grid_position) pairs used more than once")


def warn_duplicate_quali_positions(rows):
    """Deleted or disallowed times that were never renumbered, e.g. 2024
    Azerbaijan. Expected: 5."""
    seen = Counter((r["race_key"], r["quali_position"]) for r in rows)
    dupes = [k for k, n in seen.items() if n > 1]
    return _verdict("duplicate_quali_positions", len(dupes) == 0,
                    f"{len(dupes)} (race, quali_position) pairs used more than once")


def run_quality_checks(result_rows, qualifying_rows, race_laps_by_key,
                       full_reload=False):
    """Run every check, then raise on the first failure.

    Evaluating all of them first means the summary is complete even though only
    one failure is reported -- raising inside the loop would hide the rest.

    Returns a summary dict when the FAIL checks pass.
    Raises DataQualityError otherwise.
    """
    checks = [
        check_no_null_keys(result_rows, _RESULT_KEYS, "results"),
        check_no_null_keys(qualifying_rows, _QUALIFYING_KEYS, "qualifying"),
        check_unique_finish_position(result_rows),
        check_laps_within_race(result_rows, race_laps_by_key),
        check_positions_gained_rule(result_rows),
        check_flags_are_boolean(result_rows),
        check_gap_to_pole_non_negative(qualifying_rows),
    ]
    if full_reload:
        checks += [
            check_rows_present(result_rows, "results"),
            check_rows_present(qualifying_rows, "qualifying"),
            check_every_race_has_facts(result_rows, race_laps_by_key.keys()),
        ]

    warnings = [
        warn_races_without_qualifying(result_rows, qualifying_rows),
        warn_duplicate_grid_positions(result_rows),
        warn_duplicate_quali_positions(qualifying_rows),
    ]
    for w in warnings:
        if not w["passed"]:
            logger.warning(f"  WARN {w['check']}: {w['detail']}")

    failed = [c for c in checks if not c["passed"]]
    if failed:
        first = failed[0]
        raise DataQualityError(
            f"Quality check failed: {first['check']} -- {first['detail']}"
        )

    logger.info(
        f"Quality gate passed: {len(result_rows):,} result rows, "
        f"{len(qualifying_rows):,} qualifying rows, {len(checks)} checks"
    )
    for c in checks:
        logger.debug(f"  {c['check']}: {c['detail']}")

    return {"passed": True, "checks": checks, "warnings": warnings}
