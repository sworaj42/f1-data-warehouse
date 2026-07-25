-- Transaction table. Grain: one row per driver per race.
-- q2_ms / q3_ms are NULL by rule (a driver eliminated in Q1 never sets a Q2 time) -- absence, not missing data.
CREATE TABLE IF NOT EXISTS qualifying (
    qualifying_id  SERIAL   PRIMARY KEY,
    race_id        INTEGER  NOT NULL REFERENCES races(race_id)               ON DELETE CASCADE,
    driver_id      INTEGER  NOT NULL REFERENCES drivers(driver_id)           ON DELETE RESTRICT,
    constructor_id INTEGER  NOT NULL REFERENCES constructors(constructor_id) ON DELETE RESTRICT,
    car_number     SMALLINT,
    quali_position SMALLINT NOT NULL CHECK (quali_position > 0),
    q1_ms          BIGINT,                                                   -- NULL if no time set
    q2_ms          BIGINT,                                                   -- NULL if eliminated in Q1
    q3_ms          BIGINT,                                                   -- NULL if eliminated in Q2
    UNIQUE (race_id, driver_id)
);
