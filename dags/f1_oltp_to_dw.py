"""f1_prod (3NF) -> f1_dw (star schema).

The same extract -> transform -> quality -> load flow as scripts/pipeline.py, as
an Airflow graph: seeds, then five dimension loads in parallel, then one fact
task, then a verification.

WHY THE DAG IMPORTS etl.olap INSTEAD OF SHELLING OUT TO scripts/pipeline.py.
A DAG whose graph is a single BashOperator box demonstrates nothing about
orchestration. The cost is real and worth stating out loud rather than hiding:
scripts/pipeline.py and this file are now TWO CALLERS of the same modules and
can drift. They are kept deliberately parallel -- same call order, same
arguments -- so a change to one is an obvious change to the other.

None of this required touching etl/. Every function there takes an open `conn`
as its first argument and never opens or closes it, which is exactly why the
same code runs from a script and from a task.

CONNECTIONS come from Airflow, not from .env. f1_postgres runs in its own compose
stack on the host, so the conn ids below resolve through host.docker.internal --
see docker-compose.airflow.yml. The DAG never reads POSTGRES_HOST.
"""
from datetime import datetime, timedelta

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import DAG, Param, task

from etl import config
from etl.olap import extract, load, quality, transform

SRC_CONN_ID = "f1_oltp"   # f1_prod
DEST_CONN_ID = "f1_dw"    # f1_dw


def _conns():
    """(source, warehouse). The caller owns both and closes them in a finally."""
    return PostgresHook(SRC_CONN_ID).get_conn(), PostgresHook(DEST_CONN_ID).get_conn()


with DAG(
    dag_id="f1_oltp_to_dw",
    description="Load the F1 star schema in f1_dw from the 3NF f1_prod database",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    params={
        "full_reload": Param(
            False,
            type="boolean",
            description=(
                "Re-read every result instead of the watermark window. Note this widens the "
                "FACT extract only -- dimensions always rebuild at full scope, or race_laps "
                "and last_season are silently computed over the wrong window."
            ),
        ),
    },
    tags=["f1", "olap"],
) as dag:

    @task
    def seeds():
        """The -1 unknown members and the dim_date populate.

        Runs before every dimension because a fact must never need a NULL FK, and
        because sql/olap/*.sql contains no INSERT: the migrations are structure
        only, so a TRUNCATE + reload has to restore these rows from here. Both are
        ON CONFLICT DO NOTHING, so this is safe on every run.
        """
        _, dst = _conns()
        try:
            load.seed_unknown_members(dst)
            load.populate_dim_date(dst, config.SEASON_START, config.SEASON_END)
        finally:
            dst.close()

    # The five dimension tasks are genuinely independent, so they run in parallel.
    # Each is one extract + one load with no transform between them: extract.py
    # derives every dimension attribute in SQL, so there is nothing to transform.
    @task
    def dim_driver():
        src, dst = _conns()
        try:
            load.load_dim_driver(dst, extract.extract_driver(src))
        finally:
            src.close()
            dst.close()

    @task
    def dim_constructor():
        src, dst = _conns()
        try:
            load.load_dim_constructor(dst, extract.extract_constructor(src))
        finally:
            src.close()
            dst.close()

    @task
    def dim_circuit():
        src, dst = _conns()
        try:
            load.load_dim_circuit(dst, extract.extract_circuit(src))
        finally:
            src.close()
            dst.close()

    @task
    def dim_status():
        src, dst = _conns()
        try:
            load.load_dim_status(dst, extract.extract_status(src))
        finally:
            src.close()
            dst.close()

    @task
    def dim_race():
        src, dst = _conns()
        try:
            load.load_dim_race(dst, extract.extract_race(src))
        finally:
            src.close()
            dst.close()

    @task
    def load_facts(**context):
        """Extract, transform, gate and load BOTH facts -- deliberately one task.

        These four stages hand 13,006 + 11,190 rows to each other in memory.
        Splitting them across tasks would mean pushing that through XCom, which is
        a column in Airflow's metadata database, not a data channel. So the task
        boundary sits where the data boundary is.

        The quality gate runs INSIDE this task and before any write, so a failure
        leaves the facts untouched. It raises DataQualityError -- a dedicated type
        precisely so "the data was bad" is distinguishable from "the database was
        down" when this task goes red.
        """
        full_reload = context["params"]["full_reload"]
        src, dst = _conns()
        try:
            # Surrogate keys exist only once the dimension tasks upstream have run.
            lookups = extract.extract_lookup_dim(dst)

            # The FULL qualifying set is read even on an incremental run: it feeds the
            # quali_position denormalised onto the race fact, and the two facts have
            # independent watermarks whose windows can drift apart. Without it a
            # re-processed result row could overwrite a correct quali_position with NULL.
            qualifying_all = extract.extract_qualifying_full(src)

            if full_reload:
                result_rows = extract.extract_results_full(src)
                qualifying_rows = qualifying_all
            else:
                result_rows = extract.extract_results_incremental(
                    src, extract.get_race_result_watermark(dst))
                qualifying_rows = extract.extract_qualifying_incremental(
                    src, extract.get_qualifying_watermark(dst))

            fact_results = transform.transform_results(result_rows, qualifying_all, lookups)
            fact_qualifying = transform.transform_qualifying(qualifying_rows, lookups)

            # race_laps is needed by the gate's laps_completed check. Re-reading the
            # races here is one cheap query -- cheaper, and far clearer, than passing
            # a dict from the dim_race task through XCom.
            races = extract.extract_race(src)
            race_laps_by_key = {
                lookups["race"][(r["season"], r["round"])]: r["race_laps"]
                for r in races if (r["season"], r["round"]) in lookups["race"]
            }

            quality.run_quality_checks(fact_results, fact_qualifying,
                                       race_laps_by_key, full_reload=full_reload)

            load.load_fact_race_result(dst, fact_results)
            load.load_fact_qualifying(dst, fact_qualifying)
            return {"results": len(fact_results), "qualifying": len(fact_qualifying)}
        finally:
            src.close()
            dst.close()

    @task
    def verify():
        """Row counts, and fail loudly on an empty dimension.

        Without this the DAG goes green whenever the tasks merely did not raise.
        An empty dimension is the failure mode that a truncate-and-reload would
        produce, so it is the one worth asserting on.

        An empty FACT batch is NOT an error: races are two weeks apart, so most
        scheduled runs legitimately have nothing new to load.
        """
        _, dst = _conns()
        try:
            counts = {}
            with dst.cursor() as cur:
                for table in ("dim_date", "dim_driver", "dim_constructor", "dim_circuit",
                              "dim_race", "dim_status", "fact_race_result", "fact_qualifying"):
                    cur.execute(f"SELECT count(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]

            empty = [t for t, n in counts.items() if t.startswith("dim_") and n == 0]
            if empty:
                raise ValueError(f"dimension(s) empty after load: {empty} (counts={counts})")

            print("warehouse row counts:", counts)
            return counts
        finally:
            dst.close()

    dims = [dim_driver(), dim_constructor(), dim_circuit(), dim_status(), dim_race()]
    seeds() >> dims >> load_facts() >> verify()
