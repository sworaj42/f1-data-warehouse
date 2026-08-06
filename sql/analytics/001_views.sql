-- Analytics layer. Every query the dashboard runs lives here; the dashboard itself only ever
-- issues SELECT * FROM v_<name>. All aggregation happens in the warehouse, which is the point of
-- having built one -- pulling fact rows into pandas and calling groupby().sum() would say the
-- warehouse was not trusted to do its job.
--
-- Six views, not the five the spec lists. The spec sources both the per-season KPI cards and a
-- per-constructor stacked bar from v_season_kpis, but those are two different grains and one view
-- cannot serve both without a rollup in pandas -- which the spec's own design rules forbid. So the
-- constructor grain is split out into v_constructor_season.
--
-- Every view excludes season = -1: that is the dim_race unknown member, present so a fact never
-- needs a NULL FK, and it is not a season.
--
-- CREATE OR REPLACE throughout, so re-applying this file is safe. Note that run_migrations.py
-- skips files already in schema_migrations -- while iterating on view SQL, apply this file
-- directly with psql rather than through the runner.


-- Season at a glance. Grain: one row per season (33 rows).
-- Feeds the five KPI cards. Every rate is a SUM over a pre-computed boolean flag, so this is a
-- single scan of the fact with no CASE expression anywhere -- which is the whole reason the flags
-- are computed at load time rather than here.
CREATE OR REPLACE VIEW v_season_kpis AS
SELECT
    r.season,
    r.points_era,
    COUNT(DISTINCT f.race_key)                          AS races,
    COUNT(DISTINCT f.driver_key)                        AS drivers,
    COUNT(DISTINCT f.constructor_key)                   AS constructors,
    COUNT(*)                                            AS result_rows,
    SUM(f.is_winner::INT)                               AS wins_recorded,
    ROUND(100.0 * SUM(f.is_dnf::INT) / COUNT(*), 1)     AS dnf_rate_pct,
    -- AVG ignores NULL, and positions_gained is NULL exactly for DNFs and pit-lane starts, so this
    -- is correct with no filter in the dashboard query.
    ROUND(AVG(f.positions_gained), 2)                   AS avg_positions_gained,
    -- NULLIF guards 1994-2005 seasons in which no fact row carries is_pole_start (grid_position
    -- comes from the source and a season with no recorded pole would divide by zero).
    ROUND(100.0 * SUM((f.is_pole_start AND f.is_winner)::INT)
                / NULLIF(SUM(f.is_pole_start::INT), 0), 1) AS pole_to_win_pct
FROM fact_race_result f
JOIN dim_race r ON r.race_key = f.race_key
WHERE r.season <> -1
GROUP BY r.season, r.points_era;

COMMENT ON VIEW v_season_kpis IS 'Grain: one row per season. Backs the five KPI cards. points_era is carried so the dashboard can caption that raw points are comparable within one era only.';


-- Constructor performance by season. Grain: one row per season per constructor.
-- Backs the stacked-bar "is the sport competitive or dominated?" chart.
-- points is SUM'd here but is only comparable WITHIN a points_era -- the scoring system changed
-- four times across 1994-2026, so points_era is selected alongside it as a guard the chart must
-- respect. wins/podiums are flag sums and are comparable across all 33 seasons.
CREATE OR REPLACE VIEW v_constructor_season AS
SELECT
    r.season,
    r.points_era,
    c.constructor_key,
    c.name                          AS constructor_name,
    c.last_season,
    COUNT(DISTINCT f.race_key)      AS races,
    COUNT(*)                        AS entries,
    SUM(f.points)                   AS points,
    SUM(f.is_winner::INT)           AS wins,
    SUM(f.is_podium::INT)           AS podiums,
    SUM(f.is_dnf::INT)              AS dnfs
FROM fact_race_result f
JOIN dim_race        r ON r.race_key        = f.race_key
JOIN dim_constructor c ON c.constructor_key = f.constructor_key
WHERE r.season <> -1
GROUP BY r.season, r.points_era, c.constructor_key, c.name, c.last_season;

