-- ============================================================================
-- БС-5 — Косвенное владение через цепочку ЮЛ (Предполагаемый БС, балл 3)
-- Источник: AFM_2_1_TEST.AFM_2_1_5_1; госсобственность исключается по AFM_2_1.AFM_2_1_8.
-- Результат: AFM_6_TEST.AFM_6_1_11
--
-- Цепочка владения раскручивается на десять уровней: доля каждого следующего
-- уровня умножается на долю предыдущего. Физическое лицо в конце цепочки
-- признаётся предполагаемым БС, если накопленная доля достигла 25%.
-- Рекурсивных запросов в ClickHouse нет, поэтому уровни развёрнуты явно.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_11 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_11
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH
max_date AS (SELECT max(_actual_date) AS dt FROM AFM_2_1_TEST.AFM_2_1_5_1),
max_date_dir AS (SELECT max(_actual_date) AS dt FROM AFM_2_1_TEST.AFM_2_1_6_1),
gos AS (
    SELECT DISTINCT taxpayer_iin_bin
    FROM AFM_2_1.AFM_2_1_8
    WHERE ownership_type LIKE '%Государственная%'
      AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1.AFM_2_1_8)
),
founders AS (
    SELECT
        taxpayer_iin_bin,
        founder_iin_bin,
        toFloat64OrZero(replaceAll(replaceAll(COALESCE(share_percentage,'0'),',','.'),'%','')) AS share,
        founder_last_name,
        founder_first_name,
        founder_part_name,
        founder_ul_name
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT dt FROM max_date)
      AND taxpayer_iin_bin != ''
      AND founder_iin_bin != ''
      AND taxpayer_iin_bin != founder_iin_bin
      AND taxpayer_iin_bin NOT IN (SELECT taxpayer_iin_bin FROM gos)
),
lvl1 AS (
    SELECT taxpayer_iin_bin AS root_bin, founder_iin_bin AS ul_bin, share AS acc_share
    FROM founders
    WHERE left(right(founder_iin_bin,8),1) IN ('4','5')
),
lvl2 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl1 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl3 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl2 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl4 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl3 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl5 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl4 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl6 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl5 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl7 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl6 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl8 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl7 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl9 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl8 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
lvl10 AS (SELECT l.root_bin AS root_bin, f.founder_iin_bin AS ul_bin, l.acc_share * f.share / 100.0 AS acc_share
    FROM lvl9 AS l JOIN founders AS f ON l.ul_bin = f.taxpayer_iin_bin
    WHERE left(right(f.founder_iin_bin,8),1) IN ('4','5') AND l.root_bin != f.founder_iin_bin),
all_levels AS (
    SELECT root_bin, ul_bin, acc_share FROM lvl1
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl2
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl3
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl4
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl5
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl6
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl7
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl8
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl9
    UNION ALL SELECT root_bin, ul_bin, acc_share FROM lvl10
)
SELECT DISTINCT
    a.root_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    d.employee_iin_bin AS director_iin_bin,
    f.founder_iin_bin AS benefeciary_iin_bin,
    if(right(left(f.founder_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(f.founder_iin_bin,5),1) IN ('1','2','3')
            AND right(left(f.founder_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-5' AS algorithm_code,
    3 AS priority,
    'МЮ_учредители' AS source,
    toString(today()) AS _actual_date,
    concat(
        if(COALESCE(f.founder_ul_name,'') LIKE '',
            concat(COALESCE(f.founder_last_name,''),' ',
                   COALESCE(f.founder_first_name,''),' ',
                   COALESCE(f.founder_part_name,'')),
            f.founder_ul_name),
        ', накопленная доля: ', toString(round(a.acc_share, 2)), '%'
    ) AS dop_info
FROM all_levels AS a
JOIN founders AS f ON a.ul_bin = f.taxpayer_iin_bin
    AND left(right(f.founder_iin_bin,8),1) NOT IN ('4','5')
    AND f.founder_iin_bin != a.root_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT dt FROM max_date)
) AS b ON a.root_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT dt FROM max_date_dir)
) AS d ON a.root_bin = d.taxpayer_iin_bin
WHERE a.acc_share >= 25.0
  AND f.founder_iin_bin != '';
