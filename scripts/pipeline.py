"""Run the f1_prod -> f1_dw pipeline: extract, transform, quality gate, load.

    python scripts/pipeline.py                  # incremental (default)
    python scripts/pipeline.py --full-reload    # re-read every result

Holds no business logic -- it opens the two connections, calls the modules in
foreign-key order, times each stage, and closes the connections in a finally.
Logic that only ran here could only be tested by running the whole pipeline.

Both modes are idempotent: every conflict target is a natural or source key and
every conflict does DO UPDATE, so running twice lands on identical row counts.

--full-reload only widens the fact extract. Dimensions are always rebuilt at
full scope: race_laps computed over a post-watermark window would be wrong for
every race outside it, and last_season would become 2026 for every team in it.
Silent corruption, invisible in row counts.
"""
import argparse
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config, db                      # noqa: E402
from etl.logging_config import setup_logging    # noqa: E402
from etl.olap import extract, load, quality, transform   # noqa: E402

log = logging.getLogger(__name__)


def _stage(label, started):
    log.info("%s completed in %.2fs", label, time.time() - started)


def run(full_reload=False):
    setup_logging("pipeline")
    mode = "FULL" if full_reload else "INCREMENTAL"
    log.info("pipeline start: mode=%s seasons=%s-%s",
             mode, config.SEASON_START, config.SEASON_END)

    src = db.get_conn(config.prod_dsn())
    dst = db.get_conn(config.dw_dsn())
    try:
        # 1. Rows the migrations deliberately do not insert, so a truncate and
        #    reload restores a complete warehouse.
        t = time.time()
        load.seed_unknown_members(dst)
        load.populate_dim_date(dst, config.SEASON_START, config.SEASON_END)
        _stage("seeds", t)

        # 2. Dimensions, always at full scope. extract.py derives every
        #    dimension attribute in SQL, so these go straight to load.
        t = time.time()
        load.load_dim_driver(dst, extract.extract_driver(src))
        load.load_dim_constructor(dst, extract.extract_constructor(src))
        load.load_dim_circuit(dst, extract.extract_circuit(src))
        load.load_dim_status(dst, extract.extract_status(src))
        races = extract.extract_race(src)
        load.load_dim_race(dst, races)
        _stage("dimension load", t)

        # 3. Surrogate keys exist only once the dimensions are loaded.
        t = time.time()
        lookups = extract.extract_lookup_dim(dst)
        _stage("lookup extraction", t)

        # 4. Facts. The full qualifying set is always read, even incrementally:
        #    it feeds the quali_position map denormalised onto the race fact,
        #    and the two facts have independent watermarks whose windows can
        #    drift apart -- without this a re-processed result row could
        #    overwrite a correct quali_position with NULL.
        t = time.time()
        qualifying_all = extract.extract_qualifying_full(src)
        if full_reload:
            result_rows = extract.extract_results_full(src)
            qualifying_rows = qualifying_all
        else:
            result_rows = extract.extract_results_incremental(
                src, extract.get_race_result_watermark(dst))
            qualifying_rows = extract.extract_qualifying_incremental(
                src, extract.get_qualifying_watermark(dst))
        _stage("fact extraction", t)

        t = time.time()
        fact_results = transform.transform_results(result_rows, qualifying_all, lookups)
        fact_qualifying = transform.transform_qualifying(qualifying_rows, lookups)
        _stage("transformation", t)

        # 5. The gate runs on transformed rows, before any write to the facts.
        t = time.time()
        race_laps_by_key = {
            lookups["race"][(r["season"], r["round"])]: r["race_laps"]
            for r in races if (r["season"], r["round"]) in lookups["race"]
        }
        quality.run_quality_checks(fact_results, fact_qualifying,
                                   race_laps_by_key, full_reload=full_reload)
        _stage("quality gate", t)

        t = time.time()
        load.load_fact_race_result(dst, fact_results)
        load.load_fact_qualifying(dst, fact_qualifying)
        _stage("fact load", t)

        log.info("pipeline complete: mode=%s results=%d qualifying=%d",
                 mode, len(fact_results), len(fact_qualifying))
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 OLTP -> OLAP pipeline")
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="re-read every result instead of only those past the watermark",
    )
    run(parser.parse_args().full_reload)
