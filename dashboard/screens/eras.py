"""Page 3 -- the whole 33 seasons at once: reliability, competitiveness, and the tracks.

This is the page the warehouse was built for. Every figure on it spans 1994-2026, which is only
possible because each one counts a load-time BOOLEAN FLAG rather than a points total: the scoring
system changed four times in that window, so anything measured in points compares nothing across
it. Wins, retirements and finishing positions mean the same in every season.

The season-range filter scopes the two trend figures. The circuit figures at the bottom are
deliberately outside it, and say so -- a per-circuit rate needs every season it can get before it
stops being noise.
"""
import streamlit as st

import db
import theme
from charts import circuits, competitiveness, kpis, reliability

st.markdown("## Eras & trends")

kpi = db.season_kpis()
comp = db.season_competitiveness()
first, last = int(kpi["season"].min()), int(kpi["season"].max())

with st.sidebar:
    st.markdown("#### Filters")
    span = st.slider("Seasons", min_value=first, max_value=last, value=(first, last),
                     help="Scopes the reliability and competitiveness figures. The circuit "
                          "figures below use all seasons.")

st.caption(
    f"Seasons {span[0]}–{span[1]}. Every measure here counts a boolean flag — a retirement, a "
    "win, a classified finish — so it is comparable across all 33 seasons. Nothing on this page "
    "is measured in points, because points are not."
)

kpis.era_cards(kpi, comp, span)

st.write("")
with theme.card("reliability"):
    theme.section(
        "How every car ended its race",
        "Share of all results by outcome, per season. This is the single largest change in the "
        "data: the mid-1990s field failed to finish about 46% of the time, the 2020s field about "
        "13%. Cool = the car came home, warm = it did not. The five groups collapse 109 distinct "
        "source status strings, done once at load time in dim_status.\n\n"
        "Two caveats the figure marks rather than hides. **From 2023 the source stops reporting "
        "why a car retired** and retirements collapse into 'Other' — 73 results carried a cause "
        "in 2022 and none did in 2024 — so the mechanical and accident bands ending is a "
        "reporting change, not cars that stopped breaking. The total retirement share is still "
        "sound across it. And 'did not finish' is not the same measure as 'retired': roughly 250 "
        "cars in scope stopped on track but had covered enough distance to stay classified.",
    )
    figure = reliability.render(db.reliability_trend(), span)
    if figure is not None:
        theme.chart(figure, key="reliability")

st.write("")
left, right = st.columns(2, gap="medium")

with left:
    with theme.card("dominance"):
        theme.section(
            "How dominant was the best team?",
            "Share of each season's races won by its most successful constructor. Measured in "
            "wins, not points, so it compares across every scoring era. The dashed line is half "
            "the season: above it, one team won more races than the rest of the grid combined.",
        )
        figure = competitiveness.dominance(comp, span)
        if figure is not None:
            theme.chart(figure, key="dominance")

with right:
    with theme.card("winners"):
        theme.section(
            "How many different winners?",
            "Distinct race winners and distinct winning teams per season. Both are counts of the "
            "same kind, so they share one axis — two scales on one plot would invent a "
            "relationship between them.",
        )
        figure = competitiveness.winners(kpi, comp, span)
        if figure is not None:
            theme.chart(figure, key="winners")

st.write("")
theme.section(
    "Circuit character",
    f"All {last - first + 1} seasons, not the range selected above — a per-circuit rate needs "
    f"every race it can get. Limited to circuits that have held at least {circuits.MIN_RACES} of "
    "them. Sorted by attrition in both panels. Places gained is in the tooltip but not plotted: "
    "at circuit grain it measures attrition, not overtaking — Monaco leads it because a third of "
    "the field retires there and everyone still running inherits the places.",
)
attrition, speed = circuits.render(db.circuit_profile())
if attrition is not None:
    left, right = st.columns(2, gap="medium")
    with left:
        with theme.card("circuit_attrition"):
            theme.chart(attrition, key="circuit_attrition")
    with right:
        with theme.card("circuit_speed"):
            theme.chart(speed, key="circuit_speed")
