"""Rolling driver form -- a 5-race moving average of finishing position.

rolling_avg_finish comes from v_driver_rolling_form:
    AVG(finish_position) OVER (PARTITION BY driver_key ORDER BY race_date
                               ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)

The window is ordered by date rather than by (season, round), so form carries
across the winter break instead of resetting every January.

The honest caveat, and the reason races_in_window is on the view: finish_position
is NULL for a DNF, so AVG skips it. A driver with four retirements in the window
has a "5-race average" resting on one race. The chart encodes that as opacity
rather than hiding it.
"""
import altair as alt
import streamlit as st

import layout


def render(rolling_form, drivers, season_range):
    lo, hi = season_range
    window = rolling_form[
        rolling_form["driver_name"].isin(drivers)
        & rolling_form["season"].between(lo, hi)
        & rolling_form["rolling_avg_finish"].notna()
    ]

    if window.empty:
        st.info("No races for that combination of drivers and seasons.")
        return

    chart = (
        alt.Chart(window)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("race_date:T", title="Race date"),
            # Reversed: a lower average finishing position is a better one, so up
            # has to mean improving or the chart reads backwards.
            y=alt.Y("rolling_avg_finish:Q", title="5-race average finish (better ↑)",
                    scale=alt.Scale(reverse=True, zero=False)),
            color=alt.Color("driver_name:N", title="Driver"),
            # Fades where the average rests on fewer than five classified races.
            opacity=alt.Opacity("races_in_window:Q", title="Races in window",
                                scale=alt.Scale(domain=[1, 5], range=[0.25, 1]),
                                legend=None),
            tooltip=[
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("race_name:N", title="Race"),
                alt.Tooltip("season:O", title="Season"),
                alt.Tooltip("finish_position:Q", title="Finished"),
                alt.Tooltip("rolling_avg_finish:Q", title="5-race average"),
                alt.Tooltip("races_in_window:Q", title="Classified in window"),
            ],
        )
        .properties(height=layout.FULL_WIDTH_HEIGHT)
    )
    st.altair_chart(chart, width="stretch")
