"""Jolpica API -> data/raw/*.json -> f1_prod (3NF).

The scheduled counterpart to scripts/backfill.py, which stays the tool for a bulk
historical load: 33 seasons of history does not belong on a weekly schedule. This
DAG watches the CURRENT season for new races.

THE ONLY TASK THAT TOUCHES THE NETWORK IS extract_to_raw. Everything downstream
reads files from data/raw/, which is the hard boundary the whole design rests on:
once JSON is on disk, parse and load are fully offline and a re-run never re-hits
the API. That is what makes this DAG safe to demo without wifi.

DEMO RULE: prefer not to trigger this DAG live against the API. A cold extraction is
110-140 requests against a rate-limited free service that already returns frequent
429s. A warm run with `refresh` on is only ~21 (the reference endpoints plus the
in-progress season -- closed seasons stay cached either way), and every page falls
back to its cached copy if the network is down, so it is no longer the hazard it was.
Set refresh=false for a guaranteed zero-request run. Either way data/raw/ and f1_prod
stay pre-loaded as stable ground, and the live demo is f1_oltp_to_dw.

Task order is forced by foreign keys -- reference -> races -> results/qualifying --
the same order scripts/backfill.py uses.

THIS DAG STARTS f1_oltp_to_dw. Once check_oltp is green, trigger_dw fires the
warehouse DAG, which has no schedule of its own -- so the warehouse loads when
validated new OLTP data exists rather than on a clock. Set trigger_dw=false to load
f1_prod without touching the warehouse; f1_oltp_to_dw can still be triggered by hand
at any time.
"""
from datetime import datetime, timedelta

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG, Param, task

from etl import config
from etl.extract import landing
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
        "refresh": Param(
            True,
            type="boolean",
            description=(
                "Refetch the endpoints that GROW: the four reference tables and the season "
                "still being run. Closed seasons are immutable and stay cached either way. "
                "Off means a guaranteed zero-request run; on, a page whose refetch fails "
                "falls back to its cached copy, so an offline run still succeeds."
            ),
        ),
        "trigger_dw": Param(
            True,
            type="boolean",
            description=(
                "Trigger f1_oltp_to_dw once the OLTP load has passed check_oltp. Off loads "
                "the OLTP database without touching the warehouse -- useful when loading "
                "several seasons back to back, or when demoing this DAG on its own. "
                "f1_oltp_to_dw can always be triggered manually regardless."
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

        Which endpoints are landed, and which are refreshed rather than served from
        cache, is decided in etl/extract/landing.py -- the same definition backfill.py
        uses, so the two cannot drift. With refresh on this is ~21 requests.
        """
        seasons = _seasons(context)
        landing.land_all(JolpicaClient(), seasons, refresh=context["params"]["refresh"])
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
            _, skipped = load.load_races(conn, parse.parse_races(seasons), circuits,
                                         run_keys=run_keys)
            return skipped
        finally:
            conn.close()

    @task
    def load_results(**context):
        """Race results. Needs race/driver/constructor/status surrogate keys."""
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            _, skipped = load.load_results(
                conn,
                parse.parse_results(seasons),
                load.fetch_race_lookup(conn),
                load.fetch_lookup(conn, "drivers", "driver_ref", "driver_id"),
                load.fetch_lookup(conn, "constructors", "constructor_ref", "constructor_id"),
                load.fetch_lookup(conn, "statuses", "status_text", "status_id"),
            )
            return skipped
        finally:
            conn.close()

    @task
    def load_qualifying(**context):
        """Qualifying. No status dimension -- qualifying has no finishing status."""
        seasons = _seasons(context)
        conn = PostgresHook(CONN_ID).get_conn()
        try:
            _, skipped = load.load_qualifying(
                conn,
                parse.parse_qualifying(seasons),
                load.fetch_race_lookup(conn),
                load.fetch_lookup(conn, "drivers", "driver_ref", "driver_id"),
                load.fetch_lookup(conn, "constructors", "constructor_ref", "constructor_id"),
            )
            return skipped
        finally:
            conn.close()

    @task
    def check_oltp(skipped):
        """Row counts, and fail on anything the loaders dropped.

        The loaders skip a row with a missing FK and log a warning rather than
        crashing, so nothing here would have raised on its own -- and a dropped row
        leaves NO trace in the database to query for afterwards, because it was never
        inserted. The count has to be carried out of the load tasks; that is what
        `skipped` is. This is the check that turns those warnings into a red task.

        Zero tolerance is deliberate. A skipped row means a driver, circuit or race
        the reference tables have never heard of -- stale cached reference JSON, or a
        parse regression. Neither is ever acceptable, so there is no threshold to tune.

        This task passing is what allows trigger_dw to run, so a red gate here stops
        the warehouse DAG from ever starting.
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

            dropped = sum(skipped)
            if dropped:
                raise ValueError(
                    f"{dropped} rows dropped for unresolvable foreign keys. The rows are "
                    f"NOT in f1_prod and nothing else fails on this -- see the 'skip ...' "
                    f"warnings in the load task logs for which. Most likely cause: a "
                    f"driver/circuit that debuted after the cached reference JSON was "
                    f"landed. Re-run extract_to_raw with refresh=true."
                )
            if bad_finish:
                raise ValueError(f"{bad_finish} results rows violate the finish_position rule")
            if counts["results"] == 0:
                raise ValueError(f"no results loaded (counts={counts})")

            print("f1_prod row counts:", counts)
            return counts
        finally:
            conn.close()

    @task.short_circuit
    def should_trigger_dw(counts, **context):
        """The trigger_dw param, as a gate.

        Returning False SKIPS everything downstream, which is how a run loads
        f1_prod without touching the warehouse. Downstream of check_oltp, so a red
        gate means this never runs and the warehouse DAG is never started -- bad
        OLTP data cannot reach f1_dw.
        """
        if not context["params"]["trigger_dw"]:
            print("trigger_dw=false: f1_prod updated, NOT triggering f1_oltp_to_dw. "
                  "Run it by hand when the warehouse should catch up.")
            return False
        print("f1_prod validated, triggering f1_oltp_to_dw ->", counts)
        return True

    # An explicit DAG-to-DAG trigger. wait_for_completion defaults to False, which is
    # what we want: this DAG's job is done once f1_prod is loaded and validated, and
    # it should not sit occupied watching the warehouse load.
    trigger_dw = TriggerDagRunOperator(
        task_id="trigger_dw",
        trigger_dag_id="f1_oltp_to_dw",
    )

    raw = extract_to_raw()
    reference = load_reference()
    races = load_races()
    results = load_results()
    qualifying = load_qualifying()

    # Passing the skip counts makes the gate a real data dependency, not just an
    # ordering one -- check_oltp cannot run without the numbers it has to judge.
    checked = check_oltp(skipped=[races, results, qualifying])
    gated = should_trigger_dw(counts=checked)

    raw >> reference >> races >> [results, qualifying] >> checked >> gated >> trigger_dw
