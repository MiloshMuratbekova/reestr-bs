-- ============================================================================
-- БС-15 — Сведения ведомств, кроме правоохранительных (Предполагаемый БС, балл 1)
-- Источник: AFM_2_6.AFM_2_6_7.
-- Результат: AFM_6_TEST.AFM_6_1_21
--
-- Обратная сторона БС-6: там берутся записи от правоохранительных органов,
-- здесь — все остальные. Поле source не задаётся константой, а переносится
-- из данных: ведомство-поставщик у каждой записи своё.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_21 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_21
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT DISTINCT
        a.taxpayer_iin_bin AS tp_iin_bin,
        a.founder_iin_bin AS founder_iin_bin,
        a.share_percentage AS share_percentage,
        b.director_iin_bin AS director_iin_bin,
        c.employee_iin_bin AS employee_iin_bin
    FROM (
        SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
        FROM AFM_2_1_TEST.AFM_2_1_5_1
        WHERE taxpayer_iin_bin != ''
          AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
    ) AS a
    LEFT JOIN (
        SELECT taxpayer_iin_bin, employee_iin_bin AS director_iin_bin
        FROM AFM_2_1_TEST.AFM_2_1_6_1
        WHERE taxpayer_iin_bin != ''
          AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
    ) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
    LEFT JOIN (
        SELECT taxpayer_iin_bin, employee_iin_bin
        FROM AFM_2_1.AFM_2_1_19
        WHERE taxpayer_iin_bin != ''
    ) AS c ON a.taxpayer_iin_bin = c.taxpayer_iin_bin
)
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    b.director_iin_bin AS director_iin_bin,
    a.benefeciary_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(a.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-15' AS algorithm_code,
    1 AS priority,
    a.source AS source,
    a.`_actual_date` AS _actual_date,
    concat(a.benefeciary_name, ', ', a.dop_info) AS dop_info
FROM (
    SELECT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        benefeciary_name,
        source,
        dop_info,
        `_actual_date`
    FROM AFM_2_6.AFM_2_6_7
    WHERE `source` NOT LIKE '%Право%'
) AS a
LEFT JOIN table1 AS b ON a.taxpayer_iin_bin = b.tp_iin_bin;
