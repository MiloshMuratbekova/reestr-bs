-- ============================================================================
-- БС-2 — МФЦА (Регистрационный БС, балл не присваивается)
-- Источник: AFM_2_11.AFM_2_11_2 — акционеры компаний МФЦА.
-- Результат: AFM_6_TEST.AFM_6_1_8
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_8;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_8
AS
SELECT DISTINCT
    issuer_bin AS taxpayer_iin_bin,
    b.founder_iin_bin,
    b.share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    shareholder_iin_bin AS benefeciary_iin_bin,
    if(right(left(shareholder_iin_bin,5),1) = '5','Регистрационный БС - нерезидент',
        if(right(left(shareholder_iin_bin,5),1) IN ('1','2','3') AND right(left(shareholder_iin_bin,7),1)='0',
            'Регистрационный БС - нерезидент','Регистрационный БС')) AS status,
    'БС-2' AS algorithm_code,
    0 AS priority,
    'МФЦА' AS source,
    _actual_date,
    if(COALESCE(voting_share,'') != '',
        concat(shareholder_name, ', количество: ', share_quantity, '. Размещенные акции: ', outstanding_share, '. Доля: ', voting_share),
        concat(shareholder_name,
            if(COALESCE(citizenship,'') != '', concat(', гражданство: ', citizenship), ''),
            if(COALESCE(passport_number,'') != '', concat(', паспорт: ', passport_number), ''),
            if(COALESCE(kaz_id,'') != '', concat(', КАЗ ИД: ', kaz_id), ''))
    ) AS dop_info
FROM AFM_2_11.AFM_2_11_2
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) b ON issuer_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) c ON issuer_bin = c.taxpayer_iin_bin
WHERE issuer_bin != ''
AND (shareholder_iin_bin != '' OR shareholder_name IS NOT NULL);

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_8 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_8
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_8;
