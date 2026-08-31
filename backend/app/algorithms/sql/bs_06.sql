-- ============================================================================
-- БС-6 — Сведения правоохранительных органов (Предполагаемый БС, балл 4)
-- Источник: pfr_dashboard.bvu_beneficiary_info — данные, поступившие через
-- систему websfm.kz.
-- Результат: AFM_6_TEST.AFM_6_1_12
--
-- Отбираются только записи от правоохранительных органов: КНБ, МВД,
-- прокуратура, ДЭР, антикоррупционная служба, финансовая полиция, АФМ.
-- Остальные поставщики той же таблицы разбираются алгоритмом БС-18.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_12 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_12
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    p.organization_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    d.employee_iin_bin AS director_iin_bin,
    p.iin_bin AS benefeciary_iin_bin,
    if(right(left(p.iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(p.iin_bin,5),1) IN ('1','2','3')
            AND right(left(p.iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-6' AS algorithm_code,
    4 AS priority,
    'ПО' AS source,
    toString(today()) AS _actual_date,
    concat(
        concat(p.first_name, ' ', p.last_name, ' ', p.middle_name),
        if(COALESCE(p.info,'') != '', concat(', ', p.info), ''),
        if(COALESCE(p.country,'') != '', concat(', страна: ', p.country), ''),
        concat(', источник: ', p.bvu_name)
    ) AS dop_info
FROM pfr_dashboard.bvu_beneficiary_info AS p
LEFT JOIN (
    SELECT *
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON p.organization_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT *
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS d ON p.organization_iin_bin = d.taxpayer_iin_bin
WHERE p.organization_iin_bin != ''
  AND p.iin_bin != ''
  AND (
      upper(p.bvu_name) LIKE '%КНБ%'
      OR upper(p.bvu_name) LIKE '%МВД%'
      OR upper(p.bvu_name) LIKE '%ПРОКУРАТУР%'
      OR upper(p.bvu_name) LIKE '%ДЭР%'
      OR upper(p.bvu_name) LIKE '%АНТИКОРР РУ%'
      OR upper(p.bvu_name) LIKE '%ФИНАНСОВАЯ ПОЛИЦИЯ%'
      OR upper(p.bvu_name) LIKE '%АФМ%'
  );
