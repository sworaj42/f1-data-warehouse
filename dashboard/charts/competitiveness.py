"""Is the sport a contest or a procession? Two charts, because there are two measures.

TWO CHARTS AND NOT ONE, deliberately. The natural instinct is to put "share of races won by the
strongest team" (0-100%) and "how many different drivers won" (2-9) on one plot with two y axes.
That chart would be a lie: the alignment of two independent scales is arbitrary, so it invents a
correlation the data never claimed. Two panels sharing an x axis say the same thing honestly.

BOTH MEASURES COUNT WINS, NOT POINTS, and that is what makes them comparable across 33 seasons.
The scoring system changed four times between 1994 and 2026, so a points share means something
different in each era; a race win is a race win. v_season_competitiveness computes the share, with
the per-season denominator from SUM(wins) OVER (PARTITION BY season) -- which works precisely
because every race has exactly one winner.
"""
import altair as alt

import theme

from .reliability import _ticks


def _x(lo, hi, with_title):
    return alt.X("season:Q", title="Season" if with_title else None,
                 scale=alt.Scale(nice=False, domain=[lo - 0.5, hi + 0.5]),
                 axis=alt.Axis(format="d", labelAngle=0, values=_ticks(lo, hi), grid=False))


def dominance(competitiveness, seasons, height=260):
    """Share of the season's races won by its most successful constructor."""
    lo, hi = seasons
    df = competitiveness[
        (competitiveness["season"] >= lo) & (competitiveness["season"] <= hi)
    ]
    if df.empty:
        return None

    base = alt.Chart(df).encode(
        # ORDINAL x here, quantitative x on the line chart beside it, and that difference is the
        # point rather than an inconsistency. A bar needs a band to sit in: on a continuous scale
        # Vega has no band, RelativeBandSize does nothing, and 33 bars render edge to edge as one
        # solid block with no gap between seasons. An ordinal scale gives every season a band and
        # paddingInner puts real space between them. A line has no such need and keeps the
        # continuous axis, which is the honest scale for a year.
        x=alt.X("season:O", title=None,
                scale=alt.Scale(paddingInner=0.25, paddingOuter=0.15),
                axis=alt.Axis(format="d", labelAngle=0, values=_ticks(lo, hi), grid=False)),
        y=alt.Y("top_constructor_win_share_pct:Q", title="Races won by the top team (%)",
                scale=alt.Scale(domain=[0, 100], nice=False),
                axis=alt.Axis(grid=True, tickCount=5, format=".0f")),
        tooltip=[
            alt.Tooltip("season:Q", title="Season", format="d"),
            alt.Tooltip("top_constructor:N", title="Top team"),
            alt.Tooltip("top_constructor_wins:Q", title="Wins"),
            alt.Tooltip("races:Q", title="Races"),
            alt.Tooltip("top_constructor_win_share_pct:Q", title="Share of wins", format=".1f"),
            alt.Tooltip("winning_constructors:Q", title="Teams that won a race"),
        ],
    )

    # One series, one colour. Shading the bars by height would spend the colour channel on
    # information the bar length already carries.
    bars = base.mark_bar(color=theme.SERIES[0], cornerRadiusEnd=2)

    # A 50% reference line turns the chart from "some numbers" into a threshold read: above it,
    # one team won more races than the entire rest of the grid combined. Dashed deliberately --
    # this one IS a threshold, which is exactly what a dashed rule should mean and exactly why
    # the gridlines elsewhere are solid.
    #
    # No text label on the line. It was tried at the left edge and printed muted grey directly
    # over the bars, which is unreadable; there is nowhere inside a full-width bar chart for a
    # label to sit clear of the data. The caption above the figure carries it instead.
    half = alt.Chart(df).mark_rule(color=theme.INK_2, strokeWidth=1,
                                   strokeDash=[4, 3]).encode(y=alt.datum(50))

    return alt.layer(bars, half).properties(height=height)


def winners(season_kpis, competitiveness, seasons, height=260):
    """How many different drivers, and how many different teams, won a race that season."""
    lo, hi = seasons
    kpis = season_kpis[(season_kpis["season"] >= lo) & (season_kpis["season"] <= hi)]
    comp = competitiveness[
        (competitiveness["season"] >= lo) & (competitiveness["season"] <= hi)
    ]
    if kpis.empty:
        return None

    # Two series on ONE scale -- both are plain counts of "how many different X won a race" -- so
    # they belong on the same axis. This is the case a dual axis would have been wrong for, and it
    # is not one: the units are identical.
    merged = kpis[["season", "distinct_winners"]].merge(
        comp[["season", "winning_constructors"]], on="season", how="left"
    ).melt("season", var_name="kind", value_name="count")
    merged["kind"] = merged["kind"].map(
        {"distinct_winners": "Different race winners", "winning_constructors": "Different winning teams"}
    )

    x = _x(lo, hi, with_title=False)
    colour = alt.Color(
        "kind:N", title=None,
        scale=alt.Scale(domain=["Different race winners", "Different winning teams"],
                        range=[theme.SERIES[0], theme.SERIES[1]]),
        legend=alt.Legend(orient="bottom", direction="horizontal", symbolSize=110),
    )
    y = alt.Y("count:Q", title="Distinct winners",
              scale=alt.Scale(domainMin=0, nice=True),
              axis=alt.Axis(grid=True, tickCount=5, format="d"))

    lines = alt.Chart(merged).mark_line(strokeWidth=2, interpolate="monotone").encode(
        x=x, y=y, color=colour,
    )
    points = alt.Chart(merged).mark_point(size=55, filled=True, opacity=1).encode(
        x=x, y=y, color=colour,
        tooltip=[
            alt.Tooltip("season:Q", title="Season", format="d"),
            alt.Tooltip("kind:N", title=None),
            alt.Tooltip("count:Q", title="Count"),
        ],
    )
    return alt.layer(lines, points).properties(height=height)
