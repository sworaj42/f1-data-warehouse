"""Circuit character -- which tracks break cars, and how fast they are.

dim_circuit was the one conformed dimension no view reached: the warehouse carried it and nothing
asked it a question. v_circuit_profile is that question, and this is the figure.

WHY NOT "PLACES GAINED PER CIRCUIT", which was the first thing tried. It looks like an overtaking
measure and is not one: it is confounded by the very thing the left panel plots. Monaco tops the
places-gained ranking at +2.31 despite being the hardest track on the calendar to pass on, because
a third of the field retires there and every car still running inherits their positions. Attrition
manufactures places gained. The column is kept in the tooltip, where it can be read with that
caveat, and the second panel plots average fastest-lap speed instead -- a property of the track
itself that no amount of retirements can fake.

Two panels, two units, two axes, sorted identically. A single chart with two y scales would
invent a relationship between attrition and speed; side by side, the reader can see for
themselves that there isn't a clean one (Monaco is the slowest AND the most punishing; Monza is
the fastest and unremarkable for retirements).

Filtered to circuits with a real sample. A track visited twice has a DNF rate computed over ~40
entries and would top or bottom the ranking on noise alone.
"""
import altair as alt

import theme

MIN_RACES = 10


def render(circuit_profile, top_n=16, height_per_row=26):
    df = circuit_profile[circuit_profile["races_held"] >= MIN_RACES].copy()
    if df.empty:
        return None, None
    df = df.sort_values("dnf_rate_pct", ascending=False).head(top_n)
    order = df["circuit_name"].tolist()
    height = max(220, height_per_row * len(df) + 40)

    tooltip = [
        alt.Tooltip("circuit_name:N", title="Circuit"),
        alt.Tooltip("country:N", title="Country"),
        alt.Tooltip("races_held:Q", title="Races held"),
        alt.Tooltip("last_season:Q", title="Last used", format="d"),
        alt.Tooltip("dnf_rate_pct:Q", title="Did not finish (%)", format=".1f"),
        alt.Tooltip("avg_fastest_lap_kph:Q", title="Avg fastest lap (kph)", format=".0f"),
        alt.Tooltip("avg_positions_gained:Q", title="Avg places gained", format="+.2f"),
    ]

    def panel(field, title, fmt, colour):
        # Every panel keeps its own circuit labels. They live in separate Streamlit columns, and
        # a reader should never have to track a row across a column gap to know which track a bar
        # belongs to -- the repetition costs width and buys an unambiguous read.
        base = alt.Chart(df).encode(
            y=alt.Y("circuit_name:N", title=None, sort=order,
                    axis=alt.Axis(labelLimit=195, labelFontSize=11)),
            x=alt.X(f"{field}:Q", title=title,
                    scale=alt.Scale(domain=[0, float(df[field].max()) * 1.20], nice=False),
                    axis=alt.Axis(grid=True, tickCount=4, format=fmt)),
            tooltip=tooltip,
        )
        bars = base.mark_bar(color=colour, height=alt.RelativeBandSize(0.62), cornerRadiusEnd=3)
        labels = base.mark_text(align="left", dx=5, fontSize=10.5, color=theme.INK_2).encode(
            text=alt.Text(f"{field}:Q", format=fmt),
        )
        return alt.layer(bars, labels).properties(height=height)

    attrition = panel("dnf_rate_pct", "Entries that did not finish (%)", ".1f", theme.RED_DEEP)
    speed = panel("avg_fastest_lap_kph", "Average fastest lap (kph)", ".0f", theme.SERIES[0])
    return attrition, speed
