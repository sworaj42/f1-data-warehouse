-- Event table. UNIQUE (season, round) is the real-world business key;
-- race_id is a convenience surrogate for join ergonomics.
CREATE TABLE IF NOT EXISTS races (
    race_id    SERIAL       PRIMARY KEY,
    season     SMALLINT     NOT NULL CHECK (season BETWEEN 1950 AND 2100),
    round      SMALLINT     NOT NULL CHECK (round  BETWEEN 1 AND 30),
    race_name  VARCHAR(120) NOT NULL,
    race_date  DATE         NOT NULL,
    race_time  TIME,                                    -- NULL for older races
    qualifying_date DATE,                               -- from /races Qualifying.date; day before the race, NULL for older seasons
    circuit_id INTEGER      NOT NULL REFERENCES circuits(circuit_id) ON DELETE RESTRICT,
    UNIQUE (season, round)
);
