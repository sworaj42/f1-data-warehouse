"""How every car in the field ended its race, every season from 1994 -- the project's headline.

The finding this draws: the 1990s field failed to finish 46% of the time and the 2020s field 13%.
That is not a subtle trend, it is the single largest change in the data, and a 100% stacked area
is the right form for it because the question is about SHARE -- what proportion of results were
each kind of ending -- and the parts genuinely make a whole.

COLOUR IS DIVERGING AND IT IS LOAD-BEARING. Cool = the car came home, warm = it did not, neutral
grey where it is neither cleanly (a disqualification, a withdrawal, a driver who never started).
An earlier version used the `redyellowblue` scheme, which assigned RED to "Finished" and BLUE to
"Mechanical DNF": a perfectly correct gradient and exactly backwards as meaning, on a chart whose
entire subject is failure. Named schemes cannot know which end of a scale is the bad end.

The five groups come from dim_status.status_group, which collapses 109 distinct source status
strings at load time. Plotting the raw statuses would need 109 colours, which is not a chart.

STACK ORDER PUTS THE RETIREMENTS ON THE BASELINE, with "Finished" against the top edge. A stacked
band is only easy to read against a flat edge, and the quantity this chart exists to show is the
retirement share -- so that is the one that gets the baseline.

THE 2023 ANNOTATION IS NOT DECORATION, and leaving it off would make the chart lie. From 2023 the
source stops reporting WHY a car retired and returns a generic "Retired", which this warehouse
groups under "Other". Measured: 73 results carried a cause in 2022 and 0 did in 2024, while
generic retirements went from 0 to 49. So the mechanical and accident bands do not shrink to
nothing after 2023 because cars stopped breaking -- they shrink because the reporting changed.
The TOTAL retirement share is still sound across the break; only the split into causes is not.
"""
import altair as alt

import theme

# The season the source stopped reporting a cause of retirement. Verified against the fact:
# generic "Retired" rows by season run 0 (2022) -> 53 (2023) -> 49 (2024), while rows carrying a
# mechanical or accident cause run 73 -> 6 -> 0.
CAUSE_REPORTING_BREAK = 2023


def render(reliability_trend, seasons, height=380):
    lo, hi = seasons
    df = reliability_trend[
        (reliability_trend["season"] >= lo) & (reliability_trend["season"] <= hi)
    ]
    if df.empty:
        return None
    # A view has no guaranteed row order. An area mark joins its points along the x axis, but
    # sorting here makes that independent of whatever order the query planner happens to return.
    df = df.sort_values(["status_group", "season"])

    area = (
        alt.Chart(df)
        .mark_area(
            # Linear, NOT monotone. A smoothed stacked area overshoots between points, which on a
            # share chart draws percentages that are not in the data.
            interpolate="linear",
            # A hairline in the surface colour separates adjacent bands without drawing a border
            # around each one.
            stroke=theme.SURFACE,
            strokeWidth=0.8,
        )
        .encode(
            x=alt.X("season:Q", title=None, scale=alt.Scale(nice=False, domain=[lo, hi]),
                    axis=alt.Axis(format="d", tickMinStep=1, labelAngle=0, values=_ticks(lo, hi))),
            # pct_of_season already sums to 100 within a season -- the view divides by a
            # per-season denominator computed in the same pass -- so this stacks at zero rather
            # than re-normalising something that is already a share.
            y=alt.Y("pct_of_season:Q", title="Share of all results (%)", stack="zero",
                    scale=alt.Scale(domain=[0, 100], nice=False),
                    axis=alt.Axis(grid=True, tickCount=5, format=".0f")),
            color=alt.Color("status_group:N", title=None,
                            scale=alt.Scale(domain=theme.STATUS_ORDER,
                                            range=theme.STATUS_COLORS),
                            legend=alt.Legend(orient="bottom", direction="horizontal", columns=5,
                                              symbolSize=110)),
            # NO order channel here, and that is not an omission. On an AREA mark the `order`
            # channel sets the order in which points are joined into the path, not just the stack
            # order -- so adding it made every band zigzag across the plot instead of following
            # the season axis. The stack order comes from the colour scale's explicit domain
            # (STATUS_ORDER), which is where it belongs. On a BAR mark, order is safe and the
            # outcome chart on the season page does use it.
            tooltip=[
                alt.Tooltip("season:Q", title="Season", format="d"),
                alt.Tooltip("status_group:N", title="Outcome"),
                alt.Tooltip("pct_of_season:Q", title="Share of results", format=".1f"),
                alt.Tooltip("status_rows:Q", title="Results"),
                alt.Tooltip("season_rows:Q", title="Results that season"),
            ],
        )
        .properties(height=height)
    )

    # Only annotate the break if the selected range actually crosses it -- a marker for something
    # off the edge of the plot is noise.
    if not (lo < CAUSE_REPORTING_BREAK <= hi):
        return area

    mark_df = df.head(1)
    rule = alt.Chart(mark_df).mark_rule(
        color=theme.INK_2, strokeWidth=1, strokeDash=[4, 3],
    ).encode(x=alt.datum(CAUSE_REPORTING_BREAK))
    label = alt.Chart(mark_df).mark_text(
        text="source stops reporting a cause", align="right", baseline="top",
        dx=-6, dy=2, fontSize=10, color=theme.INK_2,
    ).encode(x=alt.datum(CAUSE_REPORTING_BREAK), y=alt.datum(100))

    return alt.layer(area, rule, label).properties(height=height)


def _ticks(lo, hi):
    """A tick every other season at most, so 33 four-digit labels never collide."""
    step = 1 if hi - lo <= 12 else (2 if hi - lo <= 24 else 4)
    return list(range(int(lo), int(hi) + 1, step))
