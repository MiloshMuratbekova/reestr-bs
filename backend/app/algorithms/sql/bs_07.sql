-- ============================================================================
-- БС-7 — Депозитарий ценных бумаг (Предполагаемый БС, балл 4)
-- Источник: AFM_2_12.AFM_2_12_1 — акционеры публичных компаний.
-- Результат: AFM_6_TEST.AFM_6_1_13
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_13;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_13
AS
SELECT DISTINCT
    a.taxpayer_iin_bin,
    b.founder_iin_bin,
    b.share_percentage,
    d.employee_iin_bin AS director_iin_bin,
    a.shareholder_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.shareholder_iin_bin,5),1) = '5'
        OR a.shareholder_iin_bin LIKE '%инос%'
        OR a.shareholder_iin_bin = '',
        'Предполагаемый БС - нерезидент',
        if(right(left(a.shareholder_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.shareholder_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-7' AS algorithm_code,
    4 AS priority,
    'ДЦБ' AS source,
    a._actual_date,
    concat(shareholder_name, ', ', share_type) AS dop_info
FROM AFM_2_12.AFM_2_12_1 a
LEFT JOIN (
    SELECT * FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT * FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) d ON a.taxpayer_iin_bin = d.taxpayer_iin_bin;

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_13 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_13
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_13;
