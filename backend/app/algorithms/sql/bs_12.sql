-- ============================================================================
-- БС-12 — Выгодоприобретатель по сообщению СФМ (Предполагаемый БС, балл 4)
-- Источник: pfr_dashboard.asloy.
-- Результат: AFM_6_TEST.AFM_6_1_18
--
-- Берётся связка «отправитель сообщения — выгодоприобретатель»: субъект
-- финансового мониторинга (CFM_MAINCODE) — юридическое лицо, а указанный
-- в сообщении выгодоприобретатель (BENEFICIARY_MAINCODE) — физическое.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_18 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_18
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    s.CFM_MAINCODE AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    s.BENEFICIARY_MAINCODE AS benefeciary_iin_bin,
    if(right(left(s.BENEFICIARY_MAINCODE,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(s.BENEFICIARY_MAINCODE,5),1) IN ('1','2','3')
            AND right(left(s.BENEFICIARY_MAINCODE,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-12' AS algorithm_code,
    4 AS priority,
    'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date,
    concat(
        COALESCE(s.BENEFICIARY_UR_NAME,''),
        if(COALESCE(s.BENEFICIARY_COUNTRY_RESIDENCE,'') != '',
            concat(', страна: ', s.BENEFICIARY_COUNTRY_RESIDENCE), '')
    ) AS dop_info
FROM pfr_dashboard.asloy AS s
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON s.CFM_MAINCODE = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON s.CFM_MAINCODE = c.taxpayer_iin_bin
WHERE s.BENEFICIARY_MAINCODE != ''
  AND s.BENEFICIARY_MAINCODE IS NOT NULL
  AND s.CFM_MAINCODE != ''
  AND s.CFM_MAINCODE IS NOT NULL
  AND left(right(s.CFM_MAINCODE,8),1) IN ('4','5')
  AND left(right(s.BENEFICIARY_MAINCODE,8),1) NOT IN ('4','5');
