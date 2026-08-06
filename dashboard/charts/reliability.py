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

# Finished at the bottom, failures stacked above it, so the growing/shrinking
# band of colour reads as "how much went wrong".
GROUP_ORDER = ["Finished", "Lapped", "Other", "Accident DNF", "Mechanical DNF"]


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
                            scale=alt.Scale(scheme="redyellowblue")),
            order=alt.Order("color_status_group_sort_index:Q"),
            tooltip=[
                alt.Tooltip("season:O", title="Season"),
                alt.Tooltip("status_group:N", title="Outcome"),
                alt.Tooltip("status_rows:Q", title="Results"),
                alt.Tooltip("pct_of_season:Q", title="Share of season (%)"),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(chart, width="stretch")

    # Compare the two ends of the selected window, so the caption states what the
    # chart shows rather than a hardcoded claim about the 1990s.
    def retirement_share(season):
        rows = window[window["season"] == season]
        failures = rows[~rows["status_group"].isin(["Finished", "Lapped"])]
        return 100 * failures["status_rows"].sum() / rows["status_rows"].sum()

    st.caption(
        f"Cars that did not complete the race: {retirement_share(lo):.1f}% in {lo}, "
        f"{retirement_share(hi):.1f}% in {hi}. "
        "This counts status groups, not points, which is what makes it comparable "
        "across eras at all."
    )
    # Worth stating rather than hiding: this figure runs 1-2 points above the DNF-rate
    # KPI card, and the two are measuring different things. is_dnf means "no finishing
    # position"; this means "retired". Around 250 rows are both retired AND classified,
    # because a driver who completes 90% of the distance is classified even if the car
    # stops. Neither number is wrong; they answer different questions.
    st.caption(
        ":grey[Runs slightly above the DNF-rate KPI: that card counts cars with no "
        "finishing position, while this counts retirements. A car retiring after 90% "
        "distance is still classified, so it appears here but not there.]"
    )
