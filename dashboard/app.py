"""Entry point: theme, navigation, and the standing context every page shares.

NAVIGATION IS IN THE SIDEBAR, which is where a Streamlit reader looks for it, and the sidebar
doubles as the filter rail. An earlier version of this dashboard put the nav across the top to
reclaim ~260px of chart width, because every page had to fit one viewport with no scrolling. That
constraint is gone -- the pages scroll now -- and with it the reason to fight the framework. What
the constraint had actually cost was legibility: figures were squeezed to 185px, twenty bars had
to be cut to twelve, and the axis labels Vega dropped at those heights were dropped silently.

st.navigation over an explicit screens/ list rather than pages/ auto-discovery, so the pages can
be titled properly and the directory is not mistaken for a list of SQL views.

db.py is the only module in the package that talks to Postgres, and the connection it opens is
read-only at the SERVER, not by convention: an INSERT from here raises "cannot execute INSERT in a
read-only transaction".
"""
import pathlib
import sys

import streamlit as st

# Lets screens/ and charts/ import `db`, `theme` and `charts.*` by name.
BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import theme  # noqa: E402  (must follow the sys.path insert above)

st.set_page_config(
    page_title="F1 Data Warehouse",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.apply()

pages = [
    st.Page("screens/season.py", title="Season report", icon=":material/flag:", default=True),
    st.Page("screens/drivers.py", title="Driver performance", icon=":material/speed:"),
    st.Page("screens/eras.py", title="Eras & trends", icon=":material/timeline:"),
]

with st.sidebar:
    st.markdown("### 🏁 F1 Data Warehouse")
    st.caption("1994–2026 · star schema on PostgreSQL")

nav = st.navigation(pages, position="sidebar")

# nav.run() executes the selected page, and that is when the page appends ITS filters to the
# sidebar. So the provenance block below has to come after it, or the footer would render above
# the controls it sits under.
nav.run()

with st.sidebar:
    st.divider()
    # Provenance, permanently on screen. A dashboard that does not say what it is reading is a
    # dashboard nobody can check.
    st.caption(
        "**Source** `f1_dw` — 6 conformed dimensions, 2 fact tables, 13,028 race results and "
        "11,205 qualifying rows across 33 seasons.\n\n"
        "**Every number** on every page is computed by a view in `sql/analytics/001_views.sql`. "
        "The dashboard issues `SELECT * FROM v_<name>` and nothing else — no SQL in the pages, "
        "no aggregation in pandas.\n\n"
        "**Connection** is read-only, enforced by Postgres."
    )
