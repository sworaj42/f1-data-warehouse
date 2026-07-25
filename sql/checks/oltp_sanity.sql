-- OLTP sanity checks for f1_prod. Run in DBeaver / psql against f1_prod.
-- Two result sets: (1) row counts, (2) integrity checks (n = 0 means PASS).

-- ============================================================
-- 1. Row counts
-- ============================================================
SELECT 'circuits'     AS table_name, count(*) AS rows FROM circuits
UNION ALL SELECT 'drivers',       count(*) FROM drivers
UNION ALL SELECT 'constructors',  count(*) FROM constructors
UNION ALL SELECT 'statuses',      count(*) FROM statuses
UNION ALL SELECT 'races',         count(*) FROM races
UNION ALL SELECT 'results',       count(*) FROM results
UNION ALL SELECT 'qualifying',    count(*) FROM qualifying
ORDER BY table_name;

-- ============================================================
-- 2. Integrity checks -- every row here should show n_violations = 0
--    (except the two WARN rows, which can be non-zero for legitimate reasons)
-- ============================================================
SELECT check_name, severity, n_violations,
       CASE WHEN n_violations = 0 THEN 'PASS'
            ELSE severity END AS status
FROM (
    -- FAIL: two classified drivers cannot share a finishing position in one race
    SELECT 'dup_finish_position_per_race' AS check_name, 'FAIL' AS severity,
           (SELECT count(*) FROM (
               SELECT race_id FROM results
               WHERE finish_position IS NOT NULL
               GROUP BY race_id, finish_position HAVING count(*) > 1) x) AS n_violations

    -- WARN: source genuinely duplicates grid positions (2015 grid penalties); stored faithfully
    UNION ALL SELECT 'dup_grid_position_per_race', 'WARN',
           (SELECT count(*) FROM (
               SELECT race_id FROM results
               WHERE grid_position <> 0
               GROUP BY race_id, grid_position HAVING count(*) > 1) x)

    -- FAIL: position_order (classification order) is unique per race
    UNION ALL SELECT 'dup_position_order_per_race', 'FAIL',
           (SELECT count(*) FROM (
               SELECT race_id FROM results
               GROUP BY race_id, position_order HAVING count(*) > 1) x)

    -- WARN: source duplicates quali positions when times are deleted/DSQ'd and not renumbered
    UNION ALL SELECT 'dup_quali_position_per_race', 'WARN',
           (SELECT count(*) FROM (
               SELECT race_id FROM qualifying
               GROUP BY race_id, quali_position HAVING count(*) > 1) x)

    -- FAIL: every race must have at least one result row
    UNION ALL SELECT 'races_without_results', 'FAIL',
           (SELECT count(*) FROM races r
            WHERE NOT EXISTS (SELECT 1 FROM results re WHERE re.race_id = r.race_id))

    -- FAIL: points can never be negative (also enforced by CHECK; verify anyway)
    UNION ALL SELECT 'negative_points', 'FAIL',
           (SELECT count(*) FROM results WHERE points < 0)

    -- FAIL: a classified finisher (numeric position_text) should carry a finish_position
    UNION ALL SELECT 'classified_missing_finish_pos', 'FAIL',
           (SELECT count(*) FROM results
            WHERE position_text ~ '^[0-9]+$' AND finish_position IS NULL)

    -- WARN: reached Q3 but no Q2 time recorded (rare but can be legitimate, e.g. wet sessions)
    UNION ALL SELECT 'q3_without_q2_time', 'WARN',
           (SELECT count(*) FROM qualifying WHERE q3_ms IS NOT NULL AND q2_ms IS NULL)

    -- WARN: races carrying no qualifying rows at all (older seasons, cancelled sessions)
    UNION ALL SELECT 'races_without_qualifying', 'WARN',
           (SELECT count(*) FROM races r
            WHERE NOT EXISTS (SELECT 1 FROM qualifying q WHERE q.race_id = r.race_id))
) checks
ORDER BY (n_violations = 0), severity, check_name;
