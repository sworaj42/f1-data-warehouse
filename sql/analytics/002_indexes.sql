-- Indexes serving the analytics layer. They live here rather than with the star DDL because they
-- exist for the read path: the facts are correct without them.
--
-- FOUR indexes, not the seven the spec lists. All seven were created and measured
-- (logs/explain_before_*.log vs logs/explain_after_*.log, and pg_stat_user_indexes scan counts);
-- three were then removed because the measurement showed they earn nothing. The rejected three and
-- the evidence against each are recorded at the foot of this file -- the before/after comparison is
-- the deliverable, so a measured negative belongs in the repo rather than in a deleted branch.
--
-- Postgres does NOT index foreign-key columns automatically. It creates indexes only for PRIMARY
-- KEY and UNIQUE constraints. That is why this file is needed at all.
--
-- Headline measurement, median of 7 runs after 2 warmups, 13,006-row fact:
--
--   query                             before      after     change
--   MAX(race_date)  (watermark)      1.410 ms    0.007 ms    ~200x
--   30-day incremental lookback      0.548 ms    0.011 ms     ~50x
--   one driver's whole career        0.164 ms    0.019 ms      ~9x
--   one constructor's history        0.565 ms    0.150 ms      ~4x
--   SELECT * FROM v_season_kpis     14.534 ms   14.660 ms    none
--   SELECT * FROM v_quali_vs_race   13.405 ms   14.005 ms    none
--
-- The split in that table is the real lesson: every SELECTIVE query got 4-200x faster, and every
-- view got nothing at all. A view is a full aggregation over the whole fact, so it reads every row
-- by definition and no index can help it. These indexes serve the ETL's watermark reads and any
-- filtered drill-down; the dashboard's speed comes from @st.cache_data, not from here.


-- The incremental watermark, and the biggest single win in the project: MAX(race_date) runs on
-- every pipeline execution and this turns a sequential scan of the whole fact into a one-row
-- backwards index scan. 1.410 ms -> 0.007 ms.
CREATE INDEX IF NOT EXISTS idx_frr_race_date ON fact_race_result (race_date);

-- race_key is the LEADING column of the primary key, so this looked redundant and was predicted to
-- be. It is not: the PK is two columns wide (304 kB rebuilt) and this is one (120 kB), so the
-- planner picks the narrower btree for race_key-only joins. Measured 252 scans, the most-used index
-- on the table. Prediction wrong, measurement right -- which is the argument for measuring.
CREATE INDEX IF NOT EXISTS idx_frr_race ON fact_race_result (race_key);

-- v_constructor_season groups the whole fact by constructor_key. 0.565 ms -> 0.150 ms.
CREATE INDEX IF NOT EXISTS idx_frr_constructor ON fact_race_result (constructor_key);

-- Composite, and the column ordering is the point: driver_key FIRST because it is the more
-- selective filter -- 177 distinct drivers against 611 races, so a driver predicate cuts the fact
-- to ~73 rows. A btree can only use a leading prefix, so (race_key, driver_key) would merely
-- duplicate the primary key; (driver_key, race_key) adds the access path the PK cannot serve.
-- Measured 180 scans, and it subsumes a standalone driver_key index entirely.
CREATE INDEX IF NOT EXISTS idx_frr_driver_race ON fact_race_result (driver_key, race_key);


-- --- Created, measured, and REJECTED --------------------------------------------------------
--
-- idx_frr_driver ON fact_race_result (driver_key)
--     0 scans across the full workload. A btree serves any leading prefix of its columns, so
--     idx_frr_driver_race (driver_key, race_key) already answers every driver_key lookup. This was
--     a strictly smaller duplicate of an index we keep, and the planner never chose it once.
--
-- idx_frr_date ON fact_race_result (date_key)
--     0 scans. No view joins dim_date: race_date is denormalised onto both facts and
--     dim_race.season carries the season grouping, so the date dimension is never traversed. The
--     index has no caller. dim_date remains a correct conformed dimension -- it just is not on the
--     access path, and indexing a column nothing filters on only slows the writes down.
--
-- idx_fq_race_driver ON fact_qualifying (race_key, driver_key)
--     Character-for-character the primary key of fact_qualifying, so Postgres already maintains
--     this exact btree. It initially showed 72 scans and looked useful, which was misleading: the
--     PK had bloated to 512 kB during the incremental upsert load while this index was built in
--     one pass at 264 kB, so the planner was preferring it purely on size. REINDEX on the PK
--     dropped it to 264 kB -- byte for byte identical -- confirming there was never a structural
--     advantage, only accumulated page splits. The right fix is to REINDEX, not to keep a second
--     copy of the primary key permanently in the write path.
