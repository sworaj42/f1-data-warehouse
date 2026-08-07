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
CHAMPIONSHIP_HEIGHT = 230
ROW2_HEIGHT = 215         # 160 dropped most bar labels; the top bar freed the room
FULL_WIDTH_HEIGHT = 300   # page 2: two stacked charts, no KPI row to make room for

_CSS = """
<style>
  /* Do NOT hide stHeader. An earlier version did, because the header is fixed and
     overlays content, and the default 6rem top padding exists to clear it rather
     than to look airy -- shrinking that padding alone slides the KPI row under the
     toolbar where it is silently clipped (the DOM still reports the labels visible;
     only a zoomed screenshot showed it). But st.navigation(position="top") renders
     the page tabs INSIDE stHeader, so hiding it deletes the navigation itself.
     Instead: keep the header, and just trim its padding and the block padding. */
     The header measures 60px with the nav in it, so block padding-top must CLEAR
     that or the first row renders on top of the page tabs -- which looked exactly
     like "the navigation is missing" until the DOM showed the links present at
     y=0-60 with content starting at y=41. 4rem = 64px, just past it. */
  [data-testid="stHeader"] { height: auto !important; }
  .block-container { padding-top: 4rem !important; padding-bottom: 0.25rem !important; }
  /* Tighten the gap between a subheader and the chart under it. */
  .block-container h3 { margin-bottom: 0.1rem !important; padding-top: 0.4rem !important;
                        font-size: 1.15rem !important; }
  /* The metric row is the single densest thing on the page; shrink its label. */
  [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
</style>
"""


def compact():
    """Apply the density tweaks. Call once at the top of each screen."""
    st.markdown(_CSS, unsafe_allow_html=True)
