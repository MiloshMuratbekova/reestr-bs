-- ============================================================================
-- БС-16 — Заявления КИК и ФНО 240 (Предполагаемый БС, балл 2)
-- Источники: AFM_2_1.AFM_2_1_45_1, _45_2, _45_3 — заявления о контролируемых
-- иностранных компаниях; AFM_2_1.AFM_2_1_22_2021 — форма налоговой отчётности 240.
-- Результат: AFM_6_TEST.AFM_6_1_22
--
-- Заявитель по КИК признаётся предполагаемым БС иностранной компании. Поле
-- taxpayer_iin_bin содержит текст «Иностранная компания»: речь о зарубежных
-- организациях, БИН у них нет.
--
-- Если заявление подано юридическим лицом, конечный ФЛ-бенефициар
-- устанавливается в порядке БС-1, БС-3, БС-2, БС-4, БС-5 — поэтому алгоритм
-- считается ПОСЛЕ них.
--
-- ФНО 240: берутся объекты, в описании которых есть слово «доля», за вычетом
-- недвижимости и транспорта. Девять групп полей формы (024_1..024_9)
-- развёрнуты через ARRAY JOIN — в присланном скрипте они выписаны девятью
-- одинаковыми блоками по 20 условий каждый; здесь тот же отбор записан один
-- раз, результат совпадает.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_22 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_22
ENGINE = MergeTree
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
        if(k.taxpayer_iin_bin2 <> '' AND right(left(k.taxpayer_iin_bin2,5),1) < '4',
            k.taxpayer_iin_bin2,
            if(bs1.benefeciary_iin_bin <> '', bs1.benefeciary_iin_bin,
                if(bs3.benefeciary_iin_bin <> '', bs3.benefeciary_iin_bin,
                    if(bs2.benefeciary_iin_bin <> '', bs2.benefeciary_iin_bin,
                        if(bs4.benefeciary_iin_bin <> '', bs4.benefeciary_iin_bin,
                            if(bs5.benefeciary_iin_bin <> '', bs5.benefeciary_iin_bin,
                                k.taxpayer_iin_bin2)))))) AS benefeciary_iin_bin,
        k.algorithm_code AS algorithm_code,
        k.priority AS priority,
        k.source AS source,
        k.actual_date AS actual_date,
        k.dop_info AS dop_info
    FROM (
        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k1.`field_023_01_B` AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k1.`taxpayer_iin_bin` AS taxpayer_iin_bin2,
            'БС-16' AS algorithm_code,
            2 AS priority,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k1.taxpayer_name, ', БС управляет ', k1.`field_023_01_B`,
                   ' через КИК: ', k1.taxpayer_iin_bin,
                   ', наименование: ', e.taxpayer_name) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_1 AS k1
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 AS e
            ON k1.`taxpayer_iin_bin` = e.taxpayer_iin_bin
        WHERE k1.`field_023_01_B` IS NOT NULL AND k1.`field_023_01_B` <> ''

        UNION ALL

        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k2.`field_023_02_B` AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k2.`taxpayer_iin_bin` AS taxpayer_iin_bin2,
            'БС-16' AS algorithm_code,
            2 AS priority,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k2.taxpayer_name, ', БС управляет ', k2.`field_023_02_F`,
                   ' через КИК: ', k2.taxpayer_iin_bin,
                   ', наименование: ', e.taxpayer_name) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_2 AS k2
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 AS e
            ON k2.taxpayer_iin_bin = e.taxpayer_iin_bin
        WHERE k2.`field_023_02_B` IS NOT NULL AND k2.`field_023_02_B` <> ''

        UNION ALL

        SELECT
            'Иностранная компания' AS taxpayer_iin_bin1,
            k3.`field_023_03_B` AS taxpayer_name1,
            '' AS founder_iin_bin,
            '' AS share_percentage,
            '' AS director_iin_bin,
            k3.`taxpayer_iin_bin` AS taxpayer_iin_bin2,
            'БС-16' AS algorithm_code,
            2 AS priority,
            'Заявление КИК' AS source,
            '' AS actual_date,
            concat(k3.taxpayer_name, ', БС управляет ', k3.`field_023_03_B`,
                   ' через КИК: ', k3.taxpayer_iin_bin,
                   ', ФИО: ', k3.`field_023_03_F`) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_3 AS k3
        WHERE k3.`field_023_03_B` IS NOT NULL AND k3.`field_023_03_B` <> ''
    ) AS k
    LEFT JOIN AFM_6_TEST.AFM_6_1_7 AS bs1 ON k.taxpayer_iin_bin2 = bs1.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_8 AS bs2 ON k.taxpayer_iin_bin2 = bs2.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_9 AS bs3 ON k.taxpayer_iin_bin2 = bs3.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_10 AS bs4 ON k.taxpayer_iin_bin2 = bs4.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_11 AS bs5 ON k.taxpayer_iin_bin2 = bs5.taxpayer_iin_bin

    UNION ALL

    SELECT DISTINCT
        'Иностранная компания' AS taxpayer_iin_bin,
        '' AS taxpayer_name1,
        '' AS founder_iin_bin,
        '' AS share_percentage,
        '' AS director_iin_bin,
        f.IIN_BIN AS benefeciary_iin_bin,
        'БС-16' AS algorithm_code,
        2 AS priority,
        'ФНО 240' AS source,
        '' AS actual_date,
        concat(COALESCE(h.taxpayer_name,''),
               ', объект: ', f.foreign_object,
               ', код страны: ', f.country_code,
               ', регистрационный код: ', f.reg_code,
               ', допинфо: ', f.extra_info) AS dop_info
    FROM (
        SELECT
            IIN_BIN,
            fld.1 AS foreign_object,
            fld.2 AS country_code,
            fld.3 AS reg_code,
            fld.4 AS extra_info
        FROM AFM_2_1.AFM_2_1_22_2021
        ARRAY JOIN [
            (field_240_00_024_1_A, field_240_00_024_1_B, field_240_00_024_1_C, field_240_00_024_1_D),
            (field_240_00_024_2_A, field_240_00_024_2_B, field_240_00_024_2_C, field_240_00_024_2_D),
            (field_240_00_024_3_A, field_240_00_024_3_B, field_240_00_024_3_C, field_240_00_024_3_D),
            (field_240_00_024_4_A, field_240_00_024_4_B, field_240_00_024_4_C, field_240_00_024_4_D),
            (field_240_00_024_5_A, field_240_00_024_5_B, field_240_00_024_5_C, field_240_00_024_5_D),
            (field_240_00_024_6_A, field_240_00_024_6_B, field_240_00_024_6_C, field_240_00_024_6_D),
            (field_240_00_024_7_A, field_240_00_024_7_B, field_240_00_024_7_C, field_240_00_024_7_D),
            (field_240_00_024_8_A, field_240_00_024_8_B, field_240_00_024_8_C, field_240_00_024_8_D),
            (field_240_00_024_9_A, field_240_00_024_9_B, field_240_00_024_9_C, field_240_00_024_9_D)
        ] AS fld
        WHERE lowerUTF8(fld.1) LIKE '%доля%'
          AND lowerUTF8(fld.1) NOT LIKE ''
          AND lowerUTF8(fld.1) NOT LIKE '%кв%'
          AND lowerUTF8(fld.1) NOT LIKE '%дом%'
          AND lowerUTF8(fld.1) NOT LIKE '%недв%'
          AND lowerUTF8(fld.1) NOT LIKE '%земел%'
          AND lowerUTF8(fld.1) NOT LIKE '%земли%'
          AND lowerUTF8(fld.1) NOT LIKE '%апарт%'
          AND lowerUTF8(fld.1) NOT LIKE '%аппарт%'
          AND lowerUTF8(fld.1) NOT LIKE '%жил%'
          AND lowerUTF8(fld.1) NOT LIKE '%комн%'
          AND lowerUTF8(fld.1) NOT LIKE '%собств%'
          AND lowerUTF8(fld.1) NOT LIKE '%помещ%'
          AND lowerUTF8(fld.1) NOT LIKE '%склад%'
          AND lowerUTF8(fld.1) NOT LIKE '%участка%'
          AND lowerUTF8(fld.1) NOT LIKE '%строитель%'
          AND lowerUTF8(fld.1) NOT LIKE '%гараж%'
          AND lowerUTF8(fld.1) NOT LIKE '%авто%'
          AND lowerUTF8(fld.1) NOT LIKE '%ETF%'
    ) AS f
    LEFT JOIN AFM_2_1_TEST.AFM_2_1_10 AS h ON f.IIN_BIN = h.taxpayer_iin_bin
) AS a;
