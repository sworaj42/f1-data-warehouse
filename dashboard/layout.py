"""Shared layout tuning, so both screens fit a laptop viewport without scrolling.

Streamlit ships a ~6rem top padding on the main block, which is generous for a
document and expensive for a dashboard: it is roughly 90px of nothing above the
first KPI card. Reclaiming it, plus dropping the per-page st.title that duplicates
the sidebar nav label, is most of the difference between "scrolls" and "fits".

These numbers are MEASURED in the browser, not estimated. The first attempt was
estimated and was wrong by 257px, almost all of it in one place: st.metric with
border=True and a sparkline renders a 188px row, not the ~85px a plain metric row
takes. Measuring is why the sparklines are gone.

Measured budget for page 1 (1440x729 viewport, Chrome):

    top padding             8
    KPI row (plain)        85
    era caption            25
    subheader + chart      35 + CHAMPIONSHIP_HEIGHT
    subheader + 2 charts   35 + ROW2_HEIGHT
    bottom padding         16
    ---------------------------
    total                ~660px against a 729px viewport

Verify with, in the browser console:

    document.querySelector('.block-container').getBoundingClientRect().height

If it scrolls on the presenting machine, drop ROW2_HEIGHT first -- the lower two
charts carry less detail than the championship line.
"""
import streamlit as st

# Tuned against a MEASURED 785px viewport (window.innerHeight), leaving ~10px spare.
# CHAMPIONSHIP_HEIGHT is not free to shrink: a right-hand legend needs ~28px per
# driver, so at 8 drivers it needs >=224px or Vega silently truncates the list.
# That truncation is what pushed an earlier version to direct line labels, which
# then overlapped badly whenever drivers were close on points. Height solves both.
CHAMPIONSHIP_HEIGHT = 256
ROW2_HEIGHT = 185         # 160 dropped most bar labels; the top bar freed the room
FULL_WIDTH_HEIGHT = 302   # page 2: two stacked charts, no KPI row to make room for

# The two screens, in nav order. Kept here so the switcher and app.py agree.
PAGES = {"Season": "screens/season.py", "Eras & Form": "screens/eras.py"}

_CSS = """
<style>
  /* Do NOT hide stHeader. An earlier version did, because the header is fixed and
     overlays content, and the default 6rem top padding exists to clear it rather
     than to look airy -- shrinking that padding alone slides the KPI row under the
     toolbar where it is silently clipped (the DOM still reports the labels visible;
     only a zoomed screenshot showed it). But st.navigation(position="top") renders
     the page tabs INSIDE stHeader, so hiding it deletes the navigation itself.
     Hiding it is safe ONLY because the page switcher now lives in the page body
     (layout.page_header) and app.py routes with position="hidden", so no
     navigation is lost. That reclaims the 4rem of clearance the header needed --
     which is the 31px that stood between this layout and fitting. If the nav ever
     moves back into the header, this rule has to go with it. */
  [data-testid="stHeader"] { display: none !important; }
  .block-container { padding-top: 1rem !important; padding-bottom: 0.25rem !important; }
  /* Tighten the gap between a subheader and the chart under it. */
  .block-container h3 { margin-bottom: 0.1rem !important; padding-top: 0.4rem !important;
                        font-size: 1.15rem !important; }
  /* The metric row is the single densest thing on the page; shrink its label. */
  [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.6rem !important; }

  /* Minimal borders. Applied via CSS rather than st.metric(border=True) because
     that variant renders a 188px row -- measured -- against the ~62px this layout
     affords. A 1px rule and some padding gives the same separation for ~8px. */
  [data-testid="stMetric"] {
    border: 1px solid rgba(250,250,250,0.14);
    border-radius: 8px;
    padding: 0.4rem 0.7rem;
  }
  /* Heading and page switcher are chrome, not content -- keep them tight. */
  .block-container h2 { margin: 0 !important; padding: 0 !important; font-size: 1.55rem !important; }
  [data-testid="stVegaLiteChart"] {
    border: 1px solid rgba(250,250,250,0.10);
    border-radius: 8px;
    padding: 0.35rem;
  }
</style>
"""


def compact():
    """Apply the density tweaks. Call once at the top of each screen."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(active):
    """Title row, then the page switcher. Returns the column the caller puts filters in.

    The switcher is drawn in the page body rather than left to
    st.navigation(position="top") so the heading, the filters and the page tabs
    read as one control block instead of the tabs living in Streamlit's chrome.
    app.py therefore routes with position="hidden".
    """
    title_col, filter_col = st.columns([4, 1], vertical_alignment="center")
    title_col.markdown("## 🏁 F1 Data Warehouse")

    choice = st.segmented_control(
        "Page", list(PAGES), default=active, label_visibility="collapsed", key="_nav",
    )
    # segmented_control returns None if the user clicks the already-active option,
    # so guard on both None and no-change or the app reruns into itself.
    if choice and choice != active:
        st.switch_page(PAGES[choice])

    return filter_col
