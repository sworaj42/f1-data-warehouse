"""Load normalized rows into f1_prod with idempotent upserts.

Dimensions/reference tables:  ON CONFLICT (natural_key) DO UPDATE.
Transaction tables:           resolve surrogate FKs from in-memory lookups,
                              skip+log any row with a missing FK, then
                              ON CONFLICT (race_id, driver_id) DO UPDATE.

Running any load twice produces identical row counts -- the conflict target is
the natural/business key, so a second run updates in place rather than inserting.
Every load runs inside an explicit transaction (etl.db.transaction).

Skipping is deliberately non-fatal HERE and fatal in the CALLER: a loader that
raised mid-batch would abandon good rows over one bad one, so instead the three
transaction loaders return (upserted, skipped) and the orchestrator decides. Both
orchestrators treat skipped > 0 as a failure -- a dropped row is silent data loss,
and a warning in a task log is not a signal anyone sees.
"""
import logging

from psycopg2.extras import execute_values

from etl import db

log = logging.getLogger(__name__)


# --- generic helpers -------------------------------------------------------
def _dedup(rows: list[dict], key) -> tuple[list[dict], int]:
    """Deduplicate within a batch by conflict key (keep last). Returns (rows, removed)."""
    seen = {}
    for r in rows:
        seen[key(r)] = r
    deduped = list(seen.values())
    return deduped, len(rows) - len(deduped)


def _upsert(conn, name: str, sql: str, cols: list[str], rows: list[dict]) -> int:
    if not rows:
        log.warning("%s: no rows to load", name)
        return 0
    values = [tuple(r.get(c) for c in cols) for r in rows]
    with db.transaction(conn), conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)
    return len(values)


def fetch_lookup(conn, table: str, key_col: str, id_col: str) -> dict:
    """Build a {natural_key: surrogate_id} map from a loaded table."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT {key_col}, {id_col} FROM {table}")
        return {row[0]: row[1] for row in cur.fetchall()}


def fetch_race_lookup(conn) -> dict:
    """{(season, round): race_id} -- the composite natural key of races."""
    with conn.cursor() as cur:
        cur.execute("SELECT season, round, race_id FROM races")
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}


# --- reference tables ------------------------------------------------------
_CIRCUIT_COLS = ["circuit_ref", "name", "locality", "country", "latitude", "longitude"]
_CIRCUIT_SQL = """
INSERT INTO circuits (circuit_ref, name, locality, country, latitude, longitude)
VALUES %s
ON CONFLICT (circuit_ref) DO UPDATE SET
    name = EXCLUDED.name, locality = EXCLUDED.locality, country = EXCLUDED.country,
    latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
"""


def load_circuits(conn, rows):
    n = _upsert(conn, "circuits", _CIRCUIT_SQL, _CIRCUIT_COLS, rows)
    log.info("circuits: upserted %d", n)
    return n


_DRIVER_COLS = ["driver_ref", "permanent_number", "code", "forename", "surname",
                "date_of_birth", "nationality"]
_DRIVER_SQL = """
INSERT INTO drivers (driver_ref, permanent_number, code, forename, surname, date_of_birth, nationality)
VALUES %s
ON CONFLICT (driver_ref) DO UPDATE SET
    permanent_number = EXCLUDED.permanent_number, code = EXCLUDED.code,
    forename = EXCLUDED.forename, surname = EXCLUDED.surname,
    date_of_birth = EXCLUDED.date_of_birth, nationality = EXCLUDED.nationality
"""


def load_drivers(conn, rows):
    n = _upsert(conn, "drivers", _DRIVER_SQL, _DRIVER_COLS, rows)
    log.info("drivers: upserted %d", n)
    return n


_CONSTRUCTOR_COLS = ["constructor_ref", "name", "nationality"]
_CONSTRUCTOR_SQL = """
INSERT INTO constructors (constructor_ref, name, nationality)
VALUES %s
ON CONFLICT (constructor_ref) DO UPDATE SET
    name = EXCLUDED.name, nationality = EXCLUDED.nationality
"""


def load_constructors(conn, rows):
    n = _upsert(conn, "constructors", _CONSTRUCTOR_SQL, _CONSTRUCTOR_COLS, rows)
    log.info("constructors: upserted %d", n)
    return n


_STATUS_COLS = ["status_code", "status_text"]
# COALESCE keeps an existing code when a text is re-seen from a result row (code NULL).
_STATUS_SQL = """
INSERT INTO statuses (status_code, status_text)
VALUES %s
ON CONFLICT (status_text) DO UPDATE SET
    status_code = COALESCE(EXCLUDED.status_code, statuses.status_code)
"""


def load_statuses(conn, rows):
    rows, removed = _dedup(rows, key=lambda r: r["status_text"])
    n = _upsert(conn, "statuses", _STATUS_SQL, _STATUS_COLS, rows)
    log.info("statuses: upserted %d (deduped %d)", n, removed)
    return n


# --- races -----------------------------------------------------------------
_RACE_COLS = ["season", "round", "race_name", "race_date", "race_time", "qualifying_date", "circuit_id"]
_RACE_SQL = """
INSERT INTO races (season, round, race_name, race_date, race_time, qualifying_date, circuit_id)
VALUES %s
ON CONFLICT (season, round) DO UPDATE SET
    race_name = EXCLUDED.race_name, race_date = EXCLUDED.race_date,
    race_time = EXCLUDED.race_time, qualifying_date = EXCLUDED.qualifying_date,
    circuit_id = EXCLUDED.circuit_id
