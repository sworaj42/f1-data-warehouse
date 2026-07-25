"""OLTP sanity checks against f1_prod. Prints row counts + integrity checks.

Exits non-zero if any FAIL check has violations -- a preview of the warehouse
quality gate (a bad load should be loud, not silent).

    python scripts/check_oltp.py
"""
import logging
import pathlib
import sys
from collections import namedtuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import db                             # noqa: E402
from etl.logging_config import setup_logging   # noqa: E402

log = logging.getLogger(__name__)

_TABLES = ["circuits", "drivers", "constructors", "statuses", "races", "results", "qualifying"]

# Each check's SQL returns the offending rows; zero rows = PASS.
Check = namedtuple("Check", "name severity sql")

CHECKS = [
    Check("dup_finish_position_per_race", "FAIL", """
        SELECT race_id, finish_position, count(*) FROM results
        WHERE finish_position IS NOT NULL
        GROUP BY race_id, finish_position HAVING count(*) > 1"""),
    # WARN, not FAIL: the source genuinely contains duplicate grid positions (2015 grid
    # penalties, e.g. Sainz/Nasr both on grid 17 at Monza). We store the API value faithfully.
    Check("dup_grid_position_per_race", "WARN", """
        SELECT race_id, grid_position, count(*) FROM results
        WHERE grid_position <> 0
        GROUP BY race_id, grid_position HAVING count(*) > 1"""),
    Check("dup_position_order_per_race", "FAIL", """
        SELECT race_id, position_order, count(*) FROM results
        GROUP BY race_id, position_order HAVING count(*) > 1"""),
    # WARN, not FAIL: the source duplicates quali positions when a driver's times are
    # deleted/DSQ'd and positions aren't renumbered (e.g. 2024 Azerbaijan, Gasly/Ricciardo P15).
    Check("dup_quali_position_per_race", "WARN", """
        SELECT race_id, quali_position, count(*) FROM qualifying
        GROUP BY race_id, quali_position HAVING count(*) > 1"""),
    Check("races_without_results", "FAIL", """
        SELECT r.race_id, r.season, r.round FROM races r
        WHERE NOT EXISTS (SELECT 1 FROM results re WHERE re.race_id = r.race_id)"""),
    Check("negative_points", "FAIL", "SELECT result_id FROM results WHERE points < 0"),
    Check("classified_missing_finish_pos", "FAIL", """
        SELECT result_id FROM results
        WHERE position_text ~ '^[0-9]+$' AND finish_position IS NULL"""),
    Check("q3_without_q2_time", "WARN", """
        SELECT qualifying_id FROM qualifying WHERE q3_ms IS NOT NULL AND q2_ms IS NULL"""),
    Check("races_without_qualifying", "WARN", """
        SELECT r.race_id, r.season, r.round FROM races r
        WHERE NOT EXISTS (SELECT 1 FROM qualifying q WHERE q.race_id = r.race_id)"""),
]


def print_counts(conn):
    log.info("=== row counts ===")
    with conn.cursor() as cur:
        for t in _TABLES:
            cur.execute(f"SELECT count(*) FROM {t}")
            log.info("  %-13s %d", t, cur.fetchone()[0])


def run_checks(conn) -> int:
    log.info("=== integrity checks ===")
    failures = 0
    with conn.cursor() as cur:
        for chk in CHECKS:
            cur.execute(chk.sql)
            rows = cur.fetchall()
            n = len(rows)
            if n == 0:
                log.info("  PASS  %s", chk.name)
                continue
            status = chk.severity
            if status == "FAIL":
                failures += 1
            log.warning("  %-4s  %s -- %d violation(s); sample: %s",
                        status, chk.name, n, rows[0])
    return failures


def main():
    setup_logging("check_oltp")
    conn = db.get_conn()
    try:
        print_counts(conn)
        failures = run_checks(conn)
    finally:
        conn.close()

    if failures:
        log.error("QUALITY GATE FAILED: %d FAIL check(s) had violations", failures)
        sys.exit(1)
    log.info("all FAIL checks passed")


if __name__ == "__main__":
    main()
