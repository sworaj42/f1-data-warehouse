-- Transaction table. Grain: one row per driver per race.
CREATE TABLE IF NOT EXISTS results (
    result_id             SERIAL      PRIMARY KEY,
    race_id               INTEGER     NOT NULL REFERENCES races(race_id)               ON DELETE CASCADE,
    driver_id             INTEGER     NOT NULL REFERENCES drivers(driver_id)           ON DELETE RESTRICT,
    constructor_id        INTEGER     NOT NULL REFERENCES constructors(constructor_id) ON DELETE RESTRICT,
    status_id             INTEGER     NOT NULL REFERENCES statuses(status_id)          ON DELETE RESTRICT,
    car_number            SMALLINT,
    grid_position         SMALLINT    NOT NULL CHECK (grid_position >= 0),   -- 0 = pit lane start
    finish_position       SMALLINT,                                          -- NULL if not classified
    position_text         VARCHAR(5)  NOT NULL,                              -- raw API value: 1, R, D, W
    position_order        SMALLINT    NOT NULL,                              -- always populated, for ordering
    points                NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (points >= 0),
    laps_completed        SMALLINT    NOT NULL DEFAULT 0 CHECK (laps_completed >= 0),
    race_time_ms          BIGINT,                                            -- NULL unless classified finisher
    fastest_lap_number    SMALLINT,
    fastest_lap_rank      SMALLINT,
    fastest_lap_time_ms   BIGINT,
    fastest_lap_speed_kph NUMERIC(6,3),
    UNIQUE (race_id, driver_id),
    -- finish_position is populated exactly when the driver was classified (numeric position_text).
    -- Enforced in the schema so an unclassified row can never carry a finishing position, and vice versa.
    CONSTRAINT chk_results_finish CHECK (
        (position_text ~ '^[0-9]+$' AND finish_position IS NOT NULL)
        OR (position_text !~ '^[0-9]+$' AND finish_position IS NULL)
    )
);
