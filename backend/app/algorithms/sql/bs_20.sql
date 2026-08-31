-- ============================================================================
-- БС-20 — Бенефициары по данным госзакупок (Предполагаемый БС, балл 2)
-- Источник: AFM_2_1_TEST.AFM_2_1_goszakup — сведения, раскрываемые
-- поставщиками при участии в государственных закупках.
-- Результат: AFM_6_TEST.AFM_6_1_26
--
-- Сведения приходят двумя формами: в первой указан поставщик и имя его
-- бенефициара, во второй — тот же бенефициар с ИИН, долей и документом.
-- Формы связываются по имени бенефициара, поэтому обе стороны очищаются
-- от заглушек «нет», «отсутствует», «не имеется», «нет данных», «-»:
-- иначе десятки разных поставщиков склеились бы по слову «нет».
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_26 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_26
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    f1.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    CASE
        WHEN length(f2.benefeciary_iin_bin) = 12
            AND f2.benefeciary_iin_bin NOT LIKE '%нет%'
            AND f2.benefeciary_iin_bin NOT LIKE '%не имеется%'
            AND f2.benefeciary_iin_bin NOT LIKE '%нет данных%'
            AND f2.benefeciary_iin_bin != '-'
            AND f2.benefeciary_iin_bin != ''
            AND f2.benefeciary_iin_bin NOT LIKE '% %'
            THEN f2.benefeciary_iin_bin
        ELSE ''
    END AS benefeciary_iin_bin,
    if(right(left(f2.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(f2.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(f2.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-20' AS algorithm_code,
    2 AS priority,
    'МФ_госзакупки' AS source,
    toString(today()) AS _actual_date,
    concat(
        COALESCE(f1.benefeciary_name,''),
        if(COALESCE(f1.taxpayer_name,'') != '',
            concat(', поставщик: ', f1.taxpayer_name), ''),
        if(COALESCE(f2.share_percentage,'') != '',
            concat(', доля: ', f2.share_percentage, '%'), ''),
        if(COALESCE(f2.identity_doc,'') != '',
            concat(', документ: ', f2.identity_doc), ''),
        if(COALESCE(f1.purchase_name,'') != '',
            concat(', закупка: ', f1.purchase_name), '')
    ) AS dop_info
FROM (
    SELECT DISTINCT taxpayer_iin_bin, taxpayer_name, benefeciary_name, purchase_name
    FROM AFM_2_1_TEST.AFM_2_1_goszakup
    WHERE report_form LIKE '%1%'
      AND taxpayer_iin_bin != ''
      AND length(taxpayer_iin_bin) = 12
      AND benefeciary_name IS NOT NULL
      AND benefeciary_name != ''
      AND lowerUTF8(benefeciary_name) NOT LIKE '%нет%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%отсутств%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%не имеется%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%нет данных%'
      AND benefeciary_name != '-'
) AS f1
JOIN (
    SELECT DISTINCT benefeciary_name, benefeciary_iin_bin, share_percentage, identity_doc
    FROM AFM_2_1_TEST.AFM_2_1_goszakup
    WHERE report_form LIKE '%2%'
      AND benefeciary_name IS NOT NULL
      AND benefeciary_name != ''
      AND lowerUTF8(benefeciary_name) NOT LIKE '%нет%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%отсутств%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%не имеется%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%нет данных%'
      AND lowerUTF8(benefeciary_name) NOT LIKE '%участ%'
      AND length(benefeciary_name) > 3
      AND benefeciary_name != '-'
) AS f2 ON trim(f1.benefeciary_name) = trim(f2.benefeciary_name)
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON f1.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON f1.taxpayer_iin_bin = c.taxpayer_iin_bin
WHERE f1.taxpayer_iin_bin != ''
  AND (
      (length(f2.benefeciary_iin_bin) = 12
       AND f2.benefeciary_iin_bin NOT LIKE '%нет%'
       AND f2.benefeciary_iin_bin NOT LIKE '%не имеется%'
       AND f2.benefeciary_iin_bin NOT LIKE '%нет данных%'
       AND f2.benefeciary_iin_bin != '-'
       AND f2.benefeciary_iin_bin NOT LIKE '% %')
      OR f2.benefeciary_iin_bin LIKE '% %'
  );
