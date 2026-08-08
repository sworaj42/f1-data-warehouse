"""Make the warehouse look "behind" so a live DAG run has visible work to do.

    python scripts/demo_seed.py            # delete the most recent race's fact rows
    python scripts/demo_seed.py --races 3  # delete the last three races
    python scripts/demo_seed.py --truncate # empty f1_dw entirely

Without this, a demo of the incremental DAG loads zero rows -- correct behaviour,
and completely unconvincing to watch. Deleting the last race's facts leaves a real
gap that the watermark then finds.

TOUCHES f1_dw ONLY. f1_prod and data/raw/ are never modified, so the demo can
always be reset without re-running the API extraction -- which is 110-140 requests
against a rate-limited free service and must never happen live.

--truncate is the full reset path, and it is deliberately safe: sql/olap/*.sql
contains no INSERT, so every row including the -1 unknown members and the 12,053
dim_date rows is restored by the pipeline (or by the DAG's `seeds` task), not by
the migrations.
"""
import argparse
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                     # noqa: E402
from etl.logging_config import setup_logging   # noqa: E402

log = logging.getLogger(__name__)

# Order matters: facts reference dimensions, and the FKs are ON DELETE RESTRICT.
_TRUNCATE_ORDER = [
    "fact_race_result", "fact_qualifying",
    "dim_date", "dim_driver", "dim_constructor", "dim_circuit", "dim_race", "dim_status",
]


def _counts(conn):
    with conn.cursor() as cur:
        out = {}
        for table in ("fact_race_result", "fact_qualifying"):
            cur.execute(f"SELECT count(*) FROM {table}")
            out[table] = cur.fetchone()[0]
        cur.execute("SELECT max(race_date) FROM fact_race_result")
        out["watermark"] = cur.fetchone()[0]
    return out


def delete_recent(conn, races):
    """Delete the fact rows for the N most recent races, by race_date.

    The dimensions are left alone on purpose: dim_race still holds the race, so
    this reproduces "the warehouse has not caught up yet" rather than "the race
    does not exist", which is the situation the incremental load actually solves.
    """
    with db.transaction(conn), conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT race_key, race_date FROM fact_race_result
            ORDER BY race_date DESC LIMIT %s
        """, (races,))
        targets = cur.fetchall()
        if not targets:
            log.warning("no fact rows to delete -- is f1_dw loaded?")
            return

        keys = [r[0] for r in targets]
        cur.execute("DELETE FROM fact_race_result WHERE race_key = ANY(%s)", (keys,))
        deleted_results = cur.rowcount
        cur.execute("DELETE FROM fact_qualifying WHERE race_key = ANY(%s)", (keys,))
        deleted_quali = cur.rowcount

    log.info("deleted %d result + %d qualifying rows for %d race(s): %s",
             deleted_results, deleted_quali, len(targets),
             ", ".join(str(r[1]) for r in targets))


def truncate_all(conn):
    with db.transaction(conn), conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(_TRUNCATE_ORDER)} RESTART IDENTITY CASCADE")
    log.info("truncated f1_dw (%d tables). A full pipeline or DAG run restores every row, "
             "including the -1 unknown members and dim_date.", len(_TRUNCATE_ORDER))


def run(races=1, truncate=False):
    setup_logging("demo_seed")
    conn = db.get_conn(config.dw_dsn())
    try:
        log.info("before: %s", _counts(conn))
        if truncate:
            truncate_all(conn)
        else:
            delete_recent(conn, races)
        log.info("after:  %s", _counts(conn))
        log.info("now trigger f1_oltp_to_dw%s", " with full_reload=true" if truncate else "")
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--races", type=int, default=1,
                    help="how many of the most recent races to un-load (default 1)")
    ap.add_argument("--truncate", action="store_true",
                    help="empty f1_dw entirely -- the full reset path")
    args = ap.parse_args()
    run(races=args.races, truncate=args.truncate)
