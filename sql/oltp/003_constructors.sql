-- Reference table. Extracted from the repeated Constructor object.
CREATE TABLE IF NOT EXISTS constructors (
    constructor_id  SERIAL       PRIMARY KEY,
    constructor_ref VARCHAR(50)  NOT NULL UNIQUE,      -- e.g. red_bull
    name            VARCHAR(100) NOT NULL,
    nationality     VARCHAR(60)
);
