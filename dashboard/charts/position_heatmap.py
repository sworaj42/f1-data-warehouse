"""Every result of the season on one grid: driver down, round across, colour = finishing position.

This is the chart that shows a season's SHAPE -- a band of dark cells across the top row is a
dominant campaign, a scattering of red is a car that kept breaking. A line chart of positions
cannot do it for twenty drivers without becoming spaghetti.

WHY THE NUMBERS ARE IN THE CELLS. Normally a value printed on every mark is clutter. A heatmap is
the exception: with the position written in each cell, this figure IS the table view of the
season, so nothing on the page is encoded in colour alone. That is the accessibility requirement
satisfied by the same object rather than by a second one.

DNFs get their own layer rather than a colour at the end of the ramp. finish_position is NULL for
a retirement, so it has no place on a position scale at all -- painting it "position 21" would
invent a result. It is drawn as a flat warm cell labelled DNF, which is a different KIND of
outcome, not an extreme value of the same one.
"""
import altair as alt

import theme


def render(rolling_form, season, driver_order, height=None):
    df = rolling_form[
        (rolling_form["season"] == season) & (rolling_form["driver_name"].isin(driver_order))
    ].copy()
    if df.empty:
        return None

    finished = df[df["finish_position"].notna()]
    retired = df[df["finish_position"].isna()]

    height = height or max(220, 25 * len(driver_order) + 45)
    rounds = sorted(df["round"].unique())

    y = alt.Y("driver_name:N", title=None, sort=list(driver_order),
              axis=alt.Axis(labelLimit=170, labelFontSize=11.5))
    x = alt.X("round:O", title="Round", sort=rounds,
              axis=alt.Axis(labelAngle=0, labelFontSize=10, orient="top", ticks=False))

    tooltip = [
        alt.Tooltip("driver_name:N", title="Driver"),
        alt.Tooltip("race_name:N", title="Grand Prix"),
        alt.Tooltip("finish_position:Q", title="Finished"),
        alt.Tooltip("points:Q", title="Points", format=".0f"),
    ]

    # Sequential, one hue, reversed: DARK = P1. The eye reads dark as "more", and in a finishing
    # position more is a smaller number, so the ramp has to be inverted or the chart reads
    # backwards. Domain capped at 20 so one 24-car field in the 1990s does not wash out the scale.
    cells = alt.Chart(finished).mark_rect(stroke=theme.SURFACE, strokeWidth=1.5,
                                          cornerRadius=2).encode(
        x=x, y=y,
        color=alt.Color(
            "finish_position:Q",
            title="Finish",
            scale=alt.Scale(range=theme.POSITION_RAMP, domain=[1, 20], clamp=True),
            legend=alt.Legend(orient="bottom", direction="horizontal", gradientLength=170,
                              gradientThickness=10, values=[1, 5, 10, 15, 20]),
        ),
        tooltip=tooltip,
    )

    dnf_cells = alt.Chart(retired).mark_rect(
        color=theme.RED_DEEP, opacity=0.75, stroke=theme.SURFACE, strokeWidth=1.5, cornerRadius=2,
    ).encode(x=x, y=y, tooltip=tooltip)

    # White on the dark end of the ramp, near-black on the light end. A single ink colour is
    # unreadable at one end or the other -- the ramp spans most of the lightness range.
    labels = alt.Chart(finished).mark_text(fontSize=9.5, fontWeight=500).encode(
        x=x, y=y,
        text=alt.Text("finish_position:Q", format=".0f"),
        color=alt.condition(alt.datum.finish_position <= 8,
                            alt.value("#ffffff"), alt.value("#0d0d0d")),
    )
    dnf_labels = alt.Chart(retired).mark_text(fontSize=8.5, fontWeight=600,
                                              color="#ffffff").encode(
        x=x, y=y, text=alt.value("DNF"),
    )

    return alt.layer(cells, dnf_cells, labels, dnf_labels).properties(height=height)
