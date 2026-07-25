-- Reference table. Extracted from the repeated Circuit object in the API response.
-- 3NF: circuit_country is transitively dependent on the circuit, not on a result row.
CREATE TABLE IF NOT EXISTS circuits (
    circuit_id  SERIAL       PRIMARY KEY,
    circuit_ref VARCHAR(50)  NOT NULL UNIQUE,          -- API natural key, e.g. monza
    name        VARCHAR(120) NOT NULL,
    locality    VARCHAR(100),
    country     VARCHAR(100),
    latitude    NUMERIC(9,6) CHECK (latitude  BETWEEN  -90 AND  90),
    longitude   NUMERIC(9,6) CHECK (longitude BETWEEN -180 AND 180)
);
