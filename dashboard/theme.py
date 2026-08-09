"""One place that decides what the dashboard looks like: colours, the Altair theme, page CSS.

WHY THE COLOURS ARE FIXED HEX AND NOT A VEGA SCHEME NAME. A named scheme picks hues for
aesthetics; these were picked to survive being read. The eight categorical slots below were run
through a colour-blind separation check against this exact surface (#1a1a19) and pass on all five
gates -- lightness band, chroma floor, deutan/protan/tritan separation of adjacent pairs, plain
normal-vision separation, and 3:1 contrast against the surface. Swapping in `scheme="category10"`
would silently drop that. This also fixes a real bug the old dashboard hit: `redyellowblue` had
assigned RED to "Finished" and BLUE to "Mechanical DNF" -- a correct gradient and exactly backwards
as meaning on a chart about failure.

THREE SCALES, THREE JOBS, and mixing them up is the usual way a dashboard goes wrong:

    SERIES      identity      -- which driver is this line? No order, no magnitude.
    OUTCOME     polarity      -- cool = the car finished, warm = it did not. Diverging, with a
                                 neutral grey where the answer is "neither cleanly".
    POSITION    magnitude     -- one hue, dark = a better finishing position.

SERIES is assigned in FIXED ORDER and never cycled: slot 1 goes to the championship leader, slot 2
to second, and so on. That matters when a filter changes the series count -- dropping the 8th
driver must not repaint the other seven, or a reader who learned "the blue line is Verstappen"
has been misled.
"""
import altair as alt
import streamlit as st

# --- Surfaces and ink ------------------------------------------------------------------------
# Must match .streamlit/config.toml. The palette gates were measured against SURFACE.
PLANE = "#0d0d0d"      # page background
SURFACE = "#1a1a19"    # chart surface -- bordered containers are painted this
INK = "#ffffff"
INK_2 = "#c3c2b7"      # secondary text, in-chart value labels
MUTED = "#898781"      # axis labels, captions
GRID = "#2c2c2a"       # hairline gridline, one shade off the surface
AXIS = "#383835"       # baseline / domain rule

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# --- Categorical: identity -------------------------------------------------------------------
# Eight slots, fixed order. A ninth series is never a generated hue -- every chart here that uses
# SERIES caps its series count at 8 rather than inventing a colour.
SERIES = [
    "#3987e5",  # 1 blue
    "#d95926",  # 2 orange
    "#199e70",  # 3 aqua
    "#c98500",  # 4 yellow
    "#d55181",  # 5 magenta
    "#008300",  # 6 green
    "#9085e9",  # 7 violet
    "#e66767",  # 8 red
]
MAX_SERIES = len(SERIES)

# --- Diverging: outcome polarity -------------------------------------------------------------
# Cool arm = the car came home, warm arm = it did not, neutral grey in between. Used by BOTH the
# reliability trend and the per-driver outcome bars, deliberately: the two charts answer the same
# question at different grains, so they should share a grammar. The grey midpoint is a real
# diverging midpoint and is *supposed* to sit below the categorical chroma floor -- "neither" has
# to read as nothing.
# Three blue steps for the ordinal outcome ramp, spaced by LIGHTNESS rather than by hue -- that
# is the channel colour-blind readers keep, and it is the one that survives an 11px legend swatch.
# A first pass had the top two steps 5 lightness points apart and they were indistinguishable in
# the legend; measured adjacent separation is now 16.4 (normal vision, >=15 floor).
BLUE_DEEP = "#2563c4"
BLUE_MID = "#6ba3ee"
BLUE_LIGHT = "#b7d3f6"
NEUTRAL = "#8b8a84"
RED_LIGHT = "#f0a17f"
RED_DEEP = "#cf3f3f"

# Stack order is severity order, best at the bottom of the stack.
STATUS_ORDER = ["Finished", "Lapped", "Other", "Accident DNF", "Mechanical DNF"]
STATUS_COLORS = ["#2f6fd0", "#8dbdf2", NEUTRAL, RED_LIGHT, RED_DEEP]

OUTCOME_ORDER = ["Win", "Podium", "Points", "Classified", "DNF"]
OUTCOME_COLORS = [BLUE_DEEP, BLUE_MID, BLUE_LIGHT, NEUTRAL, RED_DEEP]

# --- Sequential: magnitude -------------------------------------------------------------------
# One hue, dark -> light. Reversed against finishing position so that DARK = P1: the eye reads
# dark as "more", and in a finishing position "more" is a lower number.
POSITION_RAMP = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]

# --- Semantic pair for signed values ----------------------------------------------------------
GAIN = "#3987e5"   # above expectation
LOSS = "#e66767"   # below expectation


