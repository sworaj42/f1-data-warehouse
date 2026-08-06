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

    chart = (
        alt.Chart(plot_df)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=18))
        .encode(
            x=alt.X("round:Q", title="Round", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("cumulative_points:Q", title="Cumulative points"),
            # sort=leaders keeps legend order == championship order.
            color=alt.Color("driver_name:N", title="Driver", sort=leaders),
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
        .properties(height=420)
    )
    st.altair_chart(chart, width="stretch")

    winner = final_totals.index[0]
    margin = final_totals.iloc[0] - final_totals.iloc[1]
    st.caption(
        f"{winner} took the {season} title by {margin:.0f} points. "
        "Totals exclude sprint-race points, which are out of scope — so seasons "
        "from 2021 sit below their official figures while the order is unaffected."
    )
