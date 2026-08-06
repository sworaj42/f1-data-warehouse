"""Page 1 -- one season at a time.

Note what is absent from this file: any SQL. Every figure below reads a cached
DataFrame from db.py and filters it in pandas. Changing the season selector
issues no query at all, which is why the page responds instantly despite the
warehouse holding 13,006 fact rows.
"""
import pathlib
import sys

import streamlit as st

# app.py already puts dashboard/ on the path, but repeating it here keeps this
# screen runnable on its own -- which is what makes it testable with AppTest.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import db                                                            # noqa: E402
from charts import championship, constructors, kpis, quali_vs_race   # noqa: E402

st.title("Season")

# All four figures on this page are driven by this single control.
kpi_df = db.season_kpis()
seasons = sorted(kpi_df["season"].tolist(), reverse=True)
season = st.sidebar.selectbox("Season", seasons, index=0)
top_n = st.sidebar.slider("Drivers on the championship chart", 3, 15, 8)

kpis.render(kpi_df, season)

st.subheader("Championship progression")
championship.render(db.championship_progression(), season, top_n=top_n)

left, right = st.columns(2)
with left:
    st.subheader("Constructor standing")
    constructors.render(db.constructor_season(), season)
with right:
    st.subheader("Qualifying vs race")
    quali_vs_race.render(db.quali_vs_race(), season)
