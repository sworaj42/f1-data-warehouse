-- GRAIN: one row per DRIVER, per RACE. 13,006 rows for 1994-2026.
-- The grain is the PRIMARY KEY (race_key, driver_key), so it is enforced by the schema rather
-- than merely intended.
--
-- source_result_id does two jobs:
--   1. ON CONFLICT target. A run that dies after 8,000 rows re-runs to 13,006, not 21,006; and a
--      result the FIA restates weeks later (a DSQ) overwrites exactly one warehouse row.
--   2. Lineage. One hop back to f1_prod.results.result_id when a KPI looks wrong.
-- It is preferred over (race_key, driver_key) as the conflict target because surrogate keys are
-- reassigned if a dimension is ever rebuilt; the source id is stable.
--
-- race_date is the incremental watermark, carried on the fact so MAX(race_date) is a single
-- indexed table scan with no join and no dependency on dimension state at read time.
CREATE TABLE IF NOT EXISTS fact_race_result (
    -- six conformed dimension keys
    date_key              INTEGER      NOT NULL REFERENCES dim_date(date_key)               ON DELETE RESTRICT,
    race_key              INTEGER      NOT NULL REFERENCES dim_race(race_key)               ON DELETE RESTRICT,
    driver_key            INTEGER      NOT NULL REFERENCES dim_driver(driver_key)           ON DELETE RESTRICT,
    constructor_key       INTEGER      NOT NULL REFERENCES dim_constructor(constructor_key) ON DELETE RESTRICT,
    circuit_key           INTEGER      NOT NULL REFERENCES dim_circuit(circuit_key)         ON DELETE RESTRICT,
    status_key            INTEGER      NOT NULL REFERENCES dim_status(status_key)           ON DELETE RESTRICT,

    -- lineage and audit
    source_result_id      INTEGER      NOT NULL UNIQUE,
    race_date             DATE         NOT NULL,

    -- measures
    points                NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (points >= 0),
    laps_completed        SMALLINT     NOT NULL DEFAULT 0 CHECK (laps_completed >= 0),
    grid_position         SMALLINT     NOT NULL CHECK (grid_position >= 0),   -- 0 = pit-lane start
    finish_position       SMALLINT     CHECK (finish_position > 0),           -- NULL if not classified
    positions_gained      SMALLINT,                                           -- NULL twice over, see below
    race_time_ms          BIGINT,
    fastest_lap_time_ms   BIGINT,
    fastest_lap_speed_kph NUMERIC(6,3),

    -- one deliberate denormalisation: carried from qualifying so that
    -- quali_position - grid_position ("grid penalties applied") is a single-table read.
    quali_position        SMALLINT     CHECK (quali_position > 0),

    -- pre-computed flags: the reason each KPI card is a single scan with no CASE expression,
    -- and the reason cross-era comparison works at all
    is_winner             BOOLEAN      NOT NULL DEFAULT FALSE,
    is_podium             BOOLEAN      NOT NULL DEFAULT FALSE,
    is_points_finish      BOOLEAN      NOT NULL DEFAULT FALSE,
    is_dnf                BOOLEAN      NOT NULL DEFAULT FALSE,
    is_pole_start         BOOLEAN      NOT NULL DEFAULT FALSE,
    is_fastest_lap        BOOLEAN      NOT NULL DEFAULT FALSE,
    is_pitlane_start      BOOLEAN      NOT NULL DEFAULT FALSE,

    PRIMARY KEY (race_key, driver_key)
);

-- Additivity is recorded here because it tells the dashboard author which aggregation is legal.
COMMENT ON COLUMN fact_race_result.points                IS 'ADDITIVE, but within one points_era only -- the scoring system changed four times across 1994-2026.';
COMMENT ON COLUMN fact_race_result.laps_completed        IS 'ADDITIVE.';
COMMENT ON COLUMN fact_race_result.positions_gained      IS 'ADDITIVE. DERIVED grid_position - finish_position; NULL for DNFs and for the 68 pit-lane starts. AVG() ignores NULL, so the KPI stays correct with no dashboard filter.';
COMMENT ON COLUMN fact_race_result.grid_position         IS 'SEMI-ADDITIVE: AVG only, never SUM. Summing positions is meaningless. 0 = pit-lane start.';
COMMENT ON COLUMN fact_race_result.finish_position       IS 'SEMI-ADDITIVE: AVG only, never SUM. NULL exactly when the driver was not classified.';
COMMENT ON COLUMN fact_race_result.quali_position        IS 'SEMI-ADDITIVE: AVG only. Denormalised from qualifying; NULL for the result rows with no qualifying row, overwhelmingly pre-2003.';
COMMENT ON COLUMN fact_race_result.race_time_ms          IS 'NON-ADDITIVE: cumulative race time, comparable only within one race.';
COMMENT ON COLUMN fact_race_result.fastest_lap_time_ms   IS 'NON-ADDITIVE. 2004+ only -- see dim_race.has_fastest_lap_data.';
COMMENT ON COLUMN fact_race_result.fastest_lap_speed_kph IS 'NON-ADDITIVE. 2004+ only.';
COMMENT ON COLUMN fact_race_result.source_result_id      IS 'Lineage to f1_prod.results.result_id, and the ON CONFLICT target that makes the load idempotent.';
COMMENT ON COLUMN fact_race_result.race_date             IS 'Audit / incremental watermark. Denormalised so MAX(race_date) needs no join.';
COMMENT ON COLUMN fact_race_result.is_pitlane_start      IS 'DERIVED grid_position = 0. Retains the 68 pit-lane starts that positions_gained excludes.';
