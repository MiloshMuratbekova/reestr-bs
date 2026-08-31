-- ============================================================================
-- БС-14 — Фигуранты по данным Генеральной прокуратуры (Предполагаемый БС, балл 2)
-- Источник: AFM_2_5.AFM_2_5_1.
-- Результат: AFM_6_TEST.AFM_6_1_20
--
-- ВНИМАНИЕ. Алгоритм заведён ОТКЛЮЧЁННЫМ и в расчёте реестра не участвует.
-- Причины две:
--   * в итоговой таблице AFM_6_1_99 таблица AFM_6_1_20 отсутствует —
--     остальные алгоритмы туда включены, этот нет;
--   * присланный скрипт оборван: в нём «select *» с дописанными колонками
--     и без dop_info, то есть состав полей источника не определён.
--
-- Ниже — реконструкция по смыслу присланного скрипта: фигурант признаётся
-- предполагаемым БС организации. Названия колонок AFM_2_5_1, кроме
-- figurant_iin_bin, из скрипта не восстанавливаются, поэтому перед включением
-- алгоритма их надо сверить со справочником источника.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_20 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_20
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    a.figurant_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.figurant_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(a.figurant_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.figurant_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-14' AS algorithm_code,
    2 AS priority,
    'ГенПрок' AS source,
    toString(today()) AS _actual_date,
    COALESCE(a.figurant_name, '') AS dop_info
FROM AFM_2_5.AFM_2_5_1 AS a
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
WHERE a.figurant_iin_bin NOT LIKE '';
