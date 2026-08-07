"""F1 warehouse dashboard -- entry point.

    ./.venv/bin/streamlit run dashboard/app.py

The dashboard is the presentation layer for f1_dw. Its job is to show the
warehouse answers real questions, not to do any data work of its own: it issues
SELECT * FROM v_<name> and nothing else, and every aggregation lives in
sql/analytics/001_views.sql.

Navigation sits along the TOP rather than in a sidebar. The sidebar was measured
at 300px -- 20.8% of a 1440px window -- to hold two widgets and a two-item nav
list, and the charts that most needed the space are horizontal bar charts whose
category labels truncate first. Moving the nav up returns ~260px of width to
every figure. The cost is vertical, which is the scarcer budget here, so the
per-page filters live in a popover that shares a row with the era caption rather
than taking a row of their own.
"""
import pathlib
import sys

import streamlit as st

# Lets screens/ and charts/ import `db`, `layout` and `charts.*` by name.
BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

st.set_page_config(
    page_title="F1 Data Warehouse",
    page_icon="🏁",
    layout="wide",
)

# Our own mark, not the F1 wordmark -- see assets/logo.svg for why.
st.logo(str(BASE / "assets" / "logo.svg"), size="large")

pages = [
    st.Page("screens/season.py", title="Season", icon="🏁", default=True),
    st.Page("screens/eras.py", title="Eras & Form", icon="📈"),
]

# position="hidden": the page switcher is drawn in the page body by
# layout.page_header(), so the heading, filters and tabs read as one block
# rather than the tabs living in Streamlit's own chrome.
st.navigation(pages, position="hidden").run()
