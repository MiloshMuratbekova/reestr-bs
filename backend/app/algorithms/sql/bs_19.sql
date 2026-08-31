-- ============================================================================
-- БС-19 — Недропользователи (Предполагаемый БС, балл 4)
-- Источник: AFM_2_13.AFM_2_13_me — сведения МИИР и Министерства энергетики.
-- Результат: AFM_6_TEST.AFM_6_1_25
--
-- В поле ИИН попадает только 12-значное число без пробелов и без слов
-- «нет» / «отсутствует». Всё остальное переносится в dop_info.
--
-- ФИО берётся до первой запятой, а гражданство и доля вытягиваются из хвоста
-- benefeciary_name: в этом источнике они часто записаны одной строкой вместе
-- с именем, а не отдельными колонками.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_25 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_25
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    CASE
        WHEN toInt64(length(trimBoth(a.benefeciary_iin_bin))) = 12
            AND a.benefeciary_iin_bin NOT LIKE '%нет%'
            AND a.benefeciary_iin_bin NOT LIKE '%отсут%'
            AND a.benefeciary_iin_bin NOT LIKE '% %'
            AND match(a.benefeciary_iin_bin, '^[0-9]{12}$')
            THEN trimBoth(a.benefeciary_iin_bin)
        ELSE ''
    END AS benefeciary_iin_bin,
    if(right(left(trimBoth(a.benefeciary_iin_bin),5),1) = '5',
        'Предполагаемый БС - нерезидент',
        if(right(left(trimBoth(a.benefeciary_iin_bin),5),1) IN ('1','2','3')
            AND right(left(trimBoth(a.benefeciary_iin_bin),7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-19' AS algorithm_code,
    4 AS priority,
    'МИИР_МЭ' AS source,
    toString(today()) AS _actual_date,
    concat(
        -- ФИО: всё до первой запятой
        if(position(COALESCE(a.benefeciary_name,''), ',') > 0,
            trimBoth(substring(a.benefeciary_name, 1,
                position(a.benefeciary_name, ',') - 1)),
            trimBoth(COALESCE(a.benefeciary_name,''))),
        -- Некорректный ИИН уходит в текст
        if(NOT match(COALESCE(a.benefeciary_iin_bin,''), '^[0-9]{12}$')
            OR a.benefeciary_iin_bin LIKE '%нет%'
            OR a.benefeciary_iin_bin LIKE '%отсут%',
            concat(', идентификатор: ', COALESCE(a.benefeciary_iin_bin,'')), ''),
        -- Гражданство: отдельной колонкой либо из хвоста имени
        if(a.benefeciary_name LIKE '%гражданство%',
            concat(', ',
                trimBoth(substring(a.benefeciary_name,
                    position(a.benefeciary_name, 'гражданство'),
                    if(position(substring(a.benefeciary_name,
                        position(a.benefeciary_name, 'гражданство')), ',') > 0,
                       position(substring(a.benefeciary_name,
                        position(a.benefeciary_name, 'гражданство')), ',') - 1,
                       toInt64(length(a.benefeciary_name)))))),
            if(COALESCE(a.citizenship,'') != '',
                concat(', гражданство: ', a.citizenship), '')),
        -- Доля: отдельной колонкой либо из хвоста имени
        if((a.share_percentage IS NULL OR a.share_percentage = '')
            AND a.benefeciary_name LIKE '%доля%',
            concat(', ',
                trimBoth(substring(a.benefeciary_name,
                    position(a.benefeciary_name, 'доля'),
                    if(position(substring(a.benefeciary_name,
                        position(a.benefeciary_name, 'доля')), ',') > 0,
                       position(substring(a.benefeciary_name,
                        position(a.benefeciary_name, 'доля')), ',') - 1,
                       toInt64(length(a.benefeciary_name)))))),
            if(COALESCE(a.share_percentage,'') != '',
                concat(', доля: ', a.share_percentage, '%'), '')),
        if(COALESCE(a.country_residence,'') != '',
            concat(', страна проживания: ', a.country_residence), ''),
        if(COALESCE(a.interest_type,'') != '',
            concat(', характер интереса: ', a.interest_type), '')
    ) AS dop_info
FROM AFM_2_13.AFM_2_13_me AS a
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON a.taxpayer_iin_bin = c.taxpayer_iin_bin
WHERE a.taxpayer_iin_bin != ''
  AND toInt64(length(a.taxpayer_iin_bin)) = 12
  AND (
      (COALESCE(a.benefeciary_name,'') != ''
       AND lowerUTF8(COALESCE(a.benefeciary_name,'')) NOT LIKE '%нет%'
       AND lowerUTF8(COALESCE(a.benefeciary_name,'')) NOT LIKE '%отсут%'
       AND toInt64(length(COALESCE(a.benefeciary_name,''))) > 3)
      OR match(COALESCE(a.benefeciary_iin_bin,''), '^[0-9]{12}$')
  );
