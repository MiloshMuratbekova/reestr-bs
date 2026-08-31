-- ============================================================================
-- БС-24 — Руководитель как последний признак (Регистрационный БС, балл 0)
-- Источник: AFM_2_1_TEST.AFM_2_1_6_1 — руководители юридических лиц.
-- Результат: AFM_6_TEST.AFM_6_1_30
--
-- Замыкающий алгоритм: если по компании не сработал НИ ОДИН другой признак,
-- бенефициаром признаётся её руководитель. Государственные компании
-- исключаются — по ним бенефициары не определяются.
--
-- В присланном скрипте исключение записано как «нет в AFM_6_1_99», то есть
-- в итоговой таблице реестра. Здесь реестр не материализуется — он строится
-- запросом при каждом обращении, — поэтому то же условие выражено напрямую:
-- компании не должно быть ни в одной таблице результатов других алгоритмов.
-- Смысл тот же, промежуточная таблица не нужна.
--
-- Считается ПОСЛЕДНИМ: читает результаты всех остальных алгоритмов.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_30 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_30
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH already_found AS (
    SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_7  WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_8  WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_9  WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_10 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_11 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_12 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_13 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_14 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_15 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_16 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_17 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_18 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_19 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_21 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_22 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_23 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_24 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_25 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_26 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_27 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_28 WHERE benefeciary_iin_bin != ''
    UNION ALL SELECT taxpayer_iin_bin FROM AFM_6_TEST.AFM_6_1_29 WHERE benefeciary_iin_bin != ''
)
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    a.employee_iin_bin AS director_iin_bin,
    a.employee_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.employee_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(a.employee_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.employee_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-24' AS algorithm_code,
    0 AS priority,
    'МЮ_директор' AS source,
    toString(today()) AS _actual_date,
    concat(
        COALESCE(a.employee_last_name,''), ' ',
        COALESCE(a.employee_first_name,''), ' ',
        COALESCE(a.employee_part_name,'')
    ) AS dop_info
FROM (
    SELECT *
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
      AND taxpayer_iin_bin != ''
      AND employee_iin_bin != ''
) AS a
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin
WHERE a.taxpayer_iin_bin NOT IN (SELECT taxpayer_iin_bin FROM already_found)
  AND a.taxpayer_iin_bin NOT IN (
      SELECT taxpayer_iin_bin
      FROM AFM_2_1.AFM_2_1_8
      WHERE ownership_type LIKE '%Государственная%'
        AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1.AFM_2_1_8)
  );