"""


def load_races(conn, rows, circuit_lookup, run_keys=None):
    """Load races. If run_keys is given (set of (season, round)), only races that have
    actually been run are loaded -- future rounds of an in-progress season are held back
    until they produce results, so a race never exists without a result row.

    Returns (upserted, skipped). `skipped` counts rows DROPPED for an unresolvable FK
    and is always a bug -- the caller is expected to fail on it. It deliberately excludes
    `unrun`, which is the intended hold-back above, not a failure."""
    prepared, skipped, unrun = [], 0, 0
    for r in rows:
        if run_keys is not None and (r["season"], r["round"]) not in run_keys:
            unrun += 1
            continue
        cid = circuit_lookup.get(r["circuit_ref"])
        if cid is None:
            skipped += 1
            log.warning("skip race %s R%02d: unknown circuit_ref=%s", r["season"], r["round"], r["circuit_ref"])
            continue
        prepared.append({**r, "circuit_id": cid})
    prepared, removed = _dedup(prepared, key=lambda r: (r["season"], r["round"]))
    n = _upsert(conn, "races", _RACE_SQL, _RACE_COLS, prepared)
    log.info("races: upserted %d (skipped %d, deduped %d, not-yet-run %d)", n, skipped, removed, unrun)
    return n, skipped


# --- results ---------------------------------------------------------------
_RESULT_COLS = ["race_id", "driver_id", "constructor_id", "status_id", "car_number",
                "grid_position", "finish_position", "position_text", "position_order",
                "points", "laps_completed", "race_time_ms", "fastest_lap_number",
                "fastest_lap_rank", "fastest_lap_time_ms", "fastest_lap_speed_kph"]
_RESULT_SQL = """
INSERT INTO results (
    race_id, driver_id, constructor_id, status_id, car_number, grid_position,
    finish_position, position_text, position_order, points, laps_completed,
    race_time_ms, fastest_lap_number, fastest_lap_rank, fastest_lap_time_ms, fastest_lap_speed_kph
)
VALUES %s
ON CONFLICT (race_id, driver_id) DO UPDATE SET
    constructor_id = EXCLUDED.constructor_id, status_id = EXCLUDED.status_id,
    car_number = EXCLUDED.car_number, grid_position = EXCLUDED.grid_position,
    finish_position = EXCLUDED.finish_position, position_text = EXCLUDED.position_text,
    position_order = EXCLUDED.position_order, points = EXCLUDED.points,
    laps_completed = EXCLUDED.laps_completed, race_time_ms = EXCLUDED.race_time_ms,
    fastest_lap_number = EXCLUDED.fastest_lap_number, fastest_lap_rank = EXCLUDED.fastest_lap_rank,
    fastest_lap_time_ms = EXCLUDED.fastest_lap_time_ms, fastest_lap_speed_kph = EXCLUDED.fastest_lap_speed_kph
"""


def load_results(conn, rows, races, drivers, constructors, statuses):
    """Returns (upserted, skipped). A skipped row is silent data loss -- most often a
    driver/circuit that debuted after the cached reference JSON was landed -- so the
    caller must fail on it. Nothing else will: this loop warns and carries on."""
    prepared, skipped = [], 0
    for r in rows:
        rid = races.get((r["season"], r["round"]))
        did = drivers.get(r["driver_ref"])
        cid = constructors.get(r["constructor_ref"])
        sid = statuses.get(r["status_text"])
        if None in (rid, did, cid, sid):
            skipped += 1
            log.warning("skip result %s R%02d driver=%s: missing fk (race=%s driver=%s cons=%s status=%s)",
                        r["season"], r["round"], r["driver_ref"], rid, did, cid, sid)
            continue
        prepared.append({**r, "race_id": rid, "driver_id": did, "constructor_id": cid, "status_id": sid})
    prepared, removed = _dedup(prepared, key=lambda r: (r["race_id"], r["driver_id"]))
    n = _upsert(conn, "results", _RESULT_SQL, _RESULT_COLS, prepared)
    log.info("results: upserted %d (skipped %d, deduped %d)", n, skipped, removed)
    return n, skipped


# --- qualifying ------------------------------------------------------------
_QUALI_COLS = ["race_id", "driver_id", "constructor_id", "car_number",
               "quali_position", "q1_ms", "q2_ms", "q3_ms"]
_QUALI_SQL = """
INSERT INTO qualifying (race_id, driver_id, constructor_id, car_number, quali_position, q1_ms, q2_ms, q3_ms)
VALUES %s
ON CONFLICT (race_id, driver_id) DO UPDATE SET
    constructor_id = EXCLUDED.constructor_id, car_number = EXCLUDED.car_number,
    quali_position = EXCLUDED.quali_position, q1_ms = EXCLUDED.q1_ms,
    q2_ms = EXCLUDED.q2_ms, q3_ms = EXCLUDED.q3_ms
"""


def load_qualifying(conn, rows, races, drivers, constructors):
    """Returns (upserted, skipped). Same contract as load_results: a skip is data loss,
    and the caller is the only thing that can turn it into a failure."""
    prepared, skipped = [], 0
    for r in rows:
        rid = races.get((r["season"], r["round"]))
        did = drivers.get(r["driver_ref"])
        cid = constructors.get(r["constructor_ref"])
        if None in (rid, did, cid):
            skipped += 1
            log.warning("skip quali %s R%02d driver=%s: missing fk (race=%s driver=%s cons=%s)",
                        r["season"], r["round"], r["driver_ref"], rid, did, cid)
            continue
        prepared.append({**r, "race_id": rid, "driver_id": did, "constructor_id": cid})
    prepared, removed = _dedup(prepared, key=lambda r: (r["race_id"], r["driver_id"]))
    n = _upsert(conn, "qualifying", _QUALI_SQL, _QUALI_COLS, prepared)
    log.info("qualifying: upserted %d (skipped %d, deduped %d)", n, skipped, removed)
    return n, skipped
