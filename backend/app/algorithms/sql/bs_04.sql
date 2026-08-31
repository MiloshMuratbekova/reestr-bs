-- ============================================================================
-- БС-4 — Учредители при признаке некорректности 3 (Предполагаемый БС, балл 3)
-- Источник: AFM_2_1_TEST.AFM_2_1_5_1.
-- Результат: AFM_6_TEST.AFM_6_1_10
--
-- Признак некорректности 3: сумма долей учредителей больше нуля, но не
-- попадает в диапазон 99.9–100.1. Доля каждого пересчитывается относительно
-- фактической суммы долей компании, и порог 25% применяется уже к ней.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_10 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_10
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT
        taxpayer_iin_bin,
        founder_iin_bin,
        founder_name,
        sum(g) AS share_per
    FROM (
        SELECT
            taxpayer_iin_bin,
            founder_iin_bin,
            founder_name,
            trunc(cast(share AS Decimal(10,2)),2) AS g
        FROM (
            SELECT
                taxpayer_iin_bin,
                founder_iin_bin,
                if(founder_ul_name LIKE '',
                    concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),
                    founder_ul_name) AS founder_name,
                replace(share_percentage,',','.') AS share
            FROM AFM_2_1_TEST.AFM_2_1_5_1
            WHERE share_percentage LIKE '%,%'
              AND share_percentage NOT LIKE ''
              AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
        ) AS a
        UNION ALL
        SELECT
            taxpayer_iin_bin,
            founder_iin_bin,
            if(founder_ul_name LIKE '',
                concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),
                founder_ul_name) AS founder_name,
            floor(cast(concat(share_percentage,'.00') AS Decimal(10,2)),2) AS g
        FROM AFM_2_1_TEST.AFM_2_1_5_1
        WHERE share_percentage NOT LIKE '%,%'
          AND share_percentage NOT LIKE '0'
          AND share_percentage NOT LIKE ''
          AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
    )
    GROUP BY taxpayer_iin_bin, founder_iin_bin, founder_name
),
table2 AS (
    SELECT
        taxpayer_iin_bin,
        sum(g) AS total_share
    FROM (
        SELECT taxpayer_iin_bin, trunc(cast(share AS Decimal(10,2)),2) AS g
        FROM (
            SELECT taxpayer_iin_bin, replace(share_percentage,',','.') AS share
            FROM AFM_2_1_TEST.AFM_2_1_5_1
            WHERE share_percentage LIKE '%,%'
              AND share_percentage NOT LIKE ''
              AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
        ) AS a
        UNION ALL
        SELECT taxpayer_iin_bin,
            floor(cast(concat(share_percentage,'.00') AS Decimal(10,2)),2) AS g
        FROM AFM_2_1_TEST.AFM_2_1_5_1
        WHERE share_percentage NOT LIKE '%,%'
          AND share_percentage NOT LIKE '0'
          AND share_percentage NOT LIKE ''
          AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
    )
    GROUP BY taxpayer_iin_bin
    HAVING total_share <> 0.00 AND (total_share < 99.9 OR total_share > 100.1)
)
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    toString(cast(b.share_per AS Decimal(10,4))
        / cast(a.total_share AS Decimal(10,4)) * 100.0000) AS share_percentage,
    d.employee_iin_bin AS director_iin_bin,
    b.founder_iin_bin AS benefeciary_iin_bin,
    if(right(left(b.founder_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(b.founder_iin_bin,5),1) IN ('1','2','3')
            AND right(left(b.founder_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-4' AS algorithm_code,
    3 AS priority,
    'МЮ_учредители' AS source,
    toString(today()) AS _actual_date,
    b.founder_name AS dop_info
FROM table2 AS a
LEFT JOIN table1 AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT *
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS d ON d.taxpayer_iin_bin = b.taxpayer_iin_bin
WHERE cast(b.share_per AS Decimal(10,4))
        / cast(a.total_share AS Decimal(10,4)) * 100.0000 >= 25
  AND left(right(b.founder_iin_bin,8),1) NOT IN ('4','5')
  AND b.founder_iin_bin NOT LIKE '';
