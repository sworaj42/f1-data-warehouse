"""What a driver's season was actually made of -- every start, sorted into one of five buckets.

A points total says who was best. It does not say whether a driver got there on relentless
podiums or on one dominant run past a wall of retirements. This chart does, because the five
segments are DISJOINT and sum to the driver's start count.

THE BUCKETS ARE COMPUTED IN SQL, NOT HERE. v_driver_season carries wins, podiums_not_win,
points_not_podium, classified_no_points and dnfs as separate columns precisely so this module can
melt them and draw. The subtraction that makes them disjoint is safe because the underlying flags
are strictly nested -- verified on the loaded fact, 0 rows are a win but not a podium, 0 a podium
but not a points finish, 0 both a points finish and a DNF -- and the place to record that is the
view, next to the SUMs.

Colour is the OUTCOME scale, shared with the reliability chart on the Eras page: cool = the car
came home, warm = it did not, neutral grey for a finish that scored nothing. The two charts answer
the same question at different grains, so they read in the same language.
"""
import altair as alt
import pandas as pd

import theme

# Column -> legend label, in stack order (best outcome at the left of the bar).
_BUCKETS = {
    "wins": "Win",
    "podiums_not_win": "Podium",
    "points_not_podium": "Points",
    "classified_no_points": "Classified",
    "dnfs": "DNF",
}


def render(driver_season, season, drivers, height=None):
    df = driver_season[
        (driver_season["season"] == season) & (driver_season["driver_name"].isin(drivers))
    ]
    if df.empty:
        return None

    # melt() is a reshape, not an aggregation: five columns of one row become five rows of one
    # column and no number changes. Every SUM behind them happened in the view.
    long = df.melt(
        id_vars=["driver_name", "races"],
        value_vars=list(_BUCKETS),
        var_name="bucket",
        value_name="starts",
    )
    long["outcome"] = long["bucket"].map(_BUCKETS)
    long = long[long["starts"] > 0]

    height = height or max(200, 30 * len(drivers) + 40)
    max_races = int(df["races"].max())

    base = alt.Chart(long).encode(
        y=alt.Y("driver_name:N", title=None, sort=list(drivers),
                axis=alt.Axis(labelLimit=150, labelFontSize=12)),
        x=alt.X("starts:Q", title="Starts",
                scale=alt.Scale(domain=[0, max_races], nice=False),
                axis=alt.Axis(grid=True, tickCount=6)),
        color=alt.Color("outcome:N", title=None,
                        scale=alt.Scale(domain=theme.OUTCOME_ORDER,
                                        range=theme.OUTCOME_COLORS),
                        legend=alt.Legend(orient="bottom", direction="horizontal",
                                          columns=5, symbolSize=110)),
        order=alt.Order("color_outcome_sort_index:Q"),
        tooltip=[
            alt.Tooltip("driver_name:N", title="Driver"),
            alt.Tooltip("outcome:N", title="Outcome"),
            alt.Tooltip("starts:Q", title="Races"),
            alt.Tooltip("races:Q", title="Season starts"),
        ],
    )

    # Two mark decisions, both load-bearing.
    #
    # stroke in the SURFACE colour, not a border: it opens a hairline gap between segments so two
    # adjacent fills never touch, which is what makes a stacked bar readable. A dark outline would
    # instead draw a box around every segment.
    #
    # 0.55 of the band rather than filling it: this chart shares its height with the constructor
    # chart beside it, so a season with few charted drivers and many teams would otherwise render
    # 40px+ blocks of saturated colour -- loud, and out of key with every other figure here.
    bars = base.mark_bar(height=alt.RelativeBandSize(0.55), stroke=theme.SURFACE,
                         strokeWidth=1.5, cornerRadiusEnd=3)

    return bars.properties(height=height)


def standings_table(driver_season, season):
    """The table view of the same season: every value in the charts above, readable without colour.

    Returned as a frame rather than rendered, so the page owns the st.dataframe column_config --
    the formatting is presentation, and this module only decides which columns and in what order.
    """
    df = driver_season[driver_season["season"] == season].sort_values(
        ["points", "wins", "podiums"], ascending=False
    )
    out = pd.DataFrame({
        "Pos": range(1, len(df) + 1),
        "Driver": df["driver_name"].to_numpy(),
        "Team": df["main_constructor"].to_numpy(),
        "Points": df["points"].to_numpy(),
        "Starts": df["races"].to_numpy(),
        "Wins": df["wins"].to_numpy(),
        "Podiums": df["podiums"].to_numpy(),
        "Poles": df["pole_starts"].to_numpy(),
        "DNFs": df["dnfs"].to_numpy(),
        "Avg finish": df["avg_finish"].to_numpy(),
        "Avg grid": df["avg_grid"].to_numpy(),
    })
    return out
