-- ============================================================================
-- БС-18 — Сведения субъектов финансового мониторинга (Предполагаемый БС, балл 4)
-- Источник: pfr_dashboard.bvu_beneficiary_info.
-- Результат: AFM_6_TEST.AFM_6_1_24
--
-- Обратная сторона БС-6: там берутся записи правоохранительных органов, здесь —
-- всех остальных поставщиков той же системы, прежде всего банков второго уровня.
--
-- В поле ИИН попадает только 12-значное число. Иностранные идентификаторы,
-- номера документов и текст вида «нет данных» переносятся в dop_info под
-- ярлыком «идентификатор»: оставь их в ключевом поле — и реестр сведёт
-- разных людей в одного. Интерфейс показывает этот идентификатор в колонке
-- ИИН вместо слова «нерезидент», когда он есть.
--
-- Нерезидентство определяется по заполненной стране, а не по структуре ИИН:
-- у иностранца казахстанского номера нет вовсе, и судить по нему не о чем.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_24 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_24
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    p.organization_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    if(match(COALESCE(p.iin_bin,''), '^[0-9]{12}$'), p.iin_bin, '') AS benefeciary_iin_bin,
    if(trimBoth(COALESCE(p.country,'')) != '',
        'Предполагаемый БС - нерезидент',
        'Предполагаемый БС') AS status,
    'БС-18' AS algorithm_code,
    4 AS priority,
    'СФМ' AS source,
    toString(p.created_at) AS _actual_date,
    concat(
        trimBoth(concat(COALESCE(p.last_name,''), ' ',
                        COALESCE(p.first_name,''), ' ',
                        COALESCE(p.middle_name,''))),
        if(NOT match(COALESCE(p.iin_bin,''), '^[0-9]{12}$') AND COALESCE(p.iin_bin,'') != '',
            concat(', идентификатор: ', p.iin_bin), ''),
        if(trimBoth(COALESCE(p.country,'')) != '',
            concat(', страна: ', p.country), ', страна: Казахстан'),
        if(extract(COALESCE(p.info,''), '([0-9]+[.,]?[0-9]*)\s*%') != '',
            concat(', доля: ', extract(COALESCE(p.info,''), '([0-9]+[.,]?[0-9]*)\s*%'), '%'), ''),
        if(trimBoth(COALESCE(p.info,'')) != '', concat(', инфо: ', p.info), ''),
        concat(', данные введены: ', COALESCE(p.bvu_name,''))
    ) AS dop_info
FROM pfr_dashboard.bvu_beneficiary_info p
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) b ON p.organization_iin_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) c ON p.organization_iin_bin = c.taxpayer_iin_bin
WHERE p.organization_iin_bin != ''
    AND toInt64(length(p.organization_iin_bin)) = 12
    AND (
        match(COALESCE(p.iin_bin,''), '^[0-9]{12}$')
        OR trimBoth(concat(COALESCE(p.last_name,''), COALESCE(p.first_name,''))) != ''
    )
    AND upper(COALESCE(p.bvu_name,'')) NOT LIKE '%КНБ%'
    AND upper(COALESCE(p.bvu_name,'')) NOT LIKE '%МВД%'
    AND upper(COALESCE(p.bvu_name,'')) NOT LIKE '%ПРОКУРАТУР%'
    AND upper(COALESCE(p.bvu_name,'')) NOT LIKE '%ДЭР%'
    AND upper(COALESCE(p.bvu_name,'')) NOT LIKE '%АНТИКОРР РУ%'
