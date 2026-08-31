-- ============================================================================
-- БС-17 — Заявления КИК с учётом данных КГД (Предполагаемый БС, балл 2)
-- Источники: AFM_2_1.AFM_2_1_45_1, _45_2, _45_3.
-- Результат: AFM_6_TEST.AFM_6_1_23
--
-- Тот же материал заявлений КИК, что и в БС-16, но конечный ФЛ-бенефициар
-- ищется в другом порядке: БС-1, БС-2, БС-22, БС-3, БС-4, БС-5 — то есть
-- между регистрационными источниками участвует ещё и КГД по нерезидентам.
-- Поэтому алгоритм считается ПОСЛЕ БС-1, БС-2, БС-3, БС-4, БС-5 и БС-22.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_23 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_23
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    a.taxpayer_iin_bin AS taxpayer_iin_bin,
    a.taxpayer_name1 AS taxpayer_name,
    a.founder_iin_bin AS founder_iin_bin,
    a.share_percentage AS share_percentage,
    a.director_iin_bin AS director_iin_bin,
    a.benefeciary_iin_bin AS benefeciary_iin_bin,
    if(right(left(a.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(a.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(a.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    a.algorithm_code AS algorithm_code,
    a.priority AS priority,
    a.source AS source,
    a.actual_date AS _actual_date,
    a.dop_info AS dop_info
FROM (
    SELECT DISTINCT
        k.taxpayer_iin_bin1 AS taxpayer_iin_bin,
        k.taxpayer_name1 AS taxpayer_name1,
        k.founder_iin_bin AS founder_iin_bin,
        k.share_percentage AS share_percentage,
        k.director_iin_bin AS director_iin_bin,
        if(k.taxpayer_iin_bin2 != '' AND right(left(k.taxpayer_iin_bin2,5),1) < '4',
            k.taxpayer_iin_bin2,
            if(bs1.benefeciary_iin_bin != '', bs1.benefeciary_iin_bin,
                if(bs2.benefeciary_iin_bin != '', bs2.benefeciary_iin_bin,
                    if(bs22.benefeciary_iin_bin != '', bs22.benefeciary_iin_bin,
                        if(bs3.benefeciary_iin_bin != '', bs3.benefeciary_iin_bin,
                            if(bs4.benefeciary_iin_bin != '', bs4.benefeciary_iin_bin,
                                if(bs5.benefeciary_iin_bin != '', bs5.benefeciary_iin_bin,
                                    k.taxpayer_iin_bin2))))))) AS benefeciary_iin_bin,
        'БС-17' AS algorithm_code,
        2 AS priority,
        k.source AS source,
        k.actual_date AS actual_date,
        k.dop_info AS dop_info
    FROM (
        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k1.field_023_01_B AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k1.taxpayer_iin_bin AS taxpayer_iin_bin2,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k1.taxpayer_name, ', БС управляет ', k1.field_023_01_B,
                   ' через КИК: ', k1.taxpayer_iin_bin,
                   ', наименование: ', e.taxpayer_name) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_1 AS k1
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 AS e ON k1.taxpayer_iin_bin = e.taxpayer_iin_bin
        WHERE k1.field_023_01_B IS NOT NULL AND k1.field_023_01_B != ''

        UNION ALL

        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k2.field_023_02_B AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k2.taxpayer_iin_bin AS taxpayer_iin_bin2,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k2.taxpayer_name, ', БС управляет ', k2.field_023_02_F,
                   ' через КИК: ', k2.taxpayer_iin_bin,
                   ', наименование: ', e.taxpayer_name) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_2 AS k2
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 AS e ON k2.taxpayer_iin_bin = e.taxpayer_iin_bin
        WHERE k2.field_023_02_B IS NOT NULL AND k2.field_023_02_B != ''

        UNION ALL

        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k3.field_023_03_B AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k3.taxpayer_iin_bin AS taxpayer_iin_bin2,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k3.taxpayer_name, ', БС управляет ', k3.field_023_03_B,
                   ' через КИК: ', k3.taxpayer_iin_bin,
                   ', ФИО: ', k3.field_023_03_F) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_3 AS k3
        WHERE k3.field_023_03_B IS NOT NULL AND k3.field_023_03_B != ''
    ) AS k
    LEFT JOIN AFM_6_TEST.AFM_6_1_7  AS bs1  ON k.taxpayer_iin_bin2 = bs1.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_8  AS bs2  ON k.taxpayer_iin_bin2 = bs2.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_28 AS bs22 ON k.taxpayer_iin_bin2 = bs22.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_9  AS bs3  ON k.taxpayer_iin_bin2 = bs3.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_10 AS bs4  ON k.taxpayer_iin_bin2 = bs4.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_11 AS bs5  ON k.taxpayer_iin_bin2 = bs5.taxpayer_iin_bin
) AS a;
