"""Championship progression -- the centrepiece figure.

The analytics is not in this file. `cumulative_points` arrives from
v_championship_progression, where it is SUM(points) OVER (PARTITION BY season, driver_key
ORDER BY round) -- one pass over the fact, no self-join. This module filters and draws.

TWO THINGS HERE ARE DELIBERATE AND WERE BOTH ARRIVED AT THE HARD WAY.

1. Eight drivers, hard cap. A right-hand legend needs roughly 28px per entry, so a 9th entry is
   silently dropped by Vega rather than reported. A control that lies about what it did is worse
   than a lower limit, so the page's slider stops at 8 and the palette has exactly 8 slots.

2. No end-of-line driver labels. They were tried and reverted: they overlap badly whenever two
   drivers sit within a few points of each other -- which is precisely the situation in a title
   fight, i.e. exactly when the chart matters. The legend plus a shared hover tooltip carries
   identity instead, and the leader is named in the caption above the figure.

The hover layer pivots IN VEGA (transform_pivot), not in pandas, so one rule shows every driver's
total at that round in one tooltip rather than forcing the reader to hunt along a line.
"""
import altair as alt

import theme


def render(progression, season, drivers, height=400):
    """`drivers` is an ordered list -- championship order -- and doubles as the colour domain.

    Colour is bound to the driver NAME through an explicit domain/range pair, so removing the 8th
    driver with the slider leaves the other seven on the hues they already had. Binding colour to
    row order instead would repaint the survivors on every filter change.
    """
    df = progression[
        (progression["season"] == season) & (progression["driver_name"].isin(drivers))
    ]
    if df.empty:
        return None

    colour = alt.Color(
        "driver_name:N",
        title=None,
        scale=alt.Scale(domain=drivers, range=theme.SERIES[: len(drivers)]),
        legend=alt.Legend(orient="right", labelLimit=140, symbolType="stroke",
                          symbolStrokeWidth=3),
    )
    x = alt.X(
        "round:Q",
        title="Round",
        scale=alt.Scale(nice=False, padding=6),
        axis=alt.Axis(tickMinStep=1, format="d"),
    )

    lines = alt.Chart(df).mark_line(strokeWidth=2, interpolate="linear").encode(
        x=x,
        y=alt.Y("cumulative_points:Q", title="Cumulative points",
                axis=alt.Axis(grid=True, tickCount=6)),
        color=colour,
    )

    # Nearest-round crosshair. `empty=False` so nothing is highlighted until the pointer is
    # actually over the plot, and the rule is bound to round only -- the reader wants the whole
    # field at that round, not the one line they happened to touch.
    hover = alt.selection_point(fields=["round"], nearest=True, on="pointerover",
                                empty=False, clear="pointerout")

    rule = (
        alt.Chart(df)
        .mark_rule(color=theme.MUTED, strokeWidth=1)
        .encode(
            x=x,
            opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
            tooltip=[alt.Tooltip("season_round_label:N", title="Round"),
                     alt.Tooltip("race_name:N", title="Grand Prix")]
            + [alt.Tooltip(f"{name}:Q", title=name, format=".0f") for name in drivers],
        )
        .transform_pivot("driver_name", value="cumulative_points", groupby=["round", "season_round_label", "race_name"])
        .add_params(hover)
    )

    # A dot on the hovered round only. Points on every round would clutter 24 rounds x 8 drivers.
    points = lines.mark_circle(size=70, opacity=1).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
    )

    return (
        alt.layer(lines, points, rule)
        .properties(height=height)
        .resolve_scale(color="shared")
    )
