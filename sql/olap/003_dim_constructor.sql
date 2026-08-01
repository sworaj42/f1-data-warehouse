-- Participating constructors only: 49 of the 214 in f1_prod, same scope rule as dim_driver.
--
-- last_season answers "is this team still active?" -- 11 of the 49 raced in 2026. It is safe to
-- derive because the right-hand edge of the data is real.
-- There is deliberately no first_season: the left-hand edge is a scope boundary, not a fact, so
-- MIN(season) would report 1994 for Ferrari (really 1950), McLaren (1966), Williams (1977) and
-- 11 other teams.
-- The -1 unknown member is seeded by etl/pipeline/load.py, not here: migrations are
-- structure only, so a TRUNCATE + reload restores every row the warehouse needs.
CREATE TABLE IF NOT EXISTS dim_constructor (
    constructor_key SERIAL       PRIMARY KEY,
    constructor_ref VARCHAR(50)  NOT NULL UNIQUE,      -- natural key, e.g. red_bull
    name            VARCHAR(100) NOT NULL,
    nationality     VARCHAR(60),
    last_season     SMALLINT     CHECK (last_season BETWEEN 1950 AND 2100)  -- DERIVED, NULL only for the unknown member
);

COMMENT ON COLUMN dim_constructor.last_season IS 'DERIVED MAX(season) in which the team recorded a result. Drives the active-vs-defunct filter.';
