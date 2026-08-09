"""Constructor standings for one season -- a plain ranked bar.

ONE SERIES, ONE COLOUR. The obvious temptation is to shade each bar darker where it is bigger, or
to give every team its own hue. Both are wrong here: a value-ramp on nominal categories
double-encodes bar length as lightness, spending the only free channel on information the bar
already shows, and ten team hues on one chart was measured on the previous version of this
dashboard as "a legend of indistinguishable blues". The bar length is the encoding. The colour is
just ink.

Points, not wins, because within ONE season the scoring system is constant, so points are the
finer-grained measure and the ordering is the real championship ordering. Across seasons they are
not comparable at all -- the scoring system changed four times in 1994-2026 -- which is why the
era caption sits above this chart and why the 33-season charts on the Eras page count wins instead.
"""
import altair as alt

import theme


def render(constructor_season, season, height=None):
    df = constructor_season[constructor_season["season"] == season].copy()
    if df.empty:
        return None
    df = df.sort_values("points", ascending=False)

    # 26px a bar keeps every team name on its own line with room to breathe; below about 20px
    # Vega starts dropping axis labels, which is how a "tidy" fixed height silently hides teams.
    height = height or max(220, 26 * len(df) + 30)

    base = alt.Chart(df).encode(
        y=alt.Y("constructor_name:N", title=None, sort=None,
                axis=alt.Axis(labelLimit=190, labelFontSize=12)),
        x=alt.X("points:Q", title="Points",
                scale=alt.Scale(domain=[0, float(df["points"].max()) * 1.16], nice=False),
                axis=alt.Axis(grid=True, tickCount=5)),
        tooltip=[
            alt.Tooltip("constructor_name:N", title="Constructor"),
            alt.Tooltip("points:Q", title="Points", format=".0f"),
            alt.Tooltip("wins:Q", title="Wins"),
            alt.Tooltip("podiums:Q", title="Podiums"),
            alt.Tooltip("dnfs:Q", title="DNFs"),
            alt.Tooltip("entries:Q", title="Car entries"),
        ],
    )

    bars = base.mark_bar(color=theme.SERIES[0], height=alt.RelativeBandSize(0.62),
                         cornerRadiusEnd=3)

    # Value at the bar end rather than inside it: an in-bar label is clipped by the short bars at
    # the bottom of the table, which is where the small teams live.
    labels = base.mark_text(align="left", dx=6, color=theme.INK_2, fontSize=11).encode(
        text=alt.Text("points:Q", format=".0f"),
    )

    return alt.layer(bars, labels).properties(height=height)
