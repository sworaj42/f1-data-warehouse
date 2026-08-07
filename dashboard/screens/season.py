"""Page 1 -- one season at a time.

Note what is absent from this file: any SQL. Every figure reads a cached DataFrame
from db.py and filters it in pandas, so changing the season issues no query at all.

Also absent: st.title. The sidebar nav already names the page, and the duplicate
heading cost ~80px of the vertical budget this page has to fit inside.

Chart captions live in the `help=` tooltip on each subheader rather than as text
below the chart. The caveats are the most defensible thing on the page so they are
not dropped -- they move one hover away, and buy back ~160px.
"""
import pathlib
import sys

import streamlit as st

# app.py already puts dashboard/ on the path, but repeating it here keeps this
# screen runnable on its own -- which is what makes it testable with AppTest.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import db                                                          # noqa: E402
import layout                                                      # noqa: E402
from charts import championship, constructors, kpis, race_craft    # noqa: E402

layout.compact()

# Every figure on this page is driven by this single control.
kpi_df = db.season_kpis()
seasons = sorted(kpi_df["season"].tolist(), reverse=True)
season = st.sidebar.selectbox("Season", seasons, index=0)
top_n = st.sidebar.slider("Drivers on the championship chart", 3, 15, 8)

kpis.render(kpi_df, season)

st.subheader(
    "Championship progression",
    help="Cumulative points by round, from a SUM() OVER (PARTITION BY season, driver "
         "ORDER BY round) window function in v_championship_progression. Totals exclude "
         "sprint-race points, which are out of scope -- so seasons from 2021 sit below "
         "their official figures, though the ordering is unaffected.",
)
championship.render(db.championship_progression(), season, top_n=top_n)

left, right = st.columns(2)
with left:
    st.subheader(
        "Constructor standing",
        help="Points summed within a single season, so the scoring-era problem does not "
             "arise -- every team here scored under the same rules. Bar colour is wins.",
    )
    constructors.render(db.constructor_season(), season)
with right:
    st.subheader(
        "Race craft",
        help="Places gained relative to PAR for the grid slot they started from. A driver "
             "qualifying 20th gains ~5 places a race simply because they cannot lose any, "
             "so raw places-gained mostly ranks cars by qualifying pace. Subtracting par "
             "leaves the part the driver and team own. Minimum 5 races.",
    )
    race_craft.render(db.driver_race_craft(), season)
