"""The five KPI cards, from v_season_kpis.

Every one of these is a column the warehouse already computed. The dashboard reads
one row and formats it -- there is no arithmetic here, because each figure is a
SUM over a pre-computed boolean flag on the fact, which is why those flags exist.

There is no "Wins recorded" card. It was measured against all 33 seasons and found
to be identical to "Races" every single time, since every race has exactly one
winner. "Distinct winners" is the question that actually has an answer.
"""
import streamlit as st

# How many seasons of history each sparkline shows. Enough to read a trend,
# short enough that the 1990s do not flatten the recent years.
def render(kpis, season):
    """Five cards in one row.

    No sparklines and no borders, both tried and both removed by measurement:
    st.metric(border=True, chart_data=...) rendered a 188px row against the 85px
    this layout can afford, which is what pushed page 1 into scrolling. The trend
    they showed is on page 2 across all 33 seasons, at full size, where it is
    actually readable.
    """
    row = kpis[kpis["season"] == season].iloc[0]

    cols = st.columns(5)
    cols[0].metric("Races", int(row["races"]))
    cols[1].metric("Drivers", int(row["drivers"]))
    cols[2].metric(
        "Distinct winners", int(row["distinct_winners"]),
        help="How many different drivers won a race. Low means one team ran away "
             "with it: 3 in 2023, against 8 in 2003. Counts a flag, so it is "
             "comparable across all 33 seasons.",
    )
    cols[3].metric(
        "DNF rate", f"{row['dnf_rate_pct']:.1f}%",
        help="Share of entries with no finishing position. Near half the field in "
             "the mid-1990s, roughly one in eight today.",
    )
    # Signed, because "gained 0.4 places" and "lost 0.4 places" are different
    # claims and an unsigned number hides which one this is.
    cols[4].metric(
        "Avg places gained", f"{row['avg_positions_gained']:+.2f}",
        help="Grid to flag, averaged over classified finishers. Runs positive "
             "because retirements free up positions ahead of everyone still running.",
    )

    # Returned rather than rendered: the page composes this beside the Filters
    # popover so the two share one row. This module draws cards; the page owns
    # layout. The caveat itself is the era one -- the scoring system changed four
    # times across 1994-2026, so a points total only means something against other
    # seasons in the same band.
    return (
        f"{row['points_era']} scoring era · {int(row['result_rows'])} result rows · "
        f"pole converted to a win {row['pole_to_win_pct']:.0f}% of the time. "
        "Points compare within an era only; the flag-based figures compare across all 33 seasons."
    )
