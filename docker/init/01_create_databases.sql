-- Runs once, on first container init (empty volume), against POSTGRES_DB (f1_prod).
-- f1_prod already exists (POSTGRES_DB); create the warehouse DB now so nothing blocks
-- the later OLTP -> OLAP work. It stays empty until the warehouse stage.
CREATE DATABASE f1_dw;
