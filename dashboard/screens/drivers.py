"""Page 2 -- driver performance, separated from the car as far as the data allows.

The season page answers "who won". This one answers the harder question: who DROVE well. Those
are different, and the gap between them is the most interesting thing in the warehouse -- a
driver in the fastest car and a driver dragging a slow one into the points are not comparable on
points, but they are comparable on what they did with the position they started from.

Three figures, in order of how much they subtract:
    race craft    -- places gained, with the arithmetic of the grid slot removed
    rolling form  -- the 5-race moving average, so a single bad Sunday does not read as a slump
    result grid   -- every raw result, subtracting nothing, as the check on the two above
"""
import streamlit as st

import db
import theme
from charts import position_heatmap, race_craft, rolling_form

st.markdown("## Driver performance")

kpi = db.season_kpis()
seasons = sorted(kpi["season"].unique(), reverse=True)
driver_season = db.driver_season()

with st.sidebar:
    st.markdown("#### Filters")
    season = st.selectbox("Season", seasons, index=0, key="drivers_season_pick")

season_drivers = driver_season[driver_season["season"] == season].sort_values(
    ["points", "wins", "podiums"], ascending=False
)
all_names = season_drivers["driver_name"].tolist()

with st.sidebar:
    picked = st.multiselect(
        "Drivers on the form chart", all_names, default=all_names[:5],
        max_selections=theme.MAX_SERIES,
        help=f"Up to {theme.MAX_SERIES}. Colours are assigned in championship order and stay "
             "with the driver, so removing one does not repaint the others.",
    )
    st.caption("The race-craft and result-grid figures always show the full field.")

st.caption(
    f"Season {season}. Everything on this page compares drivers WITHIN one season only: field "
    "size was 26 in 1994 and 20 today, so a given grid slot is not the same starting point "
    "across eras."
)

with theme.card("racecraft"):
    theme.section(
        "Race craft — places gained against par for the grid slot",
        "Raw places gained mostly ranks drivers by how slow their car qualifies: pole cannot gain "
        "a place and last cannot lose one. Averaged over 2020-26 the gain by slot runs P1 -1.2, "
        "P10 +0.3, P20 +5.3. Subtracting par for each slot, computed within the season, leaves "
        "the part the driver and team are responsible for — and it reorders the field, which is "
        "the test that it does something. The bars sum to zero by construction.",
    )
    figure = race_craft.render(db.driver_race_craft(), season)
    if figure is not None:
        theme.chart(figure, key="race_craft")

st.write("")
with theme.card("form"):
    theme.section(
        "Rolling form",
        "Five-race moving average of finishing position — the axis is reversed, so up is better. "
        "The window runs across season boundaries, so the first rounds include the end of the "
        "previous year. A hollow marker means fewer than five of those five races produced a "
        "classified finish, so the average is resting on less than it appears to.",
    )
    if picked:
        figure = rolling_form.render(db.driver_rolling_form(), season, picked)
        if figure is not None:
            theme.chart(figure, key="rolling_form")
    else:
        st.info("Pick at least one driver in the sidebar to draw the form chart.")

st.write("")
with theme.card("grid"):
    theme.section(
        "Every result of the season",
        "Driver by round, coloured by finishing position — dark is a better result. Retirements "
        "are drawn separately rather than as a 21st position: a car with no finishing position "
        "has no place on a position scale. The number in each cell makes this the table view too.",
    )
    figure = position_heatmap.render(db.driver_rolling_form(), season, all_names)
    if figure is not None:
        theme.chart(figure, key="position_grid")
