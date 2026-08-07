"""Who won the season, and with what -- from v_driver_season and v_constructor_season.

Sits beside the championship chart: the line shows how the title was won, this
shows what it was won with. Every counter here is a SUM over a pre-computed flag
on the fact, so the panel costs one scan and no CASE expressions.

Champion = the highest points total in scope. Our totals exclude sprint races, so
from 2021 they sit below the official figures -- but the ORDERING was verified
against real final standings for every season, so the driver named here is the
driver who actually won it.
"""
import streamlit as st


def _driver_champion(driver_season, season):
    rows = driver_season[driver_season["season"] == season]
    return rows.sort_values("points", ascending=False).iloc[0] if len(rows) else None


def _constructor_champion(constructor_season, season):
    rows = constructor_season[constructor_season["season"] == season]
    return rows.sort_values("points", ascending=False).iloc[0] if len(rows) else None


def render(driver_season, constructor_season, season):
    driver = _driver_champion(driver_season, season)
    team = _constructor_champion(constructor_season, season)

    if driver is None or team is None:
        st.info(f"No results loaded for {season}.")
        return

    # Deliberately text, not st.metric. Two cards of four metric widgets measured
    # ~380px against the 250px chart beside them, which alone pushed the page into
    # scrolling. The same numbers as bold inline text read just as well at ~90px a
    # card, and the row now matches the chart's height instead of driving it.
    share = 100 * team["points"] / constructor_season[
        constructor_season["season"] == season]["points"].sum()

    def card(name, subtitle, headline, stats, footnote):
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:1.05em;font-weight:600;line-height:1.3'>{name}</div>"
                f"<div style='opacity:0.55;font-size:0.8em;margin-bottom:0.35rem'>{subtitle}</div>"
                f"<div style='font-size:1.5em;font-weight:700;line-height:1.1'>{headline}</div>"
                f"<div style='font-size:0.88em;margin-top:0.2rem'>{stats}</div>"
                f"<div style='opacity:0.55;font-size:0.78em;margin-top:0.25rem'>{footnote}</div>",
                unsafe_allow_html=True,
            )

    # One markdown block per card rather than stacked st.markdown + st.caption:
    # each Streamlit element carries its own margin, and four of them measured
    # ~170px a card against the 250px chart beside them. Same content, ~110px.
    card(
        driver["driver_name"],
        f"Drivers' champion · {driver['main_constructor']}",
        f"{driver['points']:.0f} pts",
        f"<b>{int(driver['wins'])}</b> wins · <b>{int(driver['podiums'])}</b> podiums · "
        f"<b>{int(driver['pole_starts'])}</b> poles · <b>{int(driver['dnfs'])}</b> DNFs",
        # A rate, not a count: it survives a season being 16 races long in 1994
        # and 24 in 2024.
        f"won {100 * driver['wins'] / driver['races']:.0f}% of {int(driver['races'])} races · "
        f"avg finish {driver['avg_finish']:.1f} from grid {driver['avg_grid']:.1f}",
    )
    card(
        team["constructor_name"],
        "Constructors' champion",
        f"{team['points']:.0f} pts",
        f"<b>{int(team['wins'])}</b> wins · <b>{int(team['podiums'])}</b> podiums · "
        f"<b>{int(team['dnfs'])}</b> DNFs",
        f"took {share:.0f}% of all points scored in {season}",
    )
