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
-- skips files already in schema_migrations -- while iterating on view SQL, delete the ledger row
-- or apply this file directly with psql rather than through the runner.
--
-- The DROP block below is load-bearing, not defensive tidying. CREATE OR REPLACE VIEW can only
-- APPEND columns: it refuses to rename or remove one ("cannot change name of view column"). So a
-- file that only ever uses OR REPLACE is re-runnable exactly until the first column is renamed,
-- and then it fails. Dropping first makes the file genuinely re-runnable.
--
-- Reverse dependency order, and deliberately WITHOUT CASCADE -- v_driver_race_craft is built on
-- v_quali_vs_race, so the order matters, and if anything else ever comes to depend on these the
-- migration should fail loudly rather than silently drop it.
DROP VIEW IF EXISTS v_driver_race_craft;
DROP VIEW IF EXISTS v_quali_vs_race;
DROP VIEW IF EXISTS v_reliability_trend;
DROP VIEW IF EXISTS v_driver_rolling_form;
DROP VIEW IF EXISTS v_championship_progression;
DROP VIEW IF EXISTS v_constructor_season;
DROP VIEW IF EXISTS v_season_kpis;


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
    -- NOT a count of wins: SUM(is_winner) is identical to races in all 33 seasons, because every
    -- race has exactly one winner. It was a KPI card until that was measured, and it told nobody
    -- anything. How many DIFFERENT drivers won is the question that has an answer -- 8 in 2003,
    -- 3 in 2023 -- and it counts a flag, so it is comparable across every era.
    COUNT(DISTINCT f.driver_key) FILTER (WHERE f.is_winner) AS distinct_winners,
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


-- Race craft: who actually gains places, once you subtract the places their grid slot hands them.
-- Grain: one row per driver per season.
--
-- WHY THIS EXISTS. Plotting places gained directly is close to meaningless, and it is worth being
-- able to say why. Averaged over 2020-2026 the places gained by grid slot is perfectly monotonic:
--
--     qualified P1  -> -1.2      qualified P10 -> +0.3      qualified P20 -> +5.3
--
-- It could not be otherwise: pole cannot gain a place and last cannot lose one. So a raw "places
-- gained" ranking mostly sorts drivers by how slow their car is in qualifying, and a scatter of
-- quali against finish mostly draws that constraint rather than anything about racing.
--
-- Subtracting the average gain FOR THAT GRID SLOT removes it. What is left is the part the driver
-- and the team are responsible for. Verified on the loaded warehouse: Perez 2026 gains +4.14
-- places a race, which looks outstanding until par for his grid slots turns out to be +3.66,
-- leaving +0.49. Hamilton is the mirror image -- he qualifies well, so par for his slots is
-- NEGATIVE (-0.96), and he still gains, which is +1.76 and top of the field.
--
-- Built on v_quali_vs_race rather than on the facts, so the two-fact join is defined once and this
-- view inherits it.
CREATE OR REPLACE VIEW v_driver_race_craft AS
WITH classified AS (
    -- A DNF has no finishing position, so there is no gain or loss to measure.
    SELECT
        season,
        driver_key,
        driver_name,
        quali_position,
        quali_position - finish_position AS places_gained
    FROM v_quali_vs_race
    WHERE finish_position IS NOT NULL
),
expected AS (
    -- Par for each grid slot, computed WITHIN a season. Field size and the circuit mix are
    -- constant inside a season and emphatically not across 33 of them -- 1994 had 26 entries
    -- against 20 today, so P20 means something different in each.
    SELECT season, quali_position, AVG(places_gained) AS expected_gain
    FROM classified
    GROUP BY season, quali_position
)
SELECT
    c.season,
    c.driver_key,
    c.driver_name,
    COUNT(*)                                          AS races,
    ROUND(AVG(c.places_gained), 2)                    AS avg_places_gained,
    ROUND(AVG(e.expected_gain), 2)                    AS expected_places_gained,
    ROUND(AVG(c.places_gained - e.expected_gain), 2)  AS places_vs_expected
FROM classified c
JOIN expected e USING (season, quali_position)
-- No constructor_name: drivers change team mid-season, so it is not functionally dependent on
-- (season, driver) and carrying it here would silently duplicate rows.
GROUP BY c.season, c.driver_key, c.driver_name;

COMMENT ON VIEW v_driver_race_craft IS 'Grain: season x driver. places_vs_expected is places gained minus the season average for that grid slot, which removes the arithmetic that pole cannot gain and last cannot lose. The residuals sum to zero within a season by construction -- a self-checking property.';
