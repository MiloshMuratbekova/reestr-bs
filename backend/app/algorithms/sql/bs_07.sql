-- ============================================================================
-- БС-7 — Депозитарий ценных бумаг (Предполагаемый БС, балл 4)
-- Источник: AFM_2_1_TEST.AFM_2_1_dcb — акционеры по данным ДЦБ.
-- Результат: AFM_6_TEST.AFM_6_1_13
--
-- Берутся только физические лица: пятый знак справа восьмизначной части ИИН
-- меньше 4. Юридические лица акционерами-бенефициарами здесь не считаются.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_13 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_13
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    a.benefeciary_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(a.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-7' AS algorithm_code,
    4 AS priority,
    'ДЦБ' AS source,
    a.`_actual_date` AS _actual_date,
    concat('Акционер по данным ДЦБ: ', COALESCE(a.taxpayer_name,'')) AS dop_info
FROM (
    SELECT taxpayer_iin_bin, taxpayer_name, benefeciary_iin_bin, `_actual_date`
    FROM AFM_2_1_TEST.AFM_2_1_dcb
    WHERE benefeciary_iin_bin != ''
      AND taxpayer_iin_bin != ''
      AND left(right(benefeciary_iin_bin,8),1) NOT IN ('4','5')
) AS a
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON a.taxpayer_iin_bin = c.taxpayer_iin_bin;
