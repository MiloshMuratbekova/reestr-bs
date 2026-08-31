-- ============================================================================
-- БС-18 — Сведения субъектов финансового мониторинга (Предполагаемый БС, балл 4)
-- Источники: pfr_dashboard.bvu_beneficiary_info, pfr_dashboard.bvu_organization_info.
-- Результат: AFM_6_TEST.AFM_6_1_24
--
-- Обратная сторона БС-6: там берутся записи правоохранительных органов, здесь —
-- всех остальных поставщиков той же системы, прежде всего банков второго уровня.
--
-- В поле ИИН попадает только 12-значное число. Иностранные идентификаторы,
-- номера документов и текст вида «нет данных» переносятся в dop_info: если
-- оставить их в ключевом поле, реестр сведёт разных людей в одного.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_24 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_24
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    t1.organization_iin_bin AS taxpayer_iin_bin,
    t3.founder_iin_bin AS founder_iin_bin,
    t3.share_percentage AS share_percentage,
    t3.director_iin_bin AS director_iin_bin,
    CASE
        WHEN match(COALESCE(t1.iin_bin,''), '^[0-9]{12}$') THEN t1.iin_bin
        ELSE ''
    END AS benefeciary_iin_bin,
    if(right(left(COALESCE(t1.iin_bin,''),5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(COALESCE(t1.iin_bin,''),5),1) IN ('1','2','3')
            AND right(left(COALESCE(t1.iin_bin,''),7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-18' AS algorithm_code,
    4 AS priority,
    'СФМ' AS source,
    toString(t1.created_at) AS _actual_date,
    concat(
        COALESCE(t1.benefeciary_name,''),
        if(NOT match(COALESCE(t1.iin_bin,''), '^[0-9]{12}$')
            AND COALESCE(t1.iin_bin,'') != '',
            concat(', идентификатор: ', t1.iin_bin), ''),
        ', данные введены: ', COALESCE(t1.bvu_name,''),
        if(COALESCE(t1.info,'') != '', concat('. ', t1.info), '')
    ) AS dop_info
FROM (
    SELECT
        p.id AS id,
        p.bvu_name AS bvu_name,
        p.created_at AS created_at,
        p.iin_bin AS iin_bin,
        concat(p.first_name, ' ', p.last_name, ' ', p.middle_name) AS benefeciary_name,
        p.organization_iin_bin AS organization_iin_bin,
        concat(COALESCE(p.info,''), ' Резидент РК: ', toString(p.is_resident),
               '. Страна: ', COALESCE(p.country,'')) AS info
    FROM pfr_dashboard.bvu_beneficiary_info AS p
    WHERE p.organization_iin_bin != ''
      AND toInt64(length(p.organization_iin_bin)) = 12
      AND upper(p.bvu_name) NOT LIKE '%КНБ%'
      AND upper(p.bvu_name) NOT LIKE '%МВД%'
      AND upper(p.bvu_name) NOT LIKE '%ПРОКУРАТУР%'
      AND upper(p.bvu_name) NOT LIKE '%ДЭР%'
      AND upper(p.bvu_name) NOT LIKE '%АНТИКОРР РУ%'
      AND upper(p.bvu_name) NOT LIKE '%АФМ%'

    UNION ALL

    SELECT
        b.id AS id,
        b.bvu_name AS bvu_name,
        b.created_at AS created_at,
        b.beneficiary_iin_bin AS iin_bin,
        a.taxpayer_name AS benefeciary_name,
        b.iin_bin AS organization_iin_bin,
        COALESCE(b.info,'') AS info
    FROM pfr_dashboard.bvu_organization_info AS b
    LEFT JOIN AFM_2_1_TEST.AFM_2_1_10 AS a
        ON b.beneficiary_iin_bin = a.taxpayer_iin_bin
    WHERE b.iin_bin != ''
      AND toInt64(length(b.iin_bin)) = 12
      AND b.beneficiary_iin_bin != ''
) AS t1
LEFT JOIN (
    SELECT DISTINCT
        a.taxpayer_iin_bin AS tp_iin_bin,
        a.founder_iin_bin AS founder_iin_bin,
        a.share_percentage AS share_percentage,
        b.director_iin_bin AS director_iin_bin
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
) AS t3 ON t1.organization_iin_bin = t3.tp_iin_bin
WHERE t1.organization_iin_bin != ''
  AND (
      match(COALESCE(t1.iin_bin,''), '^[0-9]{12}$')
      OR (COALESCE(t1.benefeciary_name,'') != ''
          AND toInt64(length(trimBoth(COALESCE(t1.benefeciary_name,'')))) > 3
          AND lowerUTF8(COALESCE(t1.benefeciary_name,'')) NOT LIKE '%нерезидент%'
          AND lowerUTF8(COALESCE(t1.benefeciary_name,'')) NOT LIKE '%нет%'
          AND lowerUTF8(COALESCE(t1.benefeciary_name,'')) NOT LIKE '%отсутств%')
      OR (NOT match(COALESCE(t1.iin_bin,''), '^[0-9]{12}$')
          AND COALESCE(t1.iin_bin,'') != ''
          AND toInt64(length(trimBoth(COALESCE(t1.iin_bin,'')))) > 3
          AND lowerUTF8(COALESCE(t1.iin_bin,'')) NOT LIKE '%нерезидент%'
          AND lowerUTF8(COALESCE(t1.iin_bin,'')) NOT LIKE '%нет%')
  );
