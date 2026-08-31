-- ============================================================================
-- БС-3 — Учредители с долей 25% и более (Регистрационный БС, балл 0)
-- Источник: AFM_2_1_TEST.AFM_2_1_5_1; госсобственность исключается по AFM_2_1.AFM_2_1_8.
-- Результат: AFM_6_TEST.AFM_6_1_9
--
-- Берутся ЮЛ без признаков некорректности 1 и 2: сумма долей учредителей
-- попадает в диапазон 99.9–100.1. Сумма считается двумя способами — по БИН
-- компании и по её наименованию: у части записей БИН учредителя пуст, и такие
-- компании опознаются только по имени.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_9 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_9
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT
        taxpayer_iin_bin,
        if(substring(',',1,length(share_percentage)) = ',' AND share_percentage != '',
            cast(replace(share_percentage,',','.') AS Decimal(10,2)),
            floor(cast(concat(share_percentage,'.00') AS Decimal(10,2)),2)) AS share_percentage,
        founder_iin_bin,
        if(founder_ul_name LIKE '',
            concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),
            founder_ul_name) AS founder_name,
        `_actual_date`
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
      AND taxpayer_iin_bin IN (
            SELECT taxpayer_iin_bin
            FROM AFM_2_1.AFM_2_1_8
            WHERE ownership_type NOT LIKE 'Государственная собственность'
              AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1.AFM_2_1_8)
      )
      AND (
        taxpayer_iin_bin IN (
            SELECT taxpayer_iin_bin
            FROM (
                SELECT taxpayer_iin_bin, trunc(cast(share AS Decimal(10,2)),2) AS g
                FROM (
                    SELECT taxpayer_iin_bin, replace(share_percentage,',','.') AS share
                    FROM AFM_2_1_TEST.AFM_2_1_5_1
                    WHERE share_percentage LIKE '%,%' AND share_percentage NOT LIKE ''
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
            ) AS b
            GROUP BY taxpayer_iin_bin
            HAVING sum(g) >= 99.9 AND sum(g) <= 100.1
        )
        OR taxpayer_name IN (
            SELECT taxpayer_name
            FROM (
                SELECT taxpayer_name, trunc(cast(share AS Decimal(10,2)),2) AS g
                FROM (
                    SELECT taxpayer_name, replace(share_percentage,',','.') AS share
                    FROM AFM_2_1_TEST.AFM_2_1_5_1
                    WHERE share_percentage LIKE '%,%' AND share_percentage NOT LIKE ''
                      AND founder_iin_bin LIKE ''
                      AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
                ) AS a
                UNION ALL
                SELECT taxpayer_name,
                    floor(cast(concat(share_percentage,'.00') AS Decimal(10,2)),2) AS g
                FROM AFM_2_1_TEST.AFM_2_1_5_1
                WHERE share_percentage NOT LIKE '%,%'
                  AND share_percentage NOT LIKE '0'
                  AND share_percentage NOT LIKE ''
                  AND founder_iin_bin LIKE ''
                  AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
            ) AS b
            GROUP BY taxpayer_name
            HAVING sum(g) >= 99.9 AND sum(g) <= 100.1
        )
      )
)
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    a.founder_iin_bin AS founder_iin_bin,
    toString(a.share_percentage) AS share_percentage,
    b.employee_iin_bin AS director_iin_bin,
    a.founder_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.founder_iin_bin,5),1) = '5', 'Регистрационный БС - нерезидент',
        if(right(left(a.founder_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.founder_iin_bin,7),1) = '0',
            'Регистрационный БС - нерезидент',
            'Регистрационный БС')) AS status,
    'БС-3' AS algorithm_code,
    0 AS priority,
    'МЮ_учредители' AS source,
    toString(today()) AS _actual_date,
    a.founder_name AS dop_info
FROM (
    SELECT *
    FROM table1
    WHERE share_percentage >= 25.0
      AND left(right(founder_iin_bin,8),1) < '4'
) AS a
LEFT JOIN (
    SELECT *
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin;
