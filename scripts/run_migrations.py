"""Apply SQL migrations in order, tracked in a schema_migrations ledger.

Two targets, one per database. Each database keeps its own ledger, so applying the
OLTP migrations never marks the OLAP ones as done.

Safe to re-run: already-applied files are skipped, and each DDL file uses
CREATE TABLE IF NOT EXISTS (and ON CONFLICT DO NOTHING for seeded rows), so a
re-run on an existing database is a no-op.

    python scripts/run_migrations.py                 # oltp (default)
    python scripts/run_migrations.py --target olap
"""
import argparse
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                     # noqa: E402
from etl.logging_config import setup_logging   # noqa: E402

log = logging.getLogger(__name__)

# target -> (migrations directory, DSN factory)
# analytics shares f1_dw (and therefore its ledger) with olap. It is a separate target because it
# is a separate kind of object: olap is structure the pipeline writes into, analytics is the
# read layer the dashboard consumes. Keeping them apart means the star DDL can be re-read without
# wading through view SQL.
TARGETS = {
    "oltp": (config.BASE_DIR / "sql" / "oltp", config.prod_dsn),
    "olap": (config.BASE_DIR / "sql" / "olap", config.dw_dsn),
    "analytics": (config.BASE_DIR / "sql" / "analytics", config.dw_dsn),
}

_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _applied(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def run(target: str = "oltp"):
    setup_logging("migrations")
    migrations_dir, dsn = TARGETS[target]
    log.info("target=%s db=%s dir=%s", target, dsn()["dbname"], migrations_dir)

    conn = db.get_conn(dsn())
    try:
        with db.transaction(conn), conn.cursor() as cur:
            cur.execute(_LEDGER_DDL)

        done = _applied(conn)
        files = sorted(migrations_dir.glob("*.sql"))
        newly = 0
        for f in files:
            if f.name in done:
                log.info("skip (already applied): %s", f.name)
                continue
            with db.transaction(conn), conn.cursor() as cur:
                cur.execute(f.read_text())
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,))
            newly += 1
            log.info("applied: %s", f.name)

        log.info("migrations complete: %d file(s), %d newly applied", len(files), newly)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGETS), default="oltp",
                        help="which database to migrate (default: oltp)")
    run(parser.parse_args().target)
