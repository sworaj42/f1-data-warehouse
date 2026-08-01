-- Event dimension: one row per race that has actually run (611 for 1994-2026; scheduled-but-unrun
-- 2026 rounds are held back in f1_prod and never reach here).
--
-- No circuit_key here. The circuit key sits on the facts instead, so a dimension is always one
-- flat join from the fact -- duplicating it onto dim_race would snowflake the design.
--
-- The three era attributes are not decoration. Across 33 seasons the points system changed
-- underneath the data, so raw points are comparable within an era only; without these columns the
-- KPI cards and the constructor points chart are quietly wrong.
-- The -1 unknown member is seeded by etl/pipeline/load.py, not here: migrations are
-- structure only, so a TRUNCATE + reload restores every row the warehouse needs.
CREATE TABLE IF NOT EXISTS dim_race (
    race_key             SERIAL       PRIMARY KEY,
    -- -1 in season/round is the unknown member; real races are always in range.
    season               SMALLINT     NOT NULL CHECK (season = -1 OR season BETWEEN 1950 AND 2100),
    round                SMALLINT     NOT NULL CHECK (round  = -1 OR round  BETWEEN 1 AND 30),
    race_name            VARCHAR(120) NOT NULL,
    race_date            DATE         NOT NULL,
    qualifying_date      DATE,                          -- NULL for 83 pre-2003 races: source coverage, not a defect
    race_laps            SMALLINT     CHECK (race_laps >= 0),
    is_season_finale     BOOLEAN      NOT NULL DEFAULT FALSE,
    points_era           VARCHAR(9)   NOT NULL CHECK (points_era IN ('1994-2009', '2010-2018', '2019-2024', '2025+', 'Unknown')),
    has_fastest_lap_data BOOLEAN      NOT NULL DEFAULT FALSE,
    has_quali_knockout   BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (season, round)                              -- the real-world business key
);

-- race_laps is the race distance, not a sum over drivers. It is MAX(laps_completed) for the race,
-- i.e. the distance ACTUALLY run, so a red-flagged race sits below its scheduled distance -- which
-- is the correct basis for the laps_completed <= race_laps quality check. The API exposes no
-- scheduled distance.
-- It is computed in transform.py from f1_prod.results grouped by race, NOT from fact_race_result:
-- the load order is dimensions before facts, so the fact does not exist yet.
COMMENT ON COLUMN dim_race.race_laps IS 'Race distance in laps = MAX(laps_completed) for this race. Actual, not scheduled. Not a sum over drivers.';
COMMENT ON COLUMN dim_race.points_era IS 'DERIVED banding of season. Guards every points aggregation: raw points are comparable within one era only.';
COMMENT ON COLUMN dim_race.has_fastest_lap_data IS 'DERIVED season >= 2004. Fastest-lap times do not exist in the source before 2004.';
COMMENT ON COLUMN dim_race.has_quali_knockout IS 'DERIVED season >= 2006. Q1/Q2/Q3 knockout format; before that, other qualifying formats entirely.';
