"""F1 warehouse dashboard -- entry point.

    ./.venv/bin/streamlit run dashboard/app.py

The dashboard is the presentation layer for f1_dw. Its job is to show the
warehouse answers real questions, not to do any data work of its own: it issues
SELECT * FROM v_<name> and nothing else, and every aggregation lives in
sql/analytics/001_views.sql.

Pages are declared explicitly with st.navigation rather than discovered from a
pages/ directory, so they can be named properly and kept in a screens/ directory
that does not read as "SQL views".
"""
import pathlib
import sys

import streamlit as st

# Lets screens/ and charts/ import `db` and `charts.*` by name.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

st.set_page_config(
    page_title="F1 Data Warehouse",
    page_icon="🏁",
    layout="wide",
)

pages = [
    st.Page("screens/season.py", title="Season", icon="🏁", default=True),
    st.Page("screens/eras.py", title="Eras & Form", icon="📈"),
]

st.navigation(pages).run()
