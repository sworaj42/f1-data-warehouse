"""Database connection helpers.

Convention (shared with the later OLTP -> OLAP pipeline and with Airflow):
every DB function takes an open `conn` as its first argument. The caller owns the
connection lifecycle and closes it in a finally block.
"""
import contextlib
import logging

import psycopg2

from etl import config

log = logging.getLogger(__name__)


def get_conn(dsn: dict | None = None):
    """Open a psycopg2 connection to f1_prod (or an explicit DSN)."""
    return psycopg2.connect(**(dsn or config.prod_dsn()))


@contextlib.contextmanager
def transaction(conn):
    """Explicit transaction boundary: commit on success, rollback on any exception.

    This is the ACID unit for every load -- try / commit / except / rollback.
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
