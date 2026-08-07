"""Page 2 -- across all 33 seasons.

Where page 1 asks "what happened in this season?", this page asks the questions
that only 33 seasons of loaded history can answer. Both figures are the argument
for keeping the OLTP faithful back to 1994 rather than truncating it to a
comparable modern window.

No KPI row here, so each chart gets more height than on page 1.
"""
import pathlib
import sys

import streamlit as st

# app.py already puts dashboard/ on the path, but repeating it here keeps this
# screen runnable on its own -- which is what makes it testable with AppTest.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import db                                        # noqa: E402
import layout                                    # noqa: E402
from charts import reliability, rolling_form     # noqa: E402

layout.compact()
filter_col = layout.page_header("Eras & Form")

kpi_df = db.season_kpis()
lo, hi = int(kpi_df["season"].min()), int(kpi_df["season"].max())
form_df = db.driver_rolling_form()

# Offer the drivers with the most starts first: a multiselect over all 177
# participating drivers, alphabetical, is unusable.
by_starts = form_df["driver_name"].value_counts().index.tolist()

with filter_col.popover("Filters", icon=":material/tune:", width="stretch"):
    season_range = st.slider("Seasons", lo, hi, (lo, hi))
    drivers = st.multiselect(
        "Drivers", by_starts, default=by_starts[:3],
        help="Ordered by career starts within 1994-2026.",
    )
st.caption(
    f"{lo}-{hi} · {len(by_starts)} participating drivers · outcomes counted as status "
    "groups, not points, which is what makes them comparable across eras."
)

st.subheader(
    "Reliability trend",
    help="Share of each status group by season. Readable only because dim_status collapses "
         "109 distinct finishing-status strings into 5 groups at load time. Comparable across "
         "eras because it counts statuses, not points. Runs 1-2 points above the DNF-rate KPI: "
         "that card counts cars with no finishing position, this counts retirements, and a car "
         "retiring after 90% distance is still classified.",
)
reliability.render(db.reliability_trend(), season_range)

st.subheader(
    "Driver rolling form",
    help="Five-race moving average of finishing position, ordered by date so form carries "
         "across the winter break instead of resetting each January. finish_position is NULL "
         "for a DNF and AVG skips it, so windows resting on fewer than five classified races "
         "are drawn faded -- the average is correct, it just carries less evidence.",
)
if drivers:
    rolling_form.render(form_df, drivers, season_range)
else:
    st.info("Pick at least one driver in Filters.")
