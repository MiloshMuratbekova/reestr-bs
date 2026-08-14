-- ============================================================================
-- БС-11 — Дивиденды ФМ (Предполагаемый БС, балл 3)
-- Источник: pfr_dashboard.asloy + pfr_dashboard.asloy_dopinfo, 6 месяцев.
-- OPER_IDTYPE = 561 (распределение чистой прибыли, выплата дивидендов)
-- либо dopinfo содержит «дивид». Порог суммы 1 млн тенге.
-- ФЛ не должен уже числиться как БС-1 или БС-3.
-- ЗАВИСИМОСТИ: AFM_6_TEST.AFM_6_1_7 (БС-1), AFM_6_TEST.AFM_6_1_9 (БС-3)
-- Результат: AFM_6_TEST.AFM_6_1_17
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_17;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_17
AS
WITH table1 AS (
    SELECT SELLER_MAINCODE AS ul, CUSTOMER_MAINCODE AS fl, CUSTOMER_UR_NAME AS fl_name, OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
        AND (OPER_IDTYPE = '561' OR MESS_ID IN (
            SELECT MESS_ID FROM pfr_dashboard.asloy_dopinfo WHERE dopinfo LIKE '%дивид%'))
        AND date_diff('day', today(), DATE_OPER) > -180
        AND CUSTOMER_MAINCODE != '' AND SELLER_MAINCODE != ''
        AND left(right(CUSTOMER_MAINCODE,8),1) NOT IN ('4','5')
        AND left(right(SELLER_MAINCODE,8),1) IN ('4','5')
),
table2 AS (
    SELECT DISTINCT a.taxpayer_iin_bin AS tp_iin_bin, founder_iin_bin, share_percentage, director_iin_bin, employee_iin_bin
    FROM (SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage FROM AFM_2_1_TEST.AFM_2_1_5_1
          WHERE taxpayer_iin_bin != '' AND _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)) a
    LEFT JOIN (SELECT taxpayer_iin_bin, employee_iin_bin AS director_iin_bin FROM AFM_2_1_TEST.AFM_2_1_6_1
               WHERE taxpayer_iin_bin != '' AND _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)) b ON a.taxpayer_iin_bin=b.taxpayer_iin_bin
    LEFT JOIN (SELECT taxpayer_iin_bin, employee_iin_bin FROM AFM_2_1.AFM_2_1_19 WHERE taxpayer_iin_bin != '') c ON a.taxpayer_iin_bin=c.taxpayer_iin_bin
),
bs1_bs3 AS (
    SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.AFM_6_1_7 WHERE benefeciary_iin_bin != ''
    UNION ALL
    SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.AFM_6_1_9 WHERE benefeciary_iin_bin != ''
)
SELECT DISTINCT t2.tp_iin_bin AS taxpayer_iin_bin, t2.founder_iin_bin, t2.share_percentage, t2.director_iin_bin,
    t1.fl AS benefeciary_iin_bin,
    if(right(left(t1.fl,5),1)='5','Предполагаемый БС - нерезидент',
        if(right(left(t1.fl,5),1) IN ('1','2','3') AND right(left(t1.fl,7),1)='0',
            'Предполагаемый БС - нерезидент','Предполагаемый БС')) AS status,
    'БС-11' AS algorithm_code, 3 AS priority, 'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date, t1.fl_name AS dop_info
FROM (SELECT fl, fl_name, ul, sum(OPER_TENGE_AMOUNT1) AS OPER_TENGE_AMOUNT2
      FROM table1 GROUP BY fl, fl_name, ul HAVING sum(OPER_TENGE_AMOUNT1) >= 1000000) t1
LEFT JOIN table2 t2 ON t1.ul=t2.tp_iin_bin
WHERE t1.fl != t2.founder_iin_bin AND t1.fl != t2.director_iin_bin AND t1.fl != t2.employee_iin_bin
    AND t2.tp_iin_bin IS NOT NULL AND t2.tp_iin_bin != ''
    AND t1.fl NOT IN (SELECT benefeciary_iin_bin FROM bs1_bs3);

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_17 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_17
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_17;