COMMENT ON VIEW v_constructor_season IS 'Grain: season x constructor. Split out of v_season_kpis because the KPI cards need a season grain and the stacked bar needs a constructor grain; one view cannot be both without aggregating in pandas.';


-- Championship progression. Grain: one row per driver per race. THE CENTREPIECE.
-- cumulative_points is the sliding-window analytic the star schema was designed to make cheap:
-- one pass over the fact, no self-join, no correlated subquery.
--
-- Two CTEs rather than one because a window function cannot be nested inside another --
-- championship_position ranks on cumulative_points, so the cumulative sum must already exist as a
-- column before the RANK() can reference it.
--
-- season_round_label lives here rather than on dim_race: it is a display string, and the warehouse
-- design dropped it from the dimension on the grounds that a column exists only because a named
-- query needs it. This is that query.
CREATE OR REPLACE VIEW v_championship_progression AS
WITH per_race AS (
    -- No GROUP BY: the fact grain is already one driver, one race, enforced by its primary key.
    SELECT
        r.season,
        r.round,
        r.race_name,
        f.race_date,
        d.driver_key,
        d.full_name AS driver_name,
        c.name      AS constructor_name,
        f.points
    FROM fact_race_result f
    JOIN dim_race        r ON r.race_key        = f.race_key
    JOIN dim_driver      d ON d.driver_key      = f.driver_key
    JOIN dim_constructor c ON c.constructor_key = f.constructor_key
    WHERE r.season <> -1
),
cumulative AS (
    SELECT
        per_race.*,
        SUM(points) OVER (
            PARTITION BY season, driver_key
            ORDER BY round
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_points
    FROM per_race
)
SELECT
    season,
    round,
    season::TEXT || ' R' || LPAD(round::TEXT, 2, '0') AS season_round_label,
    race_name,
    race_date,
    driver_key,
    driver_name,
    constructor_name,
    points,
    cumulative_points,
    -- RANK, not ROW_NUMBER: drivers genuinely tie on points mid-season and inventing an order
    -- between them would be a fabricated fact.
    RANK() OVER (PARTITION BY season, round ORDER BY cumulative_points DESC) AS championship_position
FROM cumulative;

COMMENT ON VIEW v_championship_progression IS 'Grain: driver x race. cumulative_points is SUM() OVER (PARTITION BY season, driver ORDER BY round) -- the window function the star schema exists to make cheap. Reconcile against a known season final standings.';


-- Rolling driver form. Grain: one row per driver per race, ordered by date ACROSS season
-- boundaries -- a driver's form does not reset on 1 January.
--
-- finish_position is NULL for every DNF, so AVG() skips those rows. That is correct but it can
-- flatter a driver: four DNFs in the window leaves the "5-race average" resting on one race. Hence
-- races_in_window, which counts the non-NULL rows in the same frame and lets the chart say so.
-- Without it the number is not wrong, it is just quietly unfalsifiable.
CREATE OR REPLACE VIEW v_driver_rolling_form AS
SELECT
    d.driver_key,
    d.full_name AS driver_name,
    r.season,
    r.round,
    r.race_name,
    f.race_date,
    f.finish_position,
    f.points,
    f.is_dnf,
    ROUND(AVG(f.finish_position) OVER w, 2) AS rolling_avg_finish,
    SUM(f.points)            OVER w         AS rolling_points_5,
    COUNT(f.finish_position) OVER w         AS races_in_window
FROM fact_race_result f
JOIN dim_race   r ON r.race_key   = f.race_key
JOIN dim_driver d ON d.driver_key = f.driver_key
WHERE r.season <> -1
-- round is the tiebreak: ROWS BETWEEN needs a total order, and race_date alone is not guaranteed
-- to be unique across the whole 33-season range.
WINDOW w AS (
    PARTITION BY d.driver_key
    ORDER BY f.race_date, r.round
    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
);

COMMENT ON VIEW v_driver_rolling_form IS 'Grain: driver x race. ROWS BETWEEN 4 PRECEDING AND CURRENT ROW moving average. races_in_window reports how many of the five actually carry a finish_position, since DNFs are NULL.';


-- Reliability over 33 seasons. Grain: one row per season per status_group.
-- The project's headline finding: the 1990s field failed to finish 46% of the time, the 2020s 13%.
--
-- pct_of_season nests an aggregate inside a window -- SUM(COUNT(*)) OVER (PARTITION BY season) --
-- so the per-season denominator comes from the same single pass. The obvious alternative is a
-- self-join back to a per-season count, which reads the fact twice for no benefit.
--
-- 109 distinct status strings would be an unusable chart axis; dim_status.status_group collapses
-- them to 5 at load time, which is exactly what this axis needs.
CREATE OR REPLACE VIEW v_reliability_trend AS
SELECT
    r.season,
    r.points_era,
    s.status_group,
    COUNT(*)                                   AS status_rows,
    SUM(COUNT(*)) OVER (PARTITION BY r.season) AS season_rows,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY r.season), 1) AS pct_of_season
