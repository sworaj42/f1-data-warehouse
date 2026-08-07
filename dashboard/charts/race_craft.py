"""Who actually gains places on Sunday, from v_driver_race_craft.

This replaced a qualifying-vs-race scatter, and the reason is worth keeping. That
chart plotted grid position against finish position for every driver in a season.
It looked informative and was very nearly meaningless, because places gained by
grid slot is monotonic by arithmetic -- averaged over 2020-2026:

    qualified P1 -> -1.2      qualified P10 -> +0.3      qualified P20 -> +5.3

Pole cannot gain a place; last cannot lose one. So the scatter's dominant shape was
that constraint, and a raw places-gained ranking mostly sorts drivers by how slow
their car is over one lap.

Subtracting par for the grid slot removes it. What remains is the part the driver
and team own -- and it genuinely reorders the field, which is the test that it is
doing something: Perez 2026 drops from +4.14 raw to +0.49 adjusted, while Hamilton
rises to the top at +1.76 despite starting from slots that normally lose places.
"""
import altair as alt
import pandas as pd
import streamlit as st

import layout

# Below this, one wet race or one first-lap accident swings a driver's average
# far enough to top the chart on noise alone.
MIN_RACES = 5

# Show the best and worst N rather than the whole field. Twenty bars in the height
# this layout allows makes Vega drop most of the axis labels, so two thirds of the
# chart becomes unattributable -- and the drivers in the middle are, by definition,
# the ones with nothing to say. Measured: at 195px, ~6 of 20 labels survive.
EXTREMES = 6


def render(race_craft, season):
    season_df = race_craft[
        (race_craft["season"] == season) & (race_craft["races"] >= MIN_RACES)
    ]

    if season_df.empty:
        st.info(f"No driver has completed {MIN_RACES} races in {season} yet.")
        return

    ranked = season_df.sort_values("places_vs_expected", ascending=False)
    if len(ranked) > 2 * EXTREMES:
        ranked = pd.concat([ranked.head(EXTREMES), ranked.tail(EXTREMES)])
    season_df = ranked
    order = ranked["driver_name"].tolist()

    bars = (
        alt.Chart(season_df)
        .mark_bar()
        .encode(
            x=alt.X("places_vs_expected:Q", title="Places gained vs. par for their grid"),
            y=alt.Y("driver_name:N", title=None, sort=order),
            # Diverging on the sign: beating par and missing it are opposite claims,
            # so they must not share a colour ramp direction.
            color=alt.Color(
                "places_vs_expected:Q",
                scale=alt.Scale(scheme="redyellowgreen", domainMid=0),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("races:Q", title="Races counted"),
                alt.Tooltip("avg_places_gained:Q", title="Places gained"),
                alt.Tooltip("expected_places_gained:Q", title="Par for their grid"),
                alt.Tooltip("places_vs_expected:Q", title="Above par"),
            ],
        )
    )
    # Par. Everything to the right of it beat the grid slot it started from.
    zero = alt.Chart(season_df).mark_rule(color="grey", strokeDash=[3, 3]).encode(x=alt.datum(0))

    st.altair_chart((bars + zero).properties(height=260), width="stretch")
