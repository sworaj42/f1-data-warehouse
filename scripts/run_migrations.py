"""Apply sql/oltp/*.sql migrations in order, tracked in a schema_migrations ledger.

Safe to re-run: already-applied files are skipped, and each DDL file uses
CREATE TABLE IF NOT EXISTS, so a re-run on an existing database is a no-op.

    python scripts/run_migrations.py
"""
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                     # noqa: E402
from etl.logging_config import setup_logging   # noqa: E402

log = logging.getLogger(__name__)

MIGRATIONS_DIR = config.BASE_DIR / "sql" / "oltp"

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


def run():
    setup_logging("migrations")
    conn = db.get_conn()
    try:
        with db.transaction(conn), conn.cursor() as cur:
            cur.execute(_LEDGER_DDL)

        done = _applied(conn)
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
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
    run()
