"""One-off backfill: Jolpica API -> raw JSON -> f1_prod (the API -> OLTP pipeline).

This is deliberately a manual script, not an Airflow DAG: a bulk historical load
does not belong on a schedule. The weekly "detect new races" DAG comes later.

    python scripts/backfill.py --smoke      # 2024 only, to validate the whole path
    python scripts/backfill.py              # full SEASON_START..SEASON_END range
    python scripts/backfill.py --season 2023 --season 2024

Idempotent: run it twice and the row counts are identical.
"""
import argparse
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                     # noqa: E402
from etl.extract.jolpica import JolpicaClient   # noqa: E402
from etl.logging_config import setup_logging    # noqa: E402
from etl.oltp import load, parse                # noqa: E402

log = logging.getLogger(__name__)

_TABLES = ["circuits", "drivers", "constructors", "statuses", "races", "results", "qualifying"]


def extract(client: JolpicaClient, seasons) -> None:
    """Land every endpoint's raw JSON to disk (skips anything already cached)."""
    log.info("=== EXTRACT: landing raw JSON ===")
    client.land("circuits/", "circuits")
    client.land("drivers/", "drivers")
    client.land("constructors/", "constructors")
    client.land("status/", "status")
    for s in seasons:
        client.land(f"{s}/races/", f"races/{s}")
        client.land(f"{s}/results/", f"results/{s}")
        client.land(f"{s}/qualifying/", f"qualifying/{s}")


def load_all(conn, seasons) -> None:
    """Parse the landed JSON and upsert every table in FK-dependency order."""
    log.info("=== LOAD: parse + upsert into f1_prod ===")

    # 1. reference tables (independent)
    load.load_circuits(conn, parse.parse_circuits())
    load.load_drivers(conn, parse.parse_drivers())
    load.load_constructors(conn, parse.parse_constructors())
    load.load_statuses(conn, parse.parse_statuses())

    # parse the transaction tables up front so we can backfill any status text
    # that appears in a result but was not returned by the /status endpoint.
    results = parse.parse_results(seasons)
    quali = parse.parse_qualifying(seasons)
    extra_statuses = [{"status_code": None, "status_text": t}
                      for t in {r["status_text"] for r in results}]
    load.load_statuses(conn, extra_statuses)

    # 2. races (needs circuit surrogate keys). Only load races that have actually been run
    #    -- future rounds of the in-progress season appear in /races but have no results yet.
    circuits = load.fetch_lookup(conn, "circuits", "circuit_ref", "circuit_id")
    run_keys = {(r["season"], r["round"]) for r in results}
    load.load_races(conn, parse.parse_races(seasons), circuits, run_keys=run_keys)

    # 3. results + qualifying (need race/driver/constructor/status surrogate keys)
    races = load.fetch_race_lookup(conn)
    drivers = load.fetch_lookup(conn, "drivers", "driver_ref", "driver_id")
    constructors = load.fetch_lookup(conn, "constructors", "constructor_ref", "constructor_id")
    statuses = load.fetch_lookup(conn, "statuses", "status_text", "status_id")

    load.load_results(conn, results, races, drivers, constructors, statuses)
    load.load_qualifying(conn, quali, races, drivers, constructors)


def row_counts(conn) -> dict:
    with conn.cursor() as cur:
        counts = {}
        for t in _TABLES:
            cur.execute(f"SELECT count(*) FROM {t}")
            counts[t] = cur.fetchone()[0]
    return counts


def main():
    ap = argparse.ArgumentParser(description="Backfill Jolpica-F1 -> f1_prod")
    ap.add_argument("--smoke", action="store_true", help="load only 2024 (smoke test)")
    ap.add_argument("--season", type=int, action="append", help="specific season(s); repeatable")
    args = ap.parse_args()

    setup_logging("backfill")

    if args.smoke:
        seasons = [2024]
    elif args.season:
        seasons = sorted(set(args.season))
    else:
        seasons = list(config.seasons())
    log.info("backfill seasons: %s", seasons)

    client = JolpicaClient()
    t0 = time.monotonic()
    extract(client, seasons)
    log.info("extract stage done in %.1fs", time.monotonic() - t0)

    conn = db.get_conn()
    try:
        t1 = time.monotonic()
        load_all(conn, seasons)
        log.info("load stage done in %.1fs", time.monotonic() - t1)
        log.info("final row counts: %s", row_counts(conn))
    finally:
        conn.close()

    log.info("backfill complete in %.1fs total", time.monotonic() - t0)


if __name__ == "__main__":
    main()
