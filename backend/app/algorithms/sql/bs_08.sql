-- ============================================================================
-- БС-8 — Крупные переводы ЮЛ в адрес ФЛ (Предполагаемый БС, балл 3)
-- Источник: pfr_dashboard.asloy, дополнительная информация — asloy_dopinfo.
-- Результат: AFM_6_TEST.AFM_6_1_14
--
-- КВО 0511, 0530, 0311 берутся без условий; КВО 0911 — только если в
-- дополнительной информации есть признаки безвозмездной или возвратной помощи.
-- Период — последние 6 календарных месяцев.
--
-- Порог двойной: сумма по паре ЮЛ-ФЛ больше 10 млн тенге И составляет не менее
-- 25% всех исходящих переводов ЮЛ. Условие «не менее 25%» записано умножением
-- (pair_amount * 4 >= total_amount), а не делением: деление на ноль в ClickHouse
-- дало бы NULL и строка молча выпала бы из выборки.
--
-- Плательщики-ЮЛ, являющиеся МФО, банком, ломбардом или кредитным
-- товариществом, из расчёта исключаются.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_14 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_14
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT
        SELLER_MAINCODE,
        CUSTOMER_MAINCODE,
        CUSTOMER_UR_NAME,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND OPER_IDVIEW IN ('511','530','311')
      AND date_diff('day', today(), DATE_OPER) > -180
      AND CUSTOMER_MAINCODE != ''
      AND SELLER_MAINCODE != ''
      AND left(right(CUSTOMER_MAINCODE,8),1) NOT IN ('4','5')
      AND left(right(SELLER_MAINCODE,8),1) IN ('4','5')

    UNION ALL

    SELECT
        SELLER_MAINCODE,
        CUSTOMER_MAINCODE,
        CUSTOMER_UR_NAME,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND OPER_IDVIEW = '911'
      AND date_diff('day', today(), DATE_OPER) > -180
      AND CUSTOMER_MAINCODE != ''
      AND SELLER_MAINCODE != ''
      AND left(right(CUSTOMER_MAINCODE,8),1) NOT IN ('4','5')
      AND left(right(SELLER_MAINCODE,8),1) IN ('4','5')
      AND MESS_ID IN (
          SELECT MESS_ID
          FROM pfr_dashboard.asloy_dopinfo
          WHERE dopinfo LIKE '%безвоз%'
             OR dopinfo LIKE '%фин. помощь%'
             OR dopinfo LIKE '%финпом%'
             OR dopinfo LIKE '%фин.пом%'
             OR dopinfo LIKE '%финансовая помощь%'
             OR dopinfo LIKE '%возвратная помощь%'
             OR dopinfo LIKE '%выдача краткосрочных займов%'
             OR dopinfo LIKE '%ЗАЙМ%'
             OR dopinfo LIKE '%ФИН. ПОМОЩЬ%'
             OR dopinfo LIKE '%ФИНПОМ%'
             OR dopinfo LIKE '%ФИН.ПОМ%'
             OR dopinfo LIKE '%ФИНАНСОВАЯ ПОМОЩЬ%'
             OR dopinfo LIKE '%ВОЗВРАТНАЯ ПОМОЩЬ%'
      )
),
excluded_ul AS (
    SELECT DISTINCT taxpayer_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_9
    WHERE lower(taxpayer_name) LIKE '%мфо%'
       OR lower(taxpayer_name) LIKE '%банк%'
       OR lower(taxpayer_name) LIKE '%ломбард%'
       OR lower(taxpayer_name) LIKE '%кредитное товарищество%'
),
total_ul AS (
    SELECT SELLER_MAINCODE, sum(OPER_TENGE_AMOUNT1) AS total_amount
    FROM table1
    WHERE SELLER_MAINCODE NOT IN (SELECT taxpayer_iin_bin FROM excluded_ul)
    GROUP BY SELLER_MAINCODE
),
pair AS (
    SELECT
        SELLER_MAINCODE,
        CUSTOMER_MAINCODE,
        CUSTOMER_UR_NAME,
        sum(OPER_TENGE_AMOUNT1) AS pair_amount
    FROM table1
    WHERE SELLER_MAINCODE NOT IN (SELECT taxpayer_iin_bin FROM excluded_ul)
    GROUP BY SELLER_MAINCODE, CUSTOMER_MAINCODE, CUSTOMER_UR_NAME
),
table2 AS (
    SELECT DISTINCT
        a.taxpayer_iin_bin AS tp_iin_bin,
        a.founder_iin_bin AS founder_iin_bin,
        a.share_percentage AS share_percentage,
        b.director_iin_bin AS director_iin_bin,
        c.employee_iin_bin AS employee_iin_bin
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
    LEFT JOIN (
        SELECT taxpayer_iin_bin, employee_iin_bin
        FROM AFM_2_1.AFM_2_1_19
        WHERE taxpayer_iin_bin != ''
    ) AS c ON a.taxpayer_iin_bin = c.taxpayer_iin_bin
)
SELECT DISTINCT
    t2.tp_iin_bin AS taxpayer_iin_bin,
    t2.founder_iin_bin AS founder_iin_bin,
    t2.share_percentage AS share_percentage,
    t2.director_iin_bin AS director_iin_bin,
    p.CUSTOMER_MAINCODE AS benefeciary_iin_bin,
    if(right(left(p.CUSTOMER_MAINCODE,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(p.CUSTOMER_MAINCODE,5),1) IN ('1','2','3')
            AND right(left(p.CUSTOMER_MAINCODE,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-8' AS algorithm_code,
    3 AS priority,
    'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date,
    p.CUSTOMER_UR_NAME AS dop_info
FROM pair AS p
JOIN total_ul AS t ON p.SELLER_MAINCODE = t.SELLER_MAINCODE
LEFT JOIN table2 AS t2 ON p.SELLER_MAINCODE = t2.tp_iin_bin
WHERE p.pair_amount >= 10000000
  AND p.pair_amount * 4 >= t.total_amount
  AND p.CUSTOMER_MAINCODE != t2.founder_iin_bin
  AND p.CUSTOMER_MAINCODE != t2.director_iin_bin
  AND p.CUSTOMER_MAINCODE != t2.employee_iin_bin
  AND t2.tp_iin_bin != '';
