-- ============================================================================
-- БС-17 — Заявления КИК (Предполагаемый БС, балл 2)
-- Источник: AFM_2_1.AFM_2_1_45_1 / _45_2 / _45_3 — заявления о контролируемых
-- иностранных компаниях.
-- Если заявление подано ФЛ — он и есть БС. Если ЮЛ — конечный ФЛ-бенефициар
-- устанавливается по цепочке: БС-1 → БС-2 → БС-22 → БС-3 → БС-4.
-- taxpayer_iin_bin = 'Иностранная компания' (речь о зарубежных организациях).
--
-- ЗАВИСИМОСТИ: AFM_6_1_7 (БС-1), AFM_6_1_8 (БС-2), AFM_6_1_28 (БС-22),
--              AFM_6_1_9 (БС-3), AFM_6_1_10 (БС-4)
-- Результат: AFM_6_TEST.AFM_6_1_23
--
-- ПРАВКА СИНТАКСИСА (логика не изменена), см. docs/sql-fixes.md:
--   в ТЗ было  «bs22.`k.taxpayer_iin_bin`»
--   выполняется «bs22.taxpayer_iin_bin»
--   (в AFM_6_1_28 колонка объявлена как «k.taxpayer_iin_bin AS taxpayer_iin_bin»,
--    то есть её имя — taxpayer_iin_bin).
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_23;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_23
AS
SELECT DISTINCT
    taxpayer_iin_bin, taxpayer_name1 AS taxpayer_name, founder_iin_bin, share_percentage,
    director_iin_bin, benefeciary_iin_bin,
    if(right(left(benefeciary_iin_bin,5),1)='5','Предполагаемый БС - нерезидент',
        if(right(left(benefeciary_iin_bin,5),1) IN ('1','2','3') AND right(left(benefeciary_iin_bin,7),1)='0',
            'Предполагаемый БС - нерезидент','Предполагаемый БС')) AS status,
    algorithm_code, priority, source, actual_date AS _actual_date, dop_info
FROM (
    SELECT DISTINCT taxpayer_iin_bin1 AS taxpayer_iin_bin, taxpayer_name1,
        a1.founder_iin_bin AS founder_iin_bin, a1.share_percentage AS share_percentage,
        a1.director_iin_bin AS director_iin_bin,
        if(taxpayer_iin_bin2 != '' AND right(left(taxpayer_iin_bin2,5),1) < '4', taxpayer_iin_bin2,
            if(bs1.benefeciary_iin_bin != '', bs1.benefeciary_iin_bin,
                if(bs2.benefeciary_iin_bin != '', bs2.benefeciary_iin_bin,
                    if(bs22.benefeciary_iin_bin != '', bs22.benefeciary_iin_bin,
                        if(bs3.benefeciary_iin_bin != '', bs3.benefeciary_iin_bin,
                            if(bs4.benefeciary_iin_bin != '', bs4.benefeciary_iin_bin,
                                taxpayer_iin_bin2)))))) AS benefeciary_iin_bin,
        a1.status, 'БС-17' AS algorithm_code, 2 AS priority, a1.source, actual_date, a1.dop_info
    FROM (
        SELECT 'Иностранная компания' AS taxpayer_iin_bin1, field_023_01_B AS taxpayer_name1,
            '' AS founder_iin_bin, '' AS founder_name, '' AS share_percentage,
            '' AS director_iin_bin, '' AS director_name,
            a1.taxpayer_iin_bin AS taxpayer_iin_bin2, 'Предполагаемый БС' AS status,
            'БС-17' AS algorithm_code, 2 AS priority, 'Заявление КИК' AS source, '' AS actual_date,
            concat(taxpayer_name,', БС управляет ',field_023_01_B,' через БИН: ',a1.taxpayer_iin_bin,', наименование: ',e.taxpayer_name) AS dop_info
        FROM AFM_2_1.AFM_2_1_45_1 a1
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 e ON a1.taxpayer_iin_bin=e.taxpayer_iin_bin
        WHERE field_023_01_B IS NOT NULL AND field_023_01_B != ''
        UNION ALL
        SELECT 'Иностранная компания', field_023_02_B, '', '', '', '', '',
            taxpayer_iin_bin, 'Предполагаемый БС', 'БС-17', 2, 'Заявление КИК', '',
            concat(taxpayer_name,', БС управляет ',field_023_02_F,' через БИН: ',a2.taxpayer_iin_bin,', наименование: ',e.taxpayer_name)
        FROM AFM_2_1.AFM_2_1_45_2 a2
        LEFT JOIN AFM_2_1_TEST.AFM_2_1_9 e ON a2.taxpayer_iin_bin=e.taxpayer_iin_bin
        WHERE field_023_02_B IS NOT NULL AND field_023_02_B != ''
        UNION ALL
        SELECT 'Иностранная компания', field_023_03_B, '', '', '', '', '',
            taxpayer_iin_bin, 'Предполагаемый БС', 'БС-17', 2, 'Заявление КИК', '',
            concat(taxpayer_name,', БС управляет ',field_023_03_B,' через ИИН: ',taxpayer_iin_bin,', ФИО: ',field_023_03_F)
        FROM AFM_2_1.AFM_2_1_45_3
        WHERE field_023_03_B IS NOT NULL AND field_023_03_B != ''
    ) a1
    LEFT JOIN AFM_6_TEST.AFM_6_1_7  bs1  ON a1.taxpayer_iin_bin2=bs1.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_8  bs2  ON a1.taxpayer_iin_bin2=bs2.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_28 bs22 ON a1.taxpayer_iin_bin2=bs22.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_9  bs3  ON a1.taxpayer_iin_bin2=bs3.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.AFM_6_1_10 bs4  ON a1.taxpayer_iin_bin2=bs4.taxpayer_iin_bin
    LEFT JOIN AFM_2_1_TEST.AFM_2_1_10 e  ON a1.taxpayer_iin_bin2=e.taxpayer_iin_bin
    LEFT JOIN AFM_2_1_TEST.AFM_2_1_9  h  ON a1.taxpayer_iin_bin2=h.taxpayer_iin_bin
) a;

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_23 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_23
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_23;
