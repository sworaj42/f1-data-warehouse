-- Participating drivers only: 177 of the 881 in f1_prod. The excluded rows are drivers whose
-- whole career falls outside the 1994-2026 warehouse scope -- the API's /drivers endpoint is
-- all-time (1950+) -- so they could never join a fact here.
--
-- There is deliberately no debut_season. f1_prod starts at 1994, so MIN(season) reports 1994 for
-- the 46 drivers who had already raced before then (Schumacher really debuted in 1991), and no
-- view needs it.
-- The -1 unknown member is seeded by etl/pipeline/load.py, not here: migrations are
-- structure only, so a TRUNCATE + reload restores every row the warehouse needs.
CREATE TABLE IF NOT EXISTS dim_driver (
    driver_key       SERIAL       PRIMARY KEY,
    driver_ref       VARCHAR(50)  NOT NULL UNIQUE,      -- natural key, e.g. hamilton; the ON CONFLICT target
    forename         VARCHAR(60)  NOT NULL,
    surname          VARCHAR(60)  NOT NULL,
    full_name        VARCHAR(121) NOT NULL,             -- DERIVED: forename || ' ' || surname (60 + 1 + 60)
    code             CHAR(3),                           -- NULL for pre-2014 drivers, e.g. HAM
    permanent_number SMALLINT     CHECK (permanent_number BETWEEN 0 AND 99),  -- NULL before 2014
    date_of_birth    DATE,
    nationality      VARCHAR(60)
);

-- full_name is redundant on purpose: one label column for every chart, filter and search, with
-- the concatenation rule fixed in one place rather than retyped per view.
COMMENT ON COLUMN dim_driver.full_name IS 'DERIVED forename || '' '' || surname. Denormalised for chart labels and search.';
