"""Capture EXPLAIN (ANALYZE, BUFFERS) for the analytics layer, before and after indexing.

    python scripts/explain_views.py --label before
    python scripts/explain_views.py --label after

The before/after comparison is the deliverable; a CREATE INDEX statement on its
own proves nothing, and the "before" measurement cannot be recovered once the
index exists.

TWO workloads are measured, because they answer different questions:

  VIEWS   -- SELECT * FROM v_<name>, i.e. what the dashboard actually issues.
             These read every row by construction, so an index CANNOT help them
             and the expected result is "no change". Measuring them anyway is
             the point: it is the evidence for why the dashboard caches instead
             of relying on indexes.

  PROBES  -- selective queries against the facts, where an index can eliminate
             rows. This is where an index earns its keep, and where the
             before/after difference is real.

Each query is timed over several runs and reported as a median with its spread,
because a single reading on a warm-vs-cold shared buffer cache measures I/O luck
rather than the plan.
"""
import argparse
import logging
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                     # noqa: E402
from etl.logging_config import setup_logging   # noqa: E402

log = logging.getLogger(__name__)

# Ordered as they appear in sql/analytics/001_views.sql.
VIEWS = [
    "v_season_kpis",
    "v_constructor_season",
    "v_championship_progression",
    "v_driver_rolling_form",
    "v_reliability_trend",
    "v_quali_vs_race",
]

# Selective reads, each naming the index it is meant to exercise.
PROBES = {
    "watermark MAX(race_date)":
        "SELECT MAX(race_date) FROM fact_race_result",
    "one driver's whole career":
        "SELECT count(*), avg(finish_position) FROM fact_race_result WHERE driver_key = %(driver)s",
    "one constructor's whole history":
        "SELECT count(*), sum(points) FROM fact_race_result WHERE constructor_key = %(constructor)s",
    "one driver in one race (composite)":
        "SELECT * FROM fact_race_result WHERE driver_key = %(driver)s AND race_key = %(race)s",
    "incremental 30-day lookback":
        "SELECT count(*) FROM fact_race_result WHERE race_date >= %(cutoff)s",
}

RUNS = 7
# Discard the first run of each query: it pays for a cold shared-buffer cache and
# would otherwise dominate the median on the smaller queries.
WARMUP = 2


def _explain(conn, sql, params=None):
    """Return (plan_text, execution_ms) for one EXPLAIN ANALYZE run."""
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", params)
        plan = "\n".join(row[0] for row in cur.fetchall())
    # Parse the reported execution time rather than timing the round trip, so
    # network and psycopg2 overhead stay out of the number.
    exec_line = [ln for ln in plan.splitlines() if ln.startswith("Execution Time:")][0]
    return plan, float(exec_line.split()[2])


def _measure(conn, label, sql, params=None):
    timings = []
    plan = None
    for i in range(WARMUP + RUNS):
        plan, ms = _explain(conn, sql, params)
        if i >= WARMUP:
            timings.append(ms)
    median = statistics.median(timings)
    log.info("%-36s median %8.3f ms   (min %.3f / max %.3f)",
             label, median, min(timings), max(timings))
    log.info("plan for %s:\n%s", label, plan)
    # Scan type is the part that actually shows whether an index was chosen.
    scans = sorted({ln.strip().split("  ")[0].lstrip("-> ")
                    for ln in plan.splitlines() if "Scan" in ln})
    return median, scans


def _probe_params(conn):
    """Pick real keys from the warehouse so the probes are not measuring empty results."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT driver_key, race_key, constructor_key
            FROM fact_race_result
            ORDER BY race_date DESC
            LIMIT 1
        """)
        driver, race, constructor = cur.fetchone()
        cur.execute("SELECT MAX(race_date) - INTERVAL '30 days' FROM fact_race_result")
        cutoff = cur.fetchone()[0]
    return {"driver": driver, "race": race, "constructor": constructor, "cutoff": cutoff}


def run(label=None):
    setup_logging(f"explain_{label}" if label else "explain")
    log.info("EXPLAIN ANALYZE capture: label=%s runs=%d (+%d warmup)", label, RUNS, WARMUP)

    conn = db.get_conn(config.dw_dsn())
    try:
        params = _probe_params(conn)
        log.info("probe parameters: %s", params)

        log.info("=== VIEWS (full scans -- an index cannot help these) ===")
        view_results = {v: _measure(conn, v, f"SELECT * FROM {v}") for v in VIEWS}

        log.info("=== PROBES (selective -- this is where an index pays) ===")
        probe_results = {name: _measure(conn, name, sql, params)
                         for name, sql in PROBES.items()}

        log.info("--- summary (%s) ---", label or "unlabelled")
        for name, (median, scans) in {**view_results, **probe_results}.items():
            log.info("%-36s %9.3f ms   %s", name, median, ", ".join(scans))
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="tag the log file, e.g. before / after")
    run(parser.parse_args().label)
