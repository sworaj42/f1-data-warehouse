"""Championship progression -- the centrepiece chart.

Driven entirely by cumulative_points from v_championship_progression, which is a
SUM() OVER (PARTITION BY season, driver ORDER BY round) window function. Open
that view's SQL when presenting this: the chart is a line plot, the analytics is
the window clause.

Nothing is aggregated here. The view already carries a running total per driver
per round; this module filters to one season and the leading drivers, and draws.
"""
import altair as alt
import streamlit as st

import layout


def render(progression, season, top_n=8):
    season_df = progression[progression["season"] == season]

    # Rank by each driver's final cumulative total, so the legend is ordered by
    # championship position rather than alphabetically.
    final_totals = (
        season_df.sort_values("round")
        .groupby("driver_name")["cumulative_points"]
        .last()
        .sort_values(ascending=False)
    )
    leaders = final_totals.head(top_n).index.tolist()
    plot_df = season_df[season_df["driver_name"].isin(leaders)]

    last_round = int(plot_df["round"].max())
    # Room on the right for the direct labels. Extending the domain rather than
    # shrinking the plot keeps every pixel of height for the lines.
    x_scale = alt.Scale(domain=[1, last_round + max(2, last_round * 0.28)], nice=False)
    colour = alt.Color("driver_name:N", sort=leaders, legend=None)

    base = alt.Chart(plot_df).encode(
        x=alt.X("round:Q", title="Round", axis=alt.Axis(tickMinStep=1), scale=x_scale),
        y=alt.Y("cumulative_points:Q", title="Points"),
        color=colour,
    )

    lines = base.mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=16)).encode(
        tooltip=[
            alt.Tooltip("season_round_label:N", title="Race"),
            alt.Tooltip("race_name:N", title=""),
            alt.Tooltip("driver_name:N", title="Driver"),
            alt.Tooltip("constructor_name:N", title="Team"),
            alt.Tooltip("points:Q", title="Points this race"),
            alt.Tooltip("cumulative_points:Q", title="Running total"),
            alt.Tooltip("championship_position:Q", title="Position after"),
        ],
    )

    # Direct labels instead of a legend. A legend costs vertical space this layout
    # does not have -- on the right it silently truncated at six drivers, and below
    # the plot it collapsed the plotting area to ~50px. Labelling the end of each
    # line costs nothing vertically, and removes the colour-matching step entirely.
    tips = plot_df.sort_values("round").groupby("driver_name", as_index=False).tail(1)
    labels = (
        alt.Chart(tips)
        .mark_text(align="left", dx=6, fontSize=10, fontWeight="bold")
        .encode(
            x=alt.X("round:Q", scale=x_scale),
            y=alt.Y("cumulative_points:Q"),
            text=alt.Text("driver_name:N"),
            color=colour,
        )
    )

    st.altair_chart(
        (lines + labels).properties(height=layout.CHAMPIONSHIP_HEIGHT),
        width="stretch",
    )
