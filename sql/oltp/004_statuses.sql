-- Reference table. ~140 distinct finishing-status strings behind a numeric FK.
-- status_code is the API statusId; nullable because a status text can be discovered
-- from a result row before the /status endpoint assigns it a code.
CREATE TABLE IF NOT EXISTS statuses (
    status_id   SERIAL      PRIMARY KEY,
    status_code INTEGER     UNIQUE,                     -- API statusId
    status_text VARCHAR(80) NOT NULL UNIQUE             -- e.g. Finished, +1 Lap, Gearbox
);
