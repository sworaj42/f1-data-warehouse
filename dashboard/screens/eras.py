"""Page 2 -- across all 33 seasons.

Where page 1 asks "what happened in this season?", this page asks the questions
that only 33 seasons of loaded history can answer. Both figures here are the
argument for keeping the OLTP faithful back to 1994 rather than truncating it to
a comparable modern window.
"""
import pathlib
import sys

import streamlit as st

# app.py already puts dashboard/ on the path, but repeating it here keeps this
# screen runnable on its own -- which is what makes it testable with AppTest.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import db                                          # noqa: E402
from charts import reliability, rolling_form       # noqa: E402

st.title("Eras & Form")

kpi_df = db.season_kpis()
lo, hi = int(kpi_df["season"].min()), int(kpi_df["season"].max())
season_range = st.sidebar.slider("Seasons", lo, hi, (lo, hi))

st.subheader("Reliability trend")
reliability.render(db.reliability_trend(), season_range)

st.divider()

st.subheader("Driver rolling form")
form_df = db.driver_rolling_form()

# Offer the drivers with the most starts first: a multiselect over all 177
# participating drivers, alphabetical, is unusable.
by_starts = form_df["driver_name"].value_counts().index.tolist()
drivers = st.sidebar.multiselect(
    "Drivers", by_starts, default=by_starts[:3],
    help="Ordered by career starts within 1994-2026.",
)

if drivers:
    rolling_form.render(form_df, drivers, season_range)
else:
    st.info("Pick at least one driver in the sidebar.")
