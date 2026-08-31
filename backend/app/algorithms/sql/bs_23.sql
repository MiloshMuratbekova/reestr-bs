-- ============================================================================
-- БС-23 — Форма налоговой отчётности 026 (Предполагаемый БС, балл 3)
-- Источник: AFM_2_1_TEST.AFM_2_1_form026.
-- Результат: AFM_6_TEST.AFM_6_1_29
--
-- Организация берётся из поля fields_026_01_e, бенефициар — из fields_026_01_l.
-- В поле ИИН попадает только 12-значное число; номера документов и прочие
-- идентификаторы переносятся в dop_info.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_29 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_29
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    a.fields_026_01_e AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    CASE
        WHEN match(COALESCE(a.fields_026_01_l,''), '^[0-9]{12}$')
            THEN a.fields_026_01_l
        ELSE ''
    END AS benefeciary_iin_bin,
    if(right(left(COALESCE(a.fields_026_01_l,''),5),1) = '5',
        'Предполагаемый БС - нерезидент',
        if(right(left(COALESCE(a.fields_026_01_l,''),5),1) IN ('1','2','3')
            AND right(left(COALESCE(a.fields_026_01_l,''),7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-23' AS algorithm_code,
    3 AS priority,
    'ФНО_026' AS source,
    toString(today()) AS _actual_date,
    concat(
        COALESCE(a.fields_026_01_j4,''), ' ',
        COALESCE(a.fields_026_01_j3,''), ' ',
        COALESCE(a.fields_026_01_j5,''),
        if(COALESCE(a.fields_026_01_c1,'') != '',
            concat(', организация: ', a.fields_026_01_c1), ''),
        if(NOT match(COALESCE(a.fields_026_01_l,''), '^[0-9]{12}$')
            AND COALESCE(a.fields_026_01_l,'') != '',
            concat(', документ: ', a.fields_026_01_l), '')
    ) AS dop_info
FROM AFM_2_1_TEST.AFM_2_1_form026 AS a
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON a.fields_026_01_e = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON a.fields_026_01_e = c.taxpayer_iin_bin
WHERE a.fields_026_01_e != ''
  AND toInt64(length(a.fields_026_01_e)) = 12
  AND (
      match(COALESCE(a.fields_026_01_l,''), '^[0-9]{12}$')
      OR COALESCE(a.fields_026_01_j3,'') != ''
      OR COALESCE(a.fields_026_01_j4,'') != ''
      OR (NOT match(COALESCE(a.fields_026_01_l,''), '^[0-9]{12}$')
          AND COALESCE(a.fields_026_01_l,'') != '')
  );
