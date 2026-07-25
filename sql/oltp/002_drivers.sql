-- Reference table. Extracted from the repeated Driver object in every result/qualifying row.
CREATE TABLE IF NOT EXISTS drivers (
    driver_id        SERIAL      PRIMARY KEY,
    driver_ref       VARCHAR(50) NOT NULL UNIQUE,      -- e.g. hamilton
    permanent_number SMALLINT    CHECK (permanent_number BETWEEN 0 AND 99),  -- NULL before 2014
    code             CHAR(3),                          -- NULL for older drivers, e.g. HAM
    forename         VARCHAR(60) NOT NULL,
    surname          VARCHAR(60) NOT NULL,
    date_of_birth    DATE,
    nationality      VARCHAR(60)
);
