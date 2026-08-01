-- GRAIN: one row per DRIVER, per RACE -- the same grain as fact_race_result, a different business
-- process. 11,190 rows for 1994-2026.
--
-- Five dimension keys, not six: qualifying has no finishing status.
--
-- This is a separate fact table rather than extra columns on fact_race_result because neither is a
-- subset of the other -- some result rows have no qualifying row (83 races predate the source's
-- qualifying coverage) and 7 qualifying rows have no result (drivers who qualified then did not
-- start). Merging would force structural NULLs in both directions and destroy the meaning of the
-- NULLs already here: q3_ms IS NULL currently means exactly "eliminated in Q2, or pre-2006".
CREATE TABLE IF NOT EXISTS fact_qualifying (
    -- five conformed dimension keys
    date_key             INTEGER  NOT NULL REFERENCES dim_date(date_key)               ON DELETE RESTRICT,
    race_key             INTEGER  NOT NULL REFERENCES dim_race(race_key)               ON DELETE RESTRICT,
    driver_key           INTEGER  NOT NULL REFERENCES dim_driver(driver_key)           ON DELETE RESTRICT,
    constructor_key      INTEGER  NOT NULL REFERENCES dim_constructor(constructor_key) ON DELETE RESTRICT,
    circuit_key          INTEGER  NOT NULL REFERENCES dim_circuit(circuit_key)         ON DELETE RESTRICT,

    -- lineage and audit
    source_qualifying_id INTEGER  NOT NULL UNIQUE,
    race_date            DATE     NOT NULL,

    -- measures
    quali_position       SMALLINT NOT NULL CHECK (quali_position > 0),
    q1_ms                BIGINT,                        -- NULL if no time set
    q2_ms                BIGINT,                        -- NULL if eliminated in Q1, or pre-2006
    q3_ms                BIGINT,                        -- NULL if eliminated in Q2, or pre-2006
    best_quali_ms        BIGINT,                        -- DERIVED COALESCE(q3_ms, q2_ms, q1_ms)
    gap_to_pole_ms       BIGINT   CHECK (gap_to_pole_ms >= 0),

    -- pre-computed flags
    is_pole              BOOLEAN  NOT NULL DEFAULT FALSE,
    reached_q2           BOOLEAN  NOT NULL DEFAULT FALSE,
    reached_q3           BOOLEAN  NOT NULL DEFAULT FALSE,

    PRIMARY KEY (race_key, driver_key)
);

COMMENT ON COLUMN fact_qualifying.quali_position       IS 'SEMI-ADDITIVE: AVG only, never SUM.';
COMMENT ON COLUMN fact_qualifying.q1_ms                IS 'NON-ADDITIVE. NULL by rule, not missing data.';
COMMENT ON COLUMN fact_qualifying.q2_ms                IS 'NON-ADDITIVE. NULL by rule: eliminated in Q1, or the season predates the knockout format.';
COMMENT ON COLUMN fact_qualifying.q3_ms                IS 'NON-ADDITIVE. NULL by rule: eliminated in Q2, or the season predates the knockout format.';
COMMENT ON COLUMN fact_qualifying.best_quali_ms        IS 'DERIVED COALESCE(q3_ms, q2_ms, q1_ms): the driver''s true single-lap pace, whatever segment they reached.';
COMMENT ON COLUMN fact_qualifying.gap_to_pole_ms       IS 'DERIVED best_quali_ms - MIN(best_quali_ms) OVER (PARTITION BY race_key). Makes pace comparable across circuits and eras.';
COMMENT ON COLUMN fact_qualifying.reached_q2           IS 'DERIVED q2_ms IS NOT NULL. The era-safe substitute for comparing raw Q times.';
COMMENT ON COLUMN fact_qualifying.reached_q3           IS 'DERIVED q3_ms IS NOT NULL. The era-safe substitute for comparing raw Q times.';
COMMENT ON COLUMN fact_qualifying.source_qualifying_id IS 'Lineage to f1_prod.qualifying.qualifying_id, and the ON CONFLICT target that makes the load idempotent.';
COMMENT ON COLUMN fact_qualifying.race_date            IS 'Audit / incremental watermark, matching fact_race_result.';
