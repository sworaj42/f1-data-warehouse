# Diagrams

Visual documentation for the warehouse. Two kinds, kept deliberately separate:

- **Conceptual diagrams live in the root `README.md` as Mermaid** — architecture, the star
  constellation, the pipeline stages. They render natively on GitHub, live in version control, and
  cannot silently drift out of sync with the code.
- **Detailed ER diagrams live here as PNG exports** from DBeaver. They document every column of
  every table, which Mermaid renders poorly at 24 columns wide.

The two do different jobs: the Mermaid star explains *why the design is a constellation*, the PNG
documents *what was actually implemented*.

| File | What it shows |
|---|---|
| `oltp_erd.png` | `f1_prod` — 3NF, 7 tables: reference, event, transaction |
| `olap_star.png` | `f1_dw` — 6 dimensions + 2 facts, fact tables in red |

Once those stages exist: `airflow_dag.png` (the DAG graph from the Airflow UI) and
`dashboard.png` (the Streamlit dashboard).

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
