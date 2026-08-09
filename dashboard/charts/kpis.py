"""KPI cards.

A card is the right form when the answer is ONE number -- the chart would be a single bar, which
is not a chart. These are the numbers a reader wants before any figure: how big was the season,
how many drivers actually won, how often did cars break.

EVERY CARD CARRIES A DELTA AGAINST THE PREVIOUS SEASON, and that is the whole reason the cards
earn their space. "11.5% did not finish" is a fact with no scale attached; "11.5%, down 1.7 points
on last season" is a reading.

THE DELTA COLOUR IS SET PER CARD, not left at the default, because Streamlit paints every rise
green and green means "good". Only three of these five have a good direction: more different race
winners and a higher pole conversion are green when they rise, the DNF rate is "inverse" so a
rise is red. The other two are "off" -- grey. A season in progress has fewer races than a
completed one, and painting that -13 red would be calling an incomplete calendar a bad result;
average places gained has no good direction at all, since it rises when more cars retire.

NO SPARKLINES. st.metric(chart_data=...) renders a 188px row against the ~120px a plain bordered
card takes, and a five-card row of them pushes the first real figure below the fold on a laptop.
The trend charts on the Eras page are the same information at a size where it can be read.
"""
import streamlit as st

# label, column, formatter, delta colouring, help text
_CARDS = (
    ("Races", "races", "{:.0f}", "off",
     "Rounds with a loaded result. In-progress seasons show only the races that have run, which "
     "is why the delta is grey rather than red."),
    ("Race winners", "distinct_winners", "{:.0f}", "normal",
     "How many DIFFERENT drivers won a race. Counting wins would be meaningless -- there is "
     "exactly one per race, so it always equals the race count."),
    ("Did not finish", "dnf_rate_pct", "{:.1f}%", "inverse",
     "Share of results with no classified finishing position. Not the same as 'retired': about "
     "250 cars in scope stopped but had completed enough distance to still be classified."),
    ("Pole converted", "pole_to_win_pct", "{:.1f}%", "normal",
     "Share of pole positions that turned into a win."),
    ("Avg places gained", "avg_positions_gained", "{:+.2f}", "off",
     "Grid position minus finishing position, averaged. NULL for retirements and pit-lane "
     "starts, so those rows are excluded rather than counted as zero. Grey because it has no "
     "good direction -- it rises when more cars retire ahead of those still running."),
)


def season_cards(season_kpis, season):
    """Five cards for one season, each with a year-on-year delta."""
    row = season_kpis[season_kpis["season"] == season]
    if row.empty:
        return
    row = row.iloc[0]
    prior = season_kpis[season_kpis["season"] == season - 1]
    prior = prior.iloc[0] if not prior.empty else None

    for column, (label, field, fmt, delta_color, help_text) in zip(st.columns(5), _CARDS):
        value = row[field]
        delta = None
        if prior is not None and prior[field] is not None and value is not None:
            change = float(value) - float(prior[field])
            # Suppress a delta that rounds to nothing at the precision shown, rather than
            # printing "+0.0" and inviting the reader to read meaning into it.
            if abs(change) >= (0.05 if "." in fmt else 0.5):
                delta = f"{change:+.1f}" if "." in fmt else f"{change:+.0f}"
        column.metric(
            label,
            fmt.format(value) if value is not None else "--",
            delta,
            delta_color=delta_color,
            border=True,
            help=f"{help_text} Delta is against {season - 1}.",
        )


def era_cards(season_kpis, competitiveness, seasons):
    """Four cards summarising the selected span, for the Eras page.

    Each is a comparison of the two ends of the range rather than a total, because a total over
    33 unequal seasons ('13,028 results') is a size, not a finding.
    """
    lo, hi = seasons
    window = season_kpis[(season_kpis["season"] >= lo) & (season_kpis["season"] <= hi)]
    comp = competitiveness[
        (competitiveness["season"] >= lo) & (competitiveness["season"] <= hi)
    ]
    if window.empty:
        return
    first, last = window.iloc[0], window.iloc[-1]

    cards = st.columns(4)
    cards[0].metric(
        f"Did not finish, {int(last['season'])}",
        f"{last['dnf_rate_pct']:.1f}%",
        f"{float(last['dnf_rate_pct']) - float(first['dnf_rate_pct']):+.1f} vs {int(first['season'])}",
        delta_color="inverse", border=True,
        help="The largest single change in the data: the 1990s field failed to finish about 46% "
             "of the time, the 2020s field about 13%.",
    )
    cards[1].metric(
        "Races per season now",
        f"{last['races']:.0f}",
        f"{float(last['races']) - float(first['races']):+.0f} vs {int(first['season'])}",
        # Grey, not red: an in-progress season has fewer races because the rest of its calendar
        # has not happened yet, and colouring that as a decline would be reading it as a result.
        delta_color="off", border=True,
        help="Rounds with a loaded result. An in-progress season is short because the rest of "
             "its calendar has not been raced yet, not because it was shorter.",
    )
    if not comp.empty:
        peak = comp.loc[comp["top_constructor_win_share_pct"].idxmax()]
        cards[2].metric(
            "Most dominant season",
            f"{peak['top_constructor_win_share_pct']:.0f}%",
            f"{peak['top_constructor']} in {int(peak['season'])}",
            # The delta slot is carrying a label, not a change, so it takes no arrow and no
            # good/bad colour.
            delta_arrow="off", delta_color="off", border=True,
            help="Highest share of a season's races won by a single constructor, measured in "
                 "wins rather than points so it compares across every scoring era.",
        )
    cards[3].metric(
        "Most open season",
        f"{int(window['distinct_winners'].max())} winners",
        f"in {int(window.loc[window['distinct_winners'].idxmax(), 'season'])}",
        delta_arrow="off", delta_color="off", border=True,
        help="The season in this range with the most different race winners.",
    )
