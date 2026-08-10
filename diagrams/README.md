# Diagrams

Visual documentation for the warehouse.

`readme/` holds the simplified, hand-written SVGs and the cropped screenshots the root `README.md`
embeds. They are deliberately small and readable at GitHub width. The full-detail diagrams stay in
this directory: Mermaid ER diagrams with every column and key marker live in
`docs/technical-reference.md`, and the DBeaver exports survive for the one thing Mermaid cannot do,
manual layout. Mermaid auto-arranges, so on a diagram with six dimensions feeding two facts the
connectors cross through unrelated tables and the radial shape is lost. A hand-arranged export is
still the better picture for a slide or a printed report, where that shape is the whole point.

| File | What it shows | Used for |
|---|---|---|
| `readme/architecture.svg` | Simplified pipeline flow with both DAG spans | root `README.md` |
| `readme/data-model.svg` | Fact constellation: 2 facts, 6 dimensions | root `README.md` |
| `readme/dashboard-*.png` | 1600px cropped page headers, linked to the full captures | root `README.md` |
| `oltp_erd.png` | `f1_prod`, 3NF, 7 tables: reference, event, transaction | slides, print, README link |
| `olap_star.png` | `f1_dw`, 6 dimensions and 2 facts, fact tables in red | slides, print, README link |
| `dashboard_1_season.png` | Season report page, full height | README crop target |
| `dashboard_2_drivers.png` | Driver performance page, full height | README crop target |
| `dashboard_3_eras.png` | Eras & trends page, full height | README crop target |
| `architecture_f1.png` | Detailed architecture render for slides | slides, print |

## Regenerating the README crops

Capture each page at a 1512x950 viewport with a 2x device scale factor, then crop away the sidebar
and everything below the first figure and resize to 1600px wide. The crop must keep the page title,
the KPI row where the page has one, and one representative chart.

## Regenerating `architecture_f1.png`

Unlike the ER diagrams, this one is **not** a DBeaver export — it is hand-written SVG in
`architecture_f1.html`, so the source is editable text and the PNG is a render of it. Edit the
HTML, then re-export with headless Chrome at a 2x device scale, which is what makes the 2400x1350
SVG land as a 4800x2700 PNG:

```bash
~/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-mac-arm64/chrome-headless-shell \
  --headless --disable-gpu --hide-scrollbars \
  --window-size=2400,1350 --force-device-scale-factor=2 --virtual-time-budget=3000 \
  --screenshot=diagrams/architecture_f1.png \
  "file://$PWD/diagrams/architecture_f1.html"
```

**Check the label backing rects after any text change.** Each DAG title sits on its own
`<rect>` whose width is hard-coded — SVG cannot auto-size a box to its text — so lengthening a
label without widening the rect leaves the text hanging off the end of its own background. Verify
by looking at the rendered PNG, not by reading the SVG.

## Regenerating the dashboard screenshots

Start the dashboard, then capture each page **at its full height rather than at the viewport
height**. Streamlit scrolls an inner container, so an ordinary full-page capture records only the
first screen. Measure `document.querySelector('[data-testid="stMain"]').scrollHeight`, reopen the
browser at that height, and screenshot — 1512px wide keeps the two-column rows side by side, which
is how the pages are meant to be read.

## Regenerating the ER diagrams

In DBeaver, with a connection to the database:

1. Expand the connection → **Schemas → public**, then open the **ER Diagram** tab.
2. **Delete `schema_migrations` from the canvas.** It is the migration ledger — infrastructure,
   not part of the data model. Left in, it floats unconnected and distracts from the star.
3. **Colour the fact tables differently from the dimensions** (right-click a table → *Set color*).
   This is the single most important step for `olap_star.png`: a star diagram's whole job is
   saying "these two are facts, those six are dimensions", and identical boxes do not say it.
4. Arrange dimensions around the two facts so the radial shape is visible, and drag connectors so
   lines do not cross through unrelated tables.
5. **Export**: right-click the canvas → *Export diagram* → PNG, and save over the file here using
   the same name, so the `README.md` links keep working.

For `oltp_erd.png` the equivalent of step 3 is colouring by 3NF layer — reference
(`circuits`, `drivers`, `constructors`, `statuses`), event (`races`), transaction
(`results`, `qualifying`) — which makes the load order visible in the picture.

## Note on theme

The current exports use DBeaver's dark theme. They are legible on GitHub in either mode, but a
dark rectangle on a light page is not seamless, and dark backgrounds print poorly. If these end up
in a printed report, re-export from a light DBeaver theme.
