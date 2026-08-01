-- Junk dimension. 109 distinct finishing-status strings collapsed into 5 groups.
-- 109 statuses are unusable as a chart axis; 5 groups are exactly what the reliability trend
-- needs. Verified against live data, summing to the 13,006 fact rows:
--   Finished 5,682 (1 status) | Lapped 3,805 (17) | Mechanical DNF 1,891 (78)
--   Accident DNF 1,249 (6)    | Other 379 (7)
--
-- Only statuses that actually appear in results are loaded (109 of the 136 in f1_prod), the same
-- participating-only rule the other dimensions use.
-- The -1 unknown member is seeded by etl/pipeline/load.py, not here: migrations are
-- structure only, so a TRUNCATE + reload restores every row the warehouse needs.
CREATE TABLE IF NOT EXISTS dim_status (
    status_key    SERIAL      PRIMARY KEY,
    status_text   VARCHAR(80) NOT NULL UNIQUE,         -- natural key, e.g. Finished, +1 Lap, Gearbox
    status_code   INTEGER,                             -- API statusId; nullable, as in f1_prod
    status_group  VARCHAR(20) NOT NULL CHECK (
                      status_group IN ('Finished', 'Lapped', 'Mechanical DNF',
                                       'Accident DNF', 'Other', 'Unknown')),
    is_classified BOOLEAN     NOT NULL DEFAULT FALSE   -- DERIVED: status_group IN ('Finished','Lapped')
);

COMMENT ON COLUMN dim_status.status_group IS 'DERIVED grouping of 109 status strings into 5 analysable buckets. The reliability-trend chart axis.';
COMMENT ON COLUMN dim_status.is_classified IS 'DERIVED status_group IN (Finished, Lapped) -- 9,487 rows. The complement is the DNF population.';
