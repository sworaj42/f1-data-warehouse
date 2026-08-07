"""Reliability across 33 seasons -- the project's headline finding.

Nearly half the field failed to finish a 1990s race. Today it is roughly one in
eight, and mechanical failures have all but vanished.

This works as a chart only because dim_status collapses 109 distinct finishing
status strings into 5 groups at load time. 109 categories is not an axis. And it
is comparable across 33 seasons only because it counts statuses rather than
points -- "retired with a gearbox failure" means the same thing in 1994 as in
2026, where ten points does not.
"""
import altair as alt
import streamlit as st

import layout

# Finished at the bottom, failures stacked above it, so the growing/shrinking
# band of colour reads as "how much went wrong".
GROUP_ORDER = ["Finished", "Lapped", "Other", "Accident DNF", "Mechanical DNF"]

# Explicit colours rather than a named scheme. A diverging scheme assigned red to
# "Finished" and blue to "Mechanical DNF" -- correct as a gradient, exactly backwards
# as meaning, on a chart whose entire subject is failure. Here cool = the car
# finished, warm = it did not, and grey is the small non-mechanical remainder.
GROUP_COLOURS = ["#2E86C1", "#85C1E9", "#95A5A6", "#E67E22", "#C0392B"]


def render(reliability, season_range):
    lo, hi = season_range
    window = reliability[reliability["season"].between(lo, hi)]

    chart = (
        alt.Chart(window)
        .mark_area()
        .encode(
            x=alt.X("season:O", title="Season",
                    axis=alt.Axis(labelAngle=-90, labelOverlap=True)),
            y=alt.Y("pct_of_season:Q", title="Share of results (%)",
                    stack="normalize", axis=alt.Axis(format="%")),
            color=alt.Color("status_group:N", title="Outcome", sort=GROUP_ORDER,
                            scale=alt.Scale(domain=GROUP_ORDER, range=GROUP_COLOURS)),
            order=alt.Order("color_status_group_sort_index:Q"),
            tooltip=[
                alt.Tooltip("season:O", title="Season"),
                alt.Tooltip("status_group:N", title="Outcome"),
                alt.Tooltip("status_rows:Q", title="Results"),
                alt.Tooltip("pct_of_season:Q", title="Share of season (%)"),
            ],
        )
        .properties(height=layout.FULL_WIDTH_HEIGHT)
    )
    st.altair_chart(chart, width="stretch")

    # Compare the two ends of the selected window, so the caption states what the
    # chart shows rather than a hardcoded claim about the 1990s.
    def retirement_share(season):
        rows = window[window["season"] == season]
        failures = rows[~rows["status_group"].isin(["Finished", "Lapped"])]
        return 100 * failures["status_rows"].sum() / rows["status_rows"].sum()

    # One line, because it is the headline finding of the whole project and stating
    # it costs less vertical space than making the reader compute it off the axis.
    # The reason it sits above the DNF-rate KPI card is in the subheader tooltip.
    st.caption(
        f"Cars that did not complete the race: **{retirement_share(lo):.1f}%** in {lo} → "
        f"**{retirement_share(hi):.1f}%** in {hi}."
    )
