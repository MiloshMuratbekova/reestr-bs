-- ============================================================================
-- БС-6 — Данные правоохранительных органов (Предполагаемый БС, балл 4)
-- Источник: pfr_dashboard.bvu_beneficiary_info (поступление через websfm.kz).
-- Результат: AFM_6_TEST.AFM_6_1_12
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_12;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_12
AS
SELECT DISTINCT
    p.organization_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin,
    b.share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    p.iin_bin AS benefeciary_iin_bin,
    if(right(left(p.iin_bin,5),1) = '5','Предполагаемый БС - нерезидент',
        if(right(left(p.iin_bin,5),1) IN ('1','2','3') AND right(left(p.iin_bin,7),1)='0',
            'Предполагаемый БС - нерезидент','Предполагаемый БС')) AS status,
    'БС-6' AS algorithm_code,
    4 AS priority,
    'ПО' AS source,
    toString(today()) AS _actual_date,
    concat(p.first_name,' ',p.last_name,' ',p.middle_name,
        if(COALESCE(p.info,'') != '', concat(', ',p.info),''),
        concat(', источник: ',p.bvu_name)) AS dop_info
FROM pfr_dashboard.bvu_beneficiary_info p
LEFT JOIN (SELECT * FROM AFM_2_1_TEST.AFM_2_1_5_1 WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)) b ON p.organization_iin_bin=b.taxpayer_iin_bin
LEFT JOIN (SELECT * FROM AFM_2_1_TEST.AFM_2_1_6_1 WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)) c ON p.organization_iin_bin=c.taxpayer_iin_bin
WHERE p.organization_iin_bin != '' AND p.iin_bin != ''
AND (upper(p.bvu_name) LIKE '%КНБ%' OR upper(p.bvu_name) LIKE '%МВД%'
    OR upper(p.bvu_name) LIKE '%ПРОКУРАТУР%' OR upper(p.bvu_name) LIKE '%ДЭР%'
    OR upper(p.bvu_name) LIKE '%АНТИКОРРУП%' OR upper(p.bvu_name) LIKE '%АФМ%');

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_12 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_12
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_12;
