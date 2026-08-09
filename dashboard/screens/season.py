"""Page 1 -- one season, from the headline numbers down to every individual result.

The page is ordered the way a reader asks questions: how big was this season and how did it go
(cards), who won it and when was it decided (progression), which car was underneath them
(constructors), what was each driver's season actually made of (outcomes), and finally the
numbers themselves (table). Nothing below the cards repeats what the cards already said.

FILTERS LIVE IN THE SIDEBAR, in one block, and every figure on the page reads the same selection.
Per-chart controls are the usual way a dashboard starts lying: two figures end up on different
slices and nothing says so.
"""
import streamlit as st

import db
import theme
from charts import championship, constructors, kpis, outcomes

st.markdown("## Season report")

kpi = db.season_kpis()
seasons = sorted(kpi["season"].unique(), reverse=True)

with st.sidebar:
    st.markdown("#### Filters")
    season = st.selectbox("Season", seasons, index=0, key="season_pick")
    top_n = st.slider(
        "Drivers to chart", min_value=3, max_value=theme.MAX_SERIES, value=6,
        help=f"Capped at {theme.MAX_SERIES}. The palette has exactly that many "
             "colour-blind-separable colours, and a right-hand legend needs about 28px per "
             "entry -- past this, Vega drops entries silently instead of reporting it.",
    )

era = kpi.loc[kpi["season"] == season, "points_era"].iloc[0]
st.caption(
    f"Season {season} · {era} scoring era. Points are comparable only inside one era -- the "
    "scoring system changed four times between 1994 and 2026 -- so the 33-season charts on the "
    "Eras page count wins instead. Sprint points are out of scope, so totals from 2021 sit "
    "19-38 points below the official ones; the ordering is unaffected."
)

kpis.season_cards(kpi, season)

# Championship order comes from v_driver_season, which already aggregated it. Ranking the drivers
# here with a groupby would be the dashboard doing the warehouse's job.
driver_season = db.driver_season()
season_drivers = driver_season[driver_season["season"] == season].sort_values(
    ["points", "wins", "podiums"], ascending=False
)
leaders = season_drivers["driver_name"].head(top_n).tolist()

st.write("")
with theme.card("championship"):
    if not season_drivers.empty:
        champion = season_drivers.iloc[0]
        theme.section(
            "Championship progression",
            f"Cumulative points after every round. {champion['driver_name']} finishes on "
            f"{champion['points']:.0f} for {champion['main_constructor']}. The running total is a "
            "SUM() OVER (PARTITION BY season, driver ORDER BY round) window in the warehouse, not "
            "a loop here. Hover any round for the whole field at that point.",
        )
    figure = championship.render(db.championship_progression(), season, leaders)
    if figure is not None:
        theme.chart(figure, key="championship")

st.write("")
# One height for both figures in this row. They are driven by different row counts -- eleven
# constructors against six drivers -- so left to themselves the cards end at different depths and
# the row reads as broken rather than as two panels.
constructor_rows = db.constructor_season()
n_teams = len(constructor_rows[constructor_rows["season"] == season])
row_height = max(26 * n_teams + 30, 30 * top_n + 60)

left, right = st.columns(2, gap="medium")

with left:
    with theme.card("constructors"):
        theme.section(
            "Constructors",
            "Season points by team. Bar length is the encoding, so every bar is one colour.",
        )
        figure = constructors.render(constructor_rows, season, height=row_height)
        if figure is not None:
            theme.chart(figure, key="constructors")

with right:
    with theme.card("outcomes"):
        theme.section(
            "What each season was made of",
            "Every start, sorted into five buckets that do not overlap and add up to the "
            "driver's start count. Cool = the car came home, warm = it did not.",
        )
        figure = outcomes.render(driver_season, season, leaders, height=row_height)
        if figure is not None:
            theme.chart(figure, key="outcomes")

st.write("")
with theme.card("standings"):
    theme.section(
        "Final standings",
        "The table view of everything above -- every value on this page is readable here without "
        "relying on colour.",
    )
    table = outcomes.standings_table(driver_season, season)
    st.dataframe(
        table,
        hide_index=True,
        # Sized to the row count instead of capped: the page scrolls, so a fixed height would put
        # a second scrollbar inside the first for no benefit.
        height=36 * len(table) + 42,
        column_config={
            "Pos": st.column_config.NumberColumn(width=52),
            "Driver": st.column_config.TextColumn(width="medium"),
            "Team": st.column_config.TextColumn(width="medium"),
            # A progress bar in the points column makes the gap between championship rivals
            # visible in the table itself, so the table is not just a fallback for the chart.
            "Points": st.column_config.ProgressColumn(
                format="%.0f", min_value=0,
                max_value=float(table["Points"].max()) if len(table) else 1,
            ),
            "Avg finish": st.column_config.NumberColumn(format="%.2f"),
            "Avg grid": st.column_config.NumberColumn(format="%.2f"),
        },
    )
