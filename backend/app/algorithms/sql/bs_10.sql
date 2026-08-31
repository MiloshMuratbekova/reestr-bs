-- ============================================================================
-- БС-10 — Финансовая помощь от ФЛ в адрес ЮЛ (Предполагаемый БС, балл 3)
-- Источник: pfr_dashboard.asloy совместно с pfr_dashboard.asloy_dopinfo.
-- Результат: AFM_6_TEST.AFM_6_1_16
--
-- Направление обратное БС-8: плательщик — физическое лицо, получатель —
-- юридическое. Отбираются операции, в дополнительной информации которых есть
-- признаки безвозмездной, возвратной помощи или краткосрочного займа.
-- Период — последние 6 календарных месяцев, порог суммы — 100 млн тенге.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_16 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_16
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT
        SELLER_MAINCODE AS fl,
        SELLER_UR_NAME AS fl_name,
        CUSTOMER_MAINCODE AS ul,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
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
             OR dopinfo LIKE '%ВЫДАЧА КРАТКОСРОЧНЫХ ЗАЙМОВ%'
      )
      AND date_diff('day', today(), DATE_OPER) > -180
      AND CUSTOMER_MAINCODE != ''
      AND SELLER_MAINCODE != ''
      AND left(right(CUSTOMER_MAINCODE,8),1) IN ('4','5')
      AND left(right(SELLER_MAINCODE,8),1) NOT IN ('4','5')
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
    t1.fl AS benefeciary_iin_bin,
    if(right(left(t1.fl,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(t1.fl,5),1) IN ('1','2','3')
            AND right(left(t1.fl,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-10' AS algorithm_code,
    3 AS priority,
    'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date,
    t1.fl_name AS dop_info
FROM (
    SELECT fl, fl_name, ul, sum(OPER_TENGE_AMOUNT1) AS OPER_TENGE_AMOUNT2
    FROM table1
    GROUP BY fl, fl_name, ul
    HAVING sum(OPER_TENGE_AMOUNT1) >= 100000000
) AS t1
LEFT JOIN table2 AS t2 ON t1.ul = t2.tp_iin_bin
WHERE t1.fl != t2.founder_iin_bin
  AND t1.fl != t2.director_iin_bin
  AND t2.tp_iin_bin != '';
