"""The five KPI cards, from v_season_kpis.

Every one of these is a column the warehouse already computed. The dashboard
reads a single row and formats it -- there is no arithmetic here, because each
figure is a SUM over a pre-computed boolean flag on the fact, which is the whole
reason those flags exist.
"""
import streamlit as st


def render(kpis, season):
    row = kpis[kpis["season"] == season].iloc[0]

    cols = st.columns(5)
    cols[0].metric("Races", int(row["races"]))
    cols[1].metric("Drivers", int(row["drivers"]))
    cols[2].metric("Wins recorded", int(row["wins_recorded"]))
    cols[3].metric("DNF rate", f"{row['dnf_rate_pct']:.1f}%")
    # Signed, because "gained 0.4 places" and "lost 0.4 places" are different
    # claims and an unsigned number hides which one this is.
    cols[4].metric("Avg positions gained", f"{row['avg_positions_gained']:+.2f}")

    # The era caveat, surfaced in the UI rather than buried in a column comment.
    # The scoring system changed four times across 1994-2026, so a points total
    # is only meaningful against other seasons in the same band.
    st.caption(
        f"{row['points_era']} scoring era · {int(row['result_rows'])} result rows · "
        f"pole converted to a win {row['pole_to_win_pct']:.0f}% of the time. "
        "Points are comparable within an era only; the flag-based figures "
        "(wins, DNF rate) are comparable across all 33 seasons."
    )
