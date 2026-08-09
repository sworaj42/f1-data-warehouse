"""Rolling form -- a 5-race moving average of finishing position, per driver.

The window is ROWS BETWEEN 4 PRECEDING AND CURRENT ROW in v_driver_rolling_form, ordered by race
date ACROSS season boundaries: form does not reset on 1 January. The page filters to one season,
so the first few points of a season legitimately carry races from the end of the previous one.

TWO ENCODING DECISIONS THAT CARRY MEANING:

1. The y axis is REVERSED. A finishing position is better when it is smaller, so plotting it
   normally puts the fastest driver at the bottom and every reader misreads the chart once before
   correcting themselves. Reversed, up is good, which is what a "form" chart should mean.

2. Faded points are not decoration. finish_position is NULL for a DNF, so AVG() skips those rows:
   a driver with four retirements in the window has a "5-race average" resting on ONE race. The
   view reports that as races_in_window, and a marker drawn from fewer than 5 classified finishes
   is hollowed out. Without it the number is not wrong, it is merely unfalsifiable.
"""
import altair as alt

import theme


def render(rolling_form, season, drivers, height=380):
    df = rolling_form[
        (rolling_form["season"] == season) & (rolling_form["driver_name"].isin(drivers))
    ].copy()
    if df.empty:
        return None
    df = df.sort_values(["driver_name", "round"])
    df["complete"] = df["races_in_window"] >= 5

    colour = alt.Color(
        "driver_name:N",
        title=None,
        scale=alt.Scale(domain=drivers, range=theme.SERIES[: len(drivers)]),
        legend=alt.Legend(orient="right", labelLimit=140, symbolType="stroke",
                          symbolStrokeWidth=3),
    )
    x = alt.X("round:Q", title="Round", scale=alt.Scale(nice=False, padding=6),
              axis=alt.Axis(tickMinStep=1, format="d"))
    y = alt.Y(
        "rolling_avg_finish:Q",
        title="5-race average finish",
        # reverse=True, not a negated field: the axis labels stay the real positions.
        scale=alt.Scale(reverse=True, nice=True, zero=False),
        axis=alt.Axis(grid=True, tickCount=6),
    )

    tooltip = [
        alt.Tooltip("driver_name:N", title="Driver"),
        alt.Tooltip("race_name:N", title="Grand Prix"),
        alt.Tooltip("rolling_avg_finish:Q", title="5-race avg finish", format=".2f"),
        alt.Tooltip("races_in_window:Q", title="Classified finishes in window"),
        alt.Tooltip("finish_position:Q", title="This race"),
        alt.Tooltip("rolling_points_5:Q", title="Points in window", format=".0f"),
    ]

    lines = alt.Chart(df).mark_line(strokeWidth=2, interpolate="monotone").encode(
        x=x, y=y, color=colour,
    )

    # >=8px markers, with a surface-coloured ring so two lines crossing stay separable.
    points = alt.Chart(df).mark_point(size=64, strokeWidth=1.6).encode(
        x=x, y=y, color=colour,
        # Filled = the window is a full five classified finishes; hollow = it is not.
        fill=alt.condition(alt.datum.complete, colour, alt.value(theme.SURFACE)),
        tooltip=tooltip,
    )

    return alt.layer(lines, points).properties(height=height)
