"""Constructor standing for one season -- "is the sport competitive or dominated?"

Sourced from v_constructor_season, which exists because the KPI cards need a
season grain and this needs a constructor grain. One view cannot serve both
without a groupby in pandas, and aggregating in pandas would say the warehouse
was not trusted to do its job.

Points are summed within a single season here, so the era problem does not
arise: every team on this chart scored under the same rules.
"""
import altair as alt
import streamlit as st

import layout


def render(constructor_season, season):
    season_df = constructor_season[constructor_season["season"] == season]
    order = season_df.sort_values("points", ascending=False)["constructor_name"].tolist()

    chart = (
        alt.Chart(season_df)
        .mark_bar()
        .encode(
            # Horizontal bars: team names are long, and a rotated x-axis label is
            # harder to read than a left-aligned one.
            y=alt.Y("constructor_name:N", title=None, sort=order),
            x=alt.X("points:Q", title="Points"),
            color=alt.Color("wins:Q", title="Wins", scale=alt.Scale(scheme="reds")),
            tooltip=[
                alt.Tooltip("constructor_name:N", title="Team"),
                alt.Tooltip("points:Q", title="Points"),
                alt.Tooltip("wins:Q", title="Wins"),
                alt.Tooltip("podiums:Q", title="Podiums"),
                alt.Tooltip("dnfs:Q", title="DNFs"),
                alt.Tooltip("entries:Q", title="Car entries"),
            ],
        )
        # Fixed height, matching the chart beside it, so the two columns stay level.
        # Older seasons ran more teams; Altair compresses the bars rather than
        # growing the page, which is the trade this layout wants.
        .properties(height=layout.ROW2_HEIGHT)
    )
    st.altair_chart(chart, width="stretch")
