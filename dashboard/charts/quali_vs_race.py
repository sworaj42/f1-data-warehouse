"""Qualifying position against race finish -- the chart that needs two fact tables.

v_quali_vs_race joins fact_race_result to fact_qualifying on (race_key,
driver_key), their shared grain, reaching four conformed dimensions on the way.
This is the concrete payoff of the fact-constellation design: a single merged
fact table could only answer it with a self-join over twice the rows.

The diagonal is the whole point of the chart. A driver on the line finished
where they qualified; below it they gained places on Sunday, above it they lost
them.
"""
import altair as alt
import streamlit as st


def render(quali_vs_race, season):
    season_df = quali_vs_race[quali_vs_race["season"] == season]
    # DNFs have no finish_position, so they cannot be placed on this axis at all.
    # Dropping them is stated in the caption rather than done silently.
    classified = season_df[season_df["finish_position"].notna()]

    points = (
        alt.Chart(classified)
        .mark_circle(size=55, opacity=0.6)
        .encode(
            # Both axes reversed: position 1 is the best result, so it belongs at
            # the top-left rather than the origin.
            x=alt.X("quali_position:Q", title="Qualifying position",
                    scale=alt.Scale(reverse=True, zero=False)),
            y=alt.Y("finish_position:Q", title="Race finish",
                    scale=alt.Scale(reverse=True, zero=False)),
            color=alt.Color("constructor_name:N", title="Team"),
            tooltip=[
                alt.Tooltip("race_name:N", title="Race"),
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("constructor_name:N", title="Team"),
                alt.Tooltip("quali_position:Q", title="Qualified"),
                alt.Tooltip("grid_position:Q", title="Started"),
                alt.Tooltip("grid_penalty:Q", title="Grid penalty"),
                alt.Tooltip("finish_position:Q", title="Finished"),
                alt.Tooltip("positions_gained:Q", title="Places gained"),
            ],
        )
    )

    # y = x, drawn from the data's own range so it lines up whatever the field size.
    limit = int(max(classified["quali_position"].max(), classified["finish_position"].max()))
    diagonal = (
        alt.Chart(alt.Data(values=[{"p": 1}, {"p": limit}]))
        .mark_line(strokeDash=[4, 4], color="grey", opacity=0.7)
        .encode(x=alt.X("p:Q", scale=alt.Scale(reverse=True)),
                y=alt.Y("p:Q", scale=alt.Scale(reverse=True)))
    )

    st.altair_chart((points + diagonal).properties(height=440), width="stretch")

    dropped = len(season_df) - len(classified)
    gained = int((classified["positions_gained"] > 0).sum())
    st.caption(
        f"{len(classified)} classified finishes plotted; {dropped} DNFs excluded "
        "(a retirement has no finishing position). "
        f"{gained} of them gained places relative to their grid slot. "
        "Below the dashed line is a driver who moved forward on Sunday."
    )
