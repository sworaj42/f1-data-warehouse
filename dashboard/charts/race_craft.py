"""Race craft: places gained, once you subtract the places the grid slot hands you for free.

WHY THE OBVIOUS CHART IS WORTHLESS, which is the point worth making out loud. Plotting raw places
gained ranks drivers by how slow their car is in qualifying. It cannot do anything else: pole
cannot gain a place and last cannot lose one. Measured on this warehouse, averaged over 2020-2026,
the gain by grid slot is perfectly monotonic -- P1 -1.2, P10 +0.3, P20 +5.3. A scatter of
qualifying against finishing position mostly draws that constraint.

v_driver_race_craft subtracts par for the slot, computed WITHIN the season (field size was 26 in
1994 and 20 now, so P20 is not the same starting point). What is left is the driver's and the
team's share. It reorders the field, which is the test that it does something: Perez in 2026 falls
from +4.14 raw to +0.49 adjusted, while Hamilton -- who qualifies well, so par for his slots is
NEGATIVE -- rises to +1.76 and the top of the field.

THE WHOLE FIELD IS DRAWN, not a top-6. The residuals sum to exactly zero within a season by
construction, so showing every driver makes that visible and self-checking; truncating to the best
few would hide the balancing half. This is affordable now only because the page scrolls -- an
earlier version had 187px for this figure and had to cut to best-and-worst-6 or Vega dropped most
of the axis labels.
"""
import altair as alt

import theme


def render(race_craft, season, height=None):
    df = race_craft[race_craft["season"] == season].copy()
    if df.empty:
        return None
    df = df.sort_values("places_vs_expected", ascending=False)

    height = height or max(240, 24 * len(df) + 40)
    span = float(df["places_vs_expected"].abs().max()) * 1.25

    base = alt.Chart(df).encode(
        y=alt.Y("driver_name:N", title=None, sort=None,
                axis=alt.Axis(labelLimit=170, labelFontSize=11.5)),
        x=alt.X("places_vs_expected:Q", title="Places gained vs par for the grid slot",
                scale=alt.Scale(domain=[-span, span], nice=False),
                axis=alt.Axis(grid=True, tickCount=7, format="+.1f")),
        tooltip=[
            alt.Tooltip("driver_name:N", title="Driver"),
            alt.Tooltip("races:Q", title="Races classified"),
            alt.Tooltip("avg_places_gained:Q", title="Raw places gained", format="+.2f"),
            alt.Tooltip("expected_places_gained:Q", title="Par for those slots", format="+.2f"),
            alt.Tooltip("places_vs_expected:Q", title="Above / below par", format="+.2f"),
        ],
    )

    # Two colours for a signed value -- a diverging pair, warm and cool, so the sign is legible
    # before the axis is read. Not a ramp: the magnitude is already the bar length.
    bars = base.mark_bar(height=alt.RelativeBandSize(0.66), cornerRadiusEnd=3).encode(
        color=alt.condition(
            alt.datum.places_vs_expected >= 0, alt.value(theme.GAIN), alt.value(theme.LOSS)
        ),
    )

    # Label outside the bar end, flipping side with the sign so it never sits on top of its own
    # bar. Two filtered layers rather than one conditional layer: align and dx are mark
    # properties in Vega-Lite, not encoding channels, so they cannot be driven by alt.condition.
    def _labels(positive):
        return (
            base.transform_filter(
                alt.datum.places_vs_expected >= 0 if positive else alt.datum.places_vs_expected < 0
            )
            .mark_text(
                fontSize=10.5, color=theme.INK_2,
                align="left" if positive else "right",
                dx=5 if positive else -5,
            )
            .encode(text=alt.Text("places_vs_expected:Q", format="+.2f"))
        )

    zero = alt.Chart(df).mark_rule(color=theme.AXIS, strokeWidth=1).encode(x=alt.datum(0))

    return alt.layer(zero, bars, _labels(True), _labels(False)).properties(height=height)