FROM fact_race_result f
JOIN dim_race   r ON r.race_key   = f.race_key
JOIN dim_status s ON s.status_key = f.status_key
WHERE r.season <> -1
GROUP BY r.season, r.points_era, s.status_group;

COMMENT ON VIEW v_reliability_trend IS 'Grain: season x status_group. Aggregate nested in a window gives the per-season denominator in one pass. Backs the stacked-area reliability chart.';


-- Qualifying pace against race outcome. Grain: one row per driver per race.
-- THIS IS THE VIEW THAT NEEDS TWO FACT TABLES. It joins fact_race_result to fact_qualifying on
-- (race_key, driver_key) -- their shared grain -- and reaches four conformed dimensions on the way.
-- A merged single-fact design could only answer this with a self-join over a table twice the size.
--
-- INNER JOIN, deliberately: it drops the result rows with no qualifying row (overwhelmingly the 83
-- pre-2003 races the source has no qualifying data for) and the 7 qualifying rows whose driver
-- never started. Both sides are required for the comparison to mean anything, so ~11,100 rows of
-- the 13,006 is the honest population, not a loss.
CREATE OR REPLACE VIEW v_quali_vs_race AS
SELECT
    r.season,
    r.round,
    r.race_name,
    r.has_quali_knockout,
    ci.name    AS circuit_name,
    ci.country AS circuit_country,
    d.driver_key,
    d.full_name AS driver_name,
    c.name      AS constructor_name,
    q.quali_position,
    frr.grid_position,
    frr.finish_position,
    frr.positions_gained,
    -- Grid penalties applied between qualifying and the grid. fact_race_result carries
    -- quali_position denormalised precisely so this is available without joining qualifying at
    -- all; here we are already joined, so the qualifying fact is the authoritative side.
    q.quali_position - frr.grid_position AS grid_penalty,
    q.gap_to_pole_ms,
    q.reached_q2,
    q.reached_q3,
    frr.is_dnf,
    s.status_group
FROM fact_race_result frr
JOIN fact_qualifying q ON q.race_key   = frr.race_key
                      AND q.driver_key = frr.driver_key
JOIN dim_race        r  ON r.race_key        = frr.race_key
JOIN dim_driver      d  ON d.driver_key      = frr.driver_key
JOIN dim_constructor c  ON c.constructor_key = frr.constructor_key
JOIN dim_circuit     ci ON ci.circuit_key    = frr.circuit_key
JOIN dim_status      s  ON s.status_key      = frr.status_key
WHERE r.season <> -1;

COMMENT ON VIEW v_quali_vs_race IS 'Grain: driver x race, both facts joined on (race_key, driver_key). The concrete payoff of the fact-constellation design. INNER JOIN drops results with no qualifying row and qualifiers who did not start.';
