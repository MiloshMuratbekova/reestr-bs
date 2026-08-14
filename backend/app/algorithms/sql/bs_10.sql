-- ============================================================================
-- БС-10 — Финансовая помощь ФМ (Предполагаемый БС, балл 3)
-- Источник: pfr_dashboard.asloy + pfr_dashboard.asloy_dopinfo, 6 месяцев.
-- ФЛ (SELLER) направляет безвозмездную финансовую помощь ЮЛ (CUSTOMER).
-- Исключён КВО 1671; исключены МФО, банки, ломбарды, кредитные товарищества.
-- Порог: >= 10 млн тенге И >= 25% всех поступлений в адрес ЮЛ.
-- Результат: AFM_6_TEST.AFM_6_1_16
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_16;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_16
AS
WITH table1 AS (
    SELECT SELLER_MAINCODE AS fl, SELLER_UR_NAME AS fl_name, CUSTOMER_MAINCODE AS ul, OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL AND OPER_IDVIEW != '1671'
        AND MESS_ID IN (SELECT MESS_ID FROM pfr_dashboard.asloy_dopinfo
            WHERE dopinfo LIKE '%безвоз%' OR dopinfo LIKE '%фин. помощь%' OR dopinfo LIKE '%финпом%'
                OR dopinfo LIKE '%фин.пом%' OR dopinfo LIKE '%финансовая помощь%'
                OR dopinfo LIKE '%возвратная помощь%' OR dopinfo LIKE '%выдача краткосрочных займов%'
                OR dopinfo LIKE '%ЗАЙМ%')
        AND date_diff('day', today(), DATE_OPER) > -180
        AND CUSTOMER_MAINCODE != '' AND SELLER_MAINCODE != ''
        AND left(right(CUSTOMER_MAINCODE,8),1) IN ('4','5')
        AND left(right(SELLER_MAINCODE,8),1) NOT IN ('4','5')
),
excluded_ul AS (
    SELECT DISTINCT taxpayer_iin_bin FROM AFM_2_1_TEST.AFM_2_1_9
    WHERE lower(taxpayer_name) LIKE '%мфо%' OR lower(taxpayer_name) LIKE '%банк%'
        OR lower(taxpayer_name) LIKE '%ломбард%' OR lower(taxpayer_name) LIKE '%кредитное товарищество%'
),
total_ul AS (SELECT ul, sum(OPER_TENGE_AMOUNT1) AS total_amount FROM table1
    WHERE ul NOT IN (SELECT taxpayer_iin_bin FROM excluded_ul) GROUP BY ul),
pair AS (SELECT fl, fl_name, ul, sum(OPER_TENGE_AMOUNT1) AS pair_amount FROM table1
    WHERE ul NOT IN (SELECT taxpayer_iin_bin FROM excluded_ul) GROUP BY fl, fl_name, ul),
table2 AS (
    SELECT DISTINCT a.taxpayer_iin_bin AS tp_iin_bin, founder_iin_bin, share_percentage, director_iin_bin, employee_iin_bin
    FROM (SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage FROM AFM_2_1_TEST.AFM_2_1_5_1
          WHERE taxpayer_iin_bin != '' AND _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)) a
    LEFT JOIN (SELECT taxpayer_iin_bin, employee_iin_bin AS director_iin_bin FROM AFM_2_1_TEST.AFM_2_1_6_1
               WHERE taxpayer_iin_bin != '' AND _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)) b ON a.taxpayer_iin_bin=b.taxpayer_iin_bin
    LEFT JOIN (SELECT taxpayer_iin_bin, employee_iin_bin FROM AFM_2_1.AFM_2_1_19 WHERE taxpayer_iin_bin != '') c ON a.taxpayer_iin_bin=c.taxpayer_iin_bin
)
SELECT DISTINCT t2.tp_iin_bin AS taxpayer_iin_bin, t2.founder_iin_bin, t2.share_percentage, t2.director_iin_bin,
    p.fl AS benefeciary_iin_bin,
    if(right(left(p.fl,5),1)='5','Предполагаемый БС - нерезидент',
        if(right(left(p.fl,5),1) IN ('1','2','3') AND right(left(p.fl,7),1)='0',
            'Предполагаемый БС - нерезидент','Предполагаемый БС')) AS status,
    'БС-10' AS algorithm_code, 3 AS priority, 'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date, p.fl_name AS dop_info
FROM pair p
JOIN total_ul t ON p.ul=t.ul
LEFT JOIN table2 t2 ON p.ul=t2.tp_iin_bin
WHERE p.pair_amount >= 10000000 AND p.pair_amount*4 >= t.total_amount
    AND p.fl != t2.founder_iin_bin AND p.fl != t2.director_iin_bin
    AND t2.tp_iin_bin IS NOT NULL AND t2.tp_iin_bin != '';

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_16 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_16
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_16;
