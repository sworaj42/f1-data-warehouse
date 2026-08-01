-- Participating circuits only: 43 of the 78 in f1_prod, same scope rule as dim_driver.
--
-- No continent column. The API does not carry one, none of the five views needs it, and deriving
-- it would mean hand-mapping the 30 country strings in scope -- three of which are genuinely
-- arguable (Russia, Turkey, Azerbaijan) and four non-standard (UK, USA, UAE, Korea).
-- The -1 unknown member is seeded by etl/pipeline/load.py, not here: migrations are
-- structure only, so a TRUNCATE + reload restores every row the warehouse needs.
CREATE TABLE IF NOT EXISTS dim_circuit (
    circuit_key SERIAL       PRIMARY KEY,
    circuit_ref VARCHAR(50)  NOT NULL UNIQUE,          -- natural key, e.g. monza
    name        VARCHAR(120) NOT NULL,
    locality    VARCHAR(100),
    country     VARCHAR(100),
    latitude    NUMERIC(9,6) CHECK (latitude  BETWEEN  -90 AND  90),
    longitude   NUMERIC(9,6) CHECK (longitude BETWEEN -180 AND 180)
);