@alt.theme.register("f1_dark", enable=True)
def _f1_dark() -> alt.theme.ThemeConfig:
    """Chart chrome: recessive grid and axes, thin marks, no view border.

    Registered once per server process (Streamlit caches modules in sys.modules). Every chart is
    rendered with `st.altair_chart(..., theme=None)` so Streamlit's own theme does not overwrite
    these -- passing the default "streamlit" theme would re-colour the marks and undo the palette
    validation above.
    """
    return {
        "config": {
            "background": "transparent",
            "font": FONT,
            "view": {"stroke": "transparent"},
            "padding": {"left": 4, "top": 4, "right": 4, "bottom": 4},
            "arc": {"stroke": SURFACE, "strokeWidth": 2},
            "axis": {
                "labelColor": MUTED,
                "labelFontSize": 11,
                "titleColor": MUTED,
                "titleFontSize": 11,
                "titleFontWeight": "normal",
                "titlePadding": 8,
                "domainColor": AXIS,
                "tickColor": AXIS,
                "gridColor": GRID,
                "gridWidth": 1,
                "gridDash": [],          # solid hairlines: a dashed grid reads as a threshold
                "labelFont": FONT,
                "titleFont": FONT,
            },
            "axisY": {"domain": False, "ticks": False, "labelPadding": 6},
            "axisX": {"grid": False},
            "legend": {
                "labelColor": INK_2,
                "labelFontSize": 11,
                "titleColor": MUTED,
                "titleFontSize": 11,
                "titleFontWeight": "normal",
                "labelFont": FONT,
                "titleFont": FONT,
                "symbolType": "square",
                "symbolSize": 90,
                "rowPadding": 5,
                "padding": 4,
            },
            "title": {
                "color": INK,
                "fontSize": 13,
                "fontWeight": 600,
                "anchor": "start",
                "font": FONT,
                "offset": 10,
            },
            "range": {"category": SERIES},
            "line": {"strokeWidth": 2},
            "point": {"size": 60},
            "bar": {"cornerRadiusEnd": 3},   # 4px rounded data-end, baseline stays square
            "text": {"font": FONT, "fontSize": 11, "color": INK_2},
        }
    }


_CSS = f"""
<style>
  /* Container width. Streamlit's default max-width leaves a lot of dead margin on a laptop;
     a dashboard wants the pixels for the charts. */
  .block-container {{ padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1500px; }}

  /* Cards ARE the chart surface -- the palette was validated against this exact hex, so every
     figure has to sit on it rather than on the page plane, which is darker.

     Hooked on the key, not on the DOM shape: st.container(border=True) renders as a plain
     stVerticalBlock with a border, indistinguishable in CSS from the unbordered ones that
     columns and the page body also produce. Streamlit turns key="card_x" into the class
     st-key-card_x, so theme.card() is the only thing this rule can ever match. */
  [class*="st-key-card_"] {{
      background: {SURFACE};
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.07) !important;
      padding: 1rem 1.15rem 0.9rem 1.15rem !important;
  }}

  /* Streamlit's own toolbar. The nav lives in the sidebar, so nothing here is load-bearing --
     unlike an earlier version of this dashboard, where hiding stHeader would have deleted the
     page tabs along with it. */
  [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {{ display: none; }}
  [data-testid="stHeader"] {{ background: transparent; }}

  /* Metric cards: st.metric(border=True) renders its own frame; this only tunes the type so a
     five-card row does not wrap its labels on a 13" screen. */
  [data-testid="stMetric"] {{ background: {SURFACE}; border-radius: 10px; }}
  [data-testid="stMetricLabel"] p {{ font-size: 0.78rem !important; color: {MUTED} !important;
                                     text-transform: uppercase; letter-spacing: 0.04em; }}
  [data-testid="stMetricValue"] {{ font-size: 1.75rem !important; font-weight: 600;
                                   /* proportional figures: tabular-nums makes a standalone
                                      number look loose at display sizes. */
                                   font-variant-numeric: normal; }}
  [data-testid="stMetricDelta"] {{ font-size: 0.8rem !important; }}

  /* Section headings sit close to the chart they title. */
  h3 {{ font-size: 1.02rem !important; font-weight: 600 !important;
        padding-top: 0 !important; margin-bottom: 0.15rem !important; }}
  [data-testid="stCaptionContainer"] p {{ color: {MUTED} !important; font-size: 0.78rem !important;
                                          line-height: 1.35; }}

  /* Sidebar: the filter rail. */
  [data-testid="stSidebar"] {{ border-right: 1px solid rgba(255,255,255,0.07); }}
  [data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem; }}

  /* The multiselect caps its own height and scrolls the overflow, which in a narrow sidebar puts
     one chip per row and clips the last selection through the middle of the word -- it reads as
     a rendering fault, not as a scrollable list. Two rules because the cap is split across two
     elements: the tag container does the scrolling, its parent carries the max-height. There are
     at most eight chips, so letting it grow costs nothing. */
  [data-testid="stSidebar"] [data-testid="stMultiSelectTagsContainer"] {{
      max-height: none !important; overflow: visible !important;
  }}
  [data-testid="stSidebar"] div:has(> [data-testid="stMultiSelectTagsContainer"]) {{
      max-height: none !important;
  }}

  /* Tables inherit the surface so they read as part of the same system as the charts. */
  [data-testid="stDataFrame"] {{ border-radius: 8px; }}
</style>
"""


def apply():
    """Call once, at the top of app.py. Charts import the colour names directly."""
    st.markdown(_CSS, unsafe_allow_html=True)


def card(name: str):
    """A figure card: bordered, painted with SURFACE, keyed so the CSS above can find it.

    Use as `with theme.card("championship"):`. The name only has to be unique on the page.
    """
    return st.container(border=True, key=f"card_{name}")


def section(title: str, caption: str | None = None):
    """A titled block. Every chart on every page goes through here, so the spacing between a
    heading, its caveat line and the figure is decided once instead of per page."""
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)


def chart(figure, key: str | None = None):
    """Render an Altair chart at container width with Streamlit's theme override OFF.

    theme=None is not a detail: the default "streamlit" theme re-colours marks, which would
    replace the validated palette with Streamlit's own and silently undo theme.py.
    """
    st.altair_chart(figure, width="stretch", theme=None, key=key)
