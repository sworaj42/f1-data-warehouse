# F1 Data Warehouse

End-to-end data engineering pipeline: Jolpica-F1 API → raw JSON → normalized OLTP
(`f1_prod`) → star-schema warehouse (`f1_dw`) → Streamlit dashboard.

**Status: Stage 1 (API → OLTP).** This repo currently builds and populates the normalized
3NF OLTP database. The warehouse (`f1_dw`), Airflow DAGs, and dashboard come in later stages.

## Architecture (stage 1)

```
Jolpica-F1 API  --extract·paginate·rate-limit·retry-->  data/raw/ (JSON on disk = network boundary)
data/raw/       --parse·clean·dedup·upsert----------->  f1_prod (PostgreSQL, 3NF)
```

Once JSON is on disk nothing downstream touches the network — parse/load run fully offline.

## Layout

```
docker-compose.yml        postgres:16; creates f1_prod (+ empty f1_dw for later)
docker/init/              first-boot SQL (creates f1_dw)
sql/oltp/001..007.sql     numbered 3NF migrations
etl/
  config.py               env-driven config (DSN, paths, seasons, rate limits)
  logging_config.py       file + console logging
  db.py                   get_conn() + transaction() context manager
  extract/jolpica.py      rate-limited client (dual token bucket), raw JSON landing
  oltp/parse.py           raw JSON -> normalized rows (flatten, clean, dedup, time-parse)
  oltp/load.py            idempotent upserts + surrogate-key lookups
scripts/
  run_migrations.py       apply migrations (schema_migrations ledger)
  backfill.py             API -> raw -> f1_prod (manual, one-off)
```

## Run it

```bash
# 0. one-time: python deps (a .venv already exists here)
./.venv/bin/pip install -r requirements.txt

# 1. copy env and start Postgres
cp .env.example .env          # (a dev .env is already present)
docker compose up -d          # f1_prod + f1_dw on localhost:5432

# 2. create the OLTP schema
./.venv/bin/python scripts/run_migrations.py

# 3a. smoke test on one season (validates the whole path)
./.venv/bin/python scripts/backfill.py --smoke

# 3b. full backfill 2015–2025
./.venv/bin/python scripts/backfill.py
```

Connect DBeaver to `localhost:5432`, database `f1_prod`, user/password from `.env` (`f1`/`f1`).

## Idempotency (the gate)

Run the backfill twice → identical row counts. Dimensions upsert on their natural key;
transaction tables conflict on `(race_id, driver_id)`. Extraction is cached to disk, so a
re-run never re-hits the API.

## Notes

- **Page size:** the spec assumes a 1000-row page size; the live Jolpica API caps pages at
  100. The client paginates by the effective `limit` it reports, so a full backfill is
  ~110 requests (still well inside the 500/hour quota).
- Logs are written to `logs/` and echoed to the console, with per-stage timings and row counts.
