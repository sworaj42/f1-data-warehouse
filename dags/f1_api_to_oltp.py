"""Jolpica API -> data/raw/*.json -> f1_prod (3NF).

The scheduled counterpart to scripts/backfill.py, which stays the tool for a bulk
historical load: 33 seasons of history does not belong on a weekly schedule. This
DAG watches the CURRENT season for new races.

THE ONLY TASK THAT TOUCHES THE NETWORK IS extract_to_raw. Everything downstream
reads files from data/raw/, which is the hard boundary the whole design rests on:
once JSON is on disk, parse and load are fully offline and a re-run never re-hits
the API. That is what makes this DAG safe to demo without wifi.

DEMO RULE: do not trigger this DAG live against the API. A full extraction is
110-140 requests against a rate-limited free service that already returns frequent
429s. data/raw/ and f1_prod stay pre-loaded as stable ground; the live demo is
f1_oltp_to_dw.

Task order is forced by foreign keys -- reference -> races -> results/qualifying --
the same order scripts/backfill.py uses.
"""
from datetime import datetime, timedelta

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import DAG, Param, task

from etl import config
from etl.extract.jolpica import JolpicaClient
from etl.oltp import load, parse

CONN_ID = "f1_oltp"   # f1_prod


def _seasons(context):
    """Seasons for this run. Defaults to the current season only."""
    seasons = context["params"].get("seasons")
    return sorted(seasons) if seasons else [config.SEASON_END]


with DAG(
    dag_id="f1_api_to_oltp",
    description="Land Jolpica-F1 JSON and upsert it into the 3NF f1_prod database",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    # Weekly: races are roughly two weeks apart, so most runs legitimately find
    # nothing new. The loads are idempotent upserts, so a no-op run is free.
    schedule="@weekly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    params={
        "seasons": Param(
            [],
            type="array",
            description=(
                "Seasons to process. Empty means the current season only. This is NOT the "
                "backfill tool -- use scripts/backfill.py for the full 1994-2026 range."
            ),
        ),
    },
    tags=["f1", "oltp", "api"],
) as dag:

    @task
    def extract_to_raw(**context):
        """Land every endpoint's JSON under data/raw/. The only networked task.

        JolpicaClient skips pages already cached, so re-running this is offline and
        free. It enforces 4 req/sec and 500 req/hour client-side with a dual token
        bucket rather than reacting to HTTP 429 -- a 429 means we were already rude
        to a free service.
        """
        seasons = _seasons(context)
        client = JolpicaClient()
        client.land("circuits/", "circuits")
        client.land("drivers/", "drivers")
        client.land("constructors/", "constructors")
        client.land("status/", "status")
        for season in seasons:
            client.land(f"{season}/races/", f"races/{season}")
            client.land(f"{season}/results/", f"results/{season}")
            client.land(f"{season}/qualifying/", f"qualifying/{season}")
        return seasons

    @task
    def load_reference(**context):
        """The four tables with no foreign keys, so they go first.

        load_statuses runs twice on purpose: /status does not return every status
        string that actually appears in a result, so the second call backfills the
        difference. Without it, results rows would fail their status FK and be
        skipped.
        """
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            load.load_circuits(conn, parse.parse_circuits())
            load.load_drivers(conn, parse.parse_drivers())
            load.load_constructors(conn, parse.parse_constructors())
            load.load_statuses(conn, parse.parse_statuses())

            results = parse.parse_results(seasons)
            extra = [{"status_code": None, "status_text": t}
                     for t in {r["status_text"] for r in results}]
            load.load_statuses(conn, extra)
        finally:
            conn.close()

    @task
    def load_races(**context):
        """Races, keyed to circuits -- and ONLY races that have actually run.

        A scheduled season lists future rounds in /races with no results yet.
        run_keys holds them back until they have been raced, which is why
        dim_race can trust that every race it sees really happened.

        Parsing results again here is a local file read, and cheaper than passing
        the parsed rows between tasks through XCom.
        """
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            results = parse.parse_results(seasons)
            circuits = load.fetch_lookup(conn, "circuits", "circuit_ref", "circuit_id")
            run_keys = {(r["season"], r["round"]) for r in results}
            load.load_races(conn, parse.parse_races(seasons), circuits, run_keys=run_keys)
        finally:
            conn.close()

    @task
    def load_results(**context):
        """Race results. Needs race/driver/constructor/status surrogate keys."""
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            load.load_results(
                conn,
                parse.parse_results(seasons),
                load.fetch_race_lookup(conn),
                load.fetch_lookup(conn, "drivers", "driver_ref", "driver_id"),
                load.fetch_lookup(conn, "constructors", "constructor_ref", "constructor_id"),
                load.fetch_lookup(conn, "statuses", "status_text", "status_id"),
            )
        finally:
            conn.close()

    @task
    def load_qualifying(**context):
        """Qualifying. No status dimension -- qualifying has no finishing status."""
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            load.load_qualifying(
                conn,
                parse.parse_qualifying(seasons),
                load.fetch_race_lookup(conn),
                load.fetch_lookup(conn, "drivers", "driver_ref", "driver_id"),
                load.fetch_lookup(conn, "constructors", "constructor_ref", "constructor_id"),
            )
        finally:
            conn.close()

    @task
    def check_oltp():
        """Row counts, and fail on an orphaned foreign key.

        The loaders skip a row with a missing FK and log a warning rather than
        crashing, so nothing here would have raised on its own. This is the check
        that turns those warnings into a red task.
        """
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            tables = ["circuits", "drivers", "constructors", "statuses",
                      "races", "results", "qualifying"]
            counts = {}
            with conn.cursor() as cur:
                for table in tables:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]

                # finish_position is NULL exactly when position_text is non-numeric.
                # The DB enforces this with chk_results_finish, so a violation here
                # would mean the constraint was dropped.
                cur.execute("""
                    SELECT count(*) FROM results
                    WHERE (finish_position IS NULL) <> (position_text !~ '^[0-9]+$')
                """)
                bad_finish = cur.fetchone()[0]

            if bad_finish:
                raise ValueError(f"{bad_finish} results rows violate the finish_position rule")
            if counts["results"] == 0:
                raise ValueError(f"no results loaded (counts={counts})")

            print("f1_prod row counts:", counts)
            return counts
        finally:
            conn.close()

    raw = extract_to_raw()
    reference = load_reference()
    races = load_races()

    raw >> reference >> races >> [load_results(), load_qualifying()] >> check_oltp()
