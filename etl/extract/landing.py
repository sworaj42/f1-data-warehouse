"""Which endpoints get landed, and which of them are allowed to go stale.

One definition, called by both orchestrators -- scripts/backfill.py (manual, once)
and dags/f1_api_to_oltp.py (weekly). They differ in how they RUN the stage (one
process vs. a retryable Airflow task) but never in what it does, so this is the only
place the endpoint list and the refresh policy exist. They were previously copied
into both, and had already drifted once.
"""
import logging

from etl import config

log = logging.getLogger(__name__)

# Not season-scoped: each returns every driver/circuit/constructor/status in F1
# history, so refreshing one refetches the whole all-time list (~12 pages total).
REFERENCE = [
    ("circuits/", "circuits"),
    ("drivers/", "drivers"),
    ("constructors/", "constructors"),
    ("status/", "status"),
]

# Season-scoped, so these are fetched once per season in the range.
SEASONAL = [
    ("{season}/races/", "races/{season}"),
    ("{season}/results/", "results/{season}"),
    ("{season}/qualifying/", "qualifying/{season}"),
]


def land_all(client, seasons, refresh: bool = False) -> None:
    """Land every endpoint for `seasons` under data/raw/.

    `refresh` refetches the endpoints that GROW. That is not merely a staleness
    nicety: a cached page also freezes the `total` that pagination reads, so rows
    added since the first fetch are unreachable -- the loop stops before the page
    that holds them and never requests it. A driver who debuts after the reference
    JSON was landed stays invisible, and the loaders then drop their results for an
    unresolvable FK.

    Which endpoints grow:
      * the four reference endpoints -- always, a debut can happen any week;
      * the in-progress season -- it gains a race roughly fortnightly.
    A finished season is immutable, so its cached pages stay correct forever and
    refetching them would be pure waste (and 100+ needless requests).
    """
    for path, cache_key in REFERENCE:
        client.land(path, cache_key, refresh=refresh)

    for season in seasons:
        live = refresh and season == config.SEASON_END
        for path, cache_key in SEASONAL:
            client.land(path.format(season=season),
                        cache_key.format(season=season),
                        refresh=live)
