"""Warehouse access for the dashboard. The only module here that talks to Postgres.

Two caching decorators, and getting them the right way round matters. Streamlit
re-runs the entire script on every widget interaction, so without caching each
filter change would re-open a connection and re-query:

    @st.cache_resource  -- the engine. One connection pool for the app's lifetime.
                           A resource is shared, not copied.
    @st.cache_data      -- the results. Cached per argument, with a TTL, and each
                           caller gets its own copy so a mutation cannot leak
                           between reruns.

Every function issues SELECT * FROM v_<name> and nothing else. All aggregation
lives in sql/analytics/001_views.sql; the pages filter the returned DataFrame in
pandas. That is affordable because the views are small (33 to 13,006 rows) and it
means one cached query serves every filter combination -- see the measurement in
sql/analytics/002_indexes.sql, where indexes did nothing for the views precisely
because a view reads every row anyway. The dashboard's speed comes from here.

The connection is READ-ONLY, enforced by the server rather than by convention:
default_transaction_read_only makes Postgres itself refuse a write.
"""
import pathlib
import sys

import pandas as pd
import streamlit as st
from sqlalchemy import URL, create_engine, text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from etl import config  # noqa: E402

# The six views in sql/analytics/001_views.sql. Named here so a typo is a KeyError
# at import rather than a SQL error in front of an audience.
VIEWS = (
    "v_season_kpis",
    "v_constructor_season",
    "v_championship_progression",
    "v_driver_rolling_form",
    "v_reliability_trend",
    "v_quali_vs_race",
    "v_driver_race_craft",
    "v_driver_season",
)


@st.cache_resource
def get_engine():
    """One pooled engine for the app's lifetime.

    Reuses etl.config.dw_dsn() so the dashboard adds no second place that reads
    the environment -- config.py stays the sole os.environ reader in the repo.

    pool_pre_ping tests a pooled connection before handing it out. Without it, a
    connection that went stale (Postgres restarted, the demo truncated and
    reloaded f1_dw) would surface as an error on the next rerun and keep failing
    until the cache was cleared.
    """
    dsn = config.dw_dsn()
    url = URL.create(
        "postgresql+psycopg2",
        username=dsn["user"],
        password=dsn["password"],   # URL.create escapes this; f-string building would not
        host=dsn["host"],
        port=int(dsn["port"]),
        database=dsn["dbname"],
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        # Read-only enforced by the server. The dashboard cannot write to f1_dw
        # even if a future edit tried to: Postgres raises "cannot execute INSERT
        # in a read-only transaction".
        connect_args={"options": "-c default_transaction_read_only=on"},
    )


@st.cache_data(ttl=600)
def load_view(view_name: str) -> pd.DataFrame:
    """SELECT * FROM one analytics view.

    ttl=600 so that a pipeline run during a demo becomes visible within ten
    minutes without restarting the app.
    """
    if view_name not in VIEWS:
        raise KeyError(f"{view_name} is not an analytics view; expected one of {VIEWS}")
    with get_engine().connect() as conn:
        df = pd.read_sql(text(f"SELECT * FROM {view_name}"), conn)

    # Reshaping only, not transformation: psycopg2 returns DATE as datetime.date
    # objects, which land in an object column and give Altair a categorical axis
    # instead of a time axis. Nothing here changes a value.
    for column in df.columns:
        if column.endswith("_date"):
            df[column] = pd.to_datetime(df[column])
    return df


# Thin named accessors. The pages import these rather than passing view-name
# strings around, so a page never mentions a database object.
def season_kpis() -> pd.DataFrame:
    return load_view("v_season_kpis")


def constructor_season() -> pd.DataFrame:
    return load_view("v_constructor_season")


def championship_progression() -> pd.DataFrame:
    return load_view("v_championship_progression")


def driver_rolling_form() -> pd.DataFrame:
    return load_view("v_driver_rolling_form")


def reliability_trend() -> pd.DataFrame:
    return load_view("v_reliability_trend")


def quali_vs_race() -> pd.DataFrame:
    """The raw two-fact join. Kept loadable for ad-hoc inspection; the dashboard
    plots v_driver_race_craft, which is built on top of it."""
    return load_view("v_quali_vs_race")


def driver_race_craft() -> pd.DataFrame:
    return load_view("v_driver_race_craft")


def driver_season() -> pd.DataFrame:
    return load_view("v_driver_season")
