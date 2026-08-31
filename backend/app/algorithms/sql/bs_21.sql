-- ============================================================================
-- БС-21 — Бенефициары поставщиков «Самрук-Казына» (Предполагаемый БС, балл 2)
-- Источник: AFM_2_1_TEST.AFM_2_1_samruk.
-- Результат: AFM_6_TEST.AFM_6_1_27
--
-- ИИН в источнике записан по-разному: чистым числом либо внутри текста
-- вида «ИИН 123456789012». Оба случая приводятся к 12-значному числу,
-- остальное уходит в dop_info.
--
-- Разбор ИИН вынесен в отдельный уровень (подзапрос clean): в присланном
-- скрипте то же выражение CASE повторено четырежды — в самом поле и трижды
-- внутри вычисления статуса. Результат тот же, но правится в одном месте.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_27 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_27
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    clean.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    clean.clean_iin AS benefeciary_iin_bin,
    if(right(left(clean.clean_iin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(clean.clean_iin,5),1) IN ('1','2','3')
            AND right(left(clean.clean_iin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-21' AS algorithm_code,
    2 AS priority,
    'Самрук_Казына' AS source,
    toString(today()) AS _actual_date,
    concat(
        COALESCE(clean.last_name,''), ' ',
        COALESCE(clean.first_name,''), ' ',
        COALESCE(clean.middle_name,''),
        if(COALESCE(clean.benefeciary_name,'') != '',
            concat(', ', clean.benefeciary_name), ''),
        if(clean.clean_iin = '' AND COALESCE(clean.raw_iin,'') != '',
            concat(', доп.инфо: ', clean.raw_iin), ''),
        if(COALESCE(clean.participation_type,'') != '',
            concat(', тип участия: ', clean.participation_type), ''),
        if(COALESCE(clean.request_status,'') != '',
            concat(', статус заявки: ', clean.request_status), '')
    ) AS dop_info
FROM (
    SELECT
        a.taxpayer_iin_bin AS taxpayer_iin_bin,
        a.benefeciary_iin_bin AS raw_iin,
        a.benefeciary_name AS benefeciary_name,
        a.last_name AS last_name,
        a.first_name AS first_name,
        a.middle_name AS middle_name,
        a.participation_type AS participation_type,
        a.request_status AS request_status,
        CASE
            WHEN match(COALESCE(a.benefeciary_iin_bin,''), '^[0-9]{12}$')
                THEN a.benefeciary_iin_bin
            WHEN match(COALESCE(a.benefeciary_iin_bin,''), '[0-9]{12}')
                AND (a.benefeciary_iin_bin LIKE '%ИИН%'
                     OR a.benefeciary_iin_bin LIKE '%БИН%')
                THEN extract(a.benefeciary_iin_bin, '([0-9]{12})')
            ELSE ''
        END AS clean_iin
    FROM AFM_2_1_TEST.AFM_2_1_samruk AS a
    WHERE a.taxpayer_iin_bin != ''
      AND toInt64(length(a.taxpayer_iin_bin)) = 12
      AND (
          match(COALESCE(a.benefeciary_iin_bin,''), '^[0-9]{12}$')
          OR (match(COALESCE(a.benefeciary_iin_bin,''), '[0-9]{12}')
              AND (a.benefeciary_iin_bin LIKE '%ИИН%'
                   OR a.benefeciary_iin_bin LIKE '%БИН%'))
          OR (COALESCE(a.last_name,'') != '' AND toInt64(length(COALESCE(a.last_name,''))) > 2)
          OR (COALESCE(a.first_name,'') != '' AND toInt64(length(COALESCE(a.first_name,''))) > 2)
      )
      AND lowerUTF8(COALESCE(a.benefeciary_iin_bin,'')) NOT LIKE '%нет%'
      AND lowerUTF8(COALESCE(a.benefeciary_iin_bin,'')) NOT LIKE '%отсутств%'
      AND lowerUTF8(COALESCE(a.benefeciary_iin_bin,'')) NOT LIKE '%не имеет%'
      AND COALESCE(a.benefeciary_iin_bin,'') != '111111111111'
      AND COALESCE(a.benefeciary_iin_bin,'') != '999999999999'
      AND COALESCE(a.benefeciary_iin_bin,'') != '998989999999'
) AS clean
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON clean.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON clean.taxpayer_iin_bin = c.taxpayer_iin_bin;
