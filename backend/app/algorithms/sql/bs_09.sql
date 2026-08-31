-- ============================================================================
-- БС-9 — Действия от имени ЮЛ и выгодоприобретатели (Предполагаемый БС, балл 2)
-- Источник: pfr_dashboard.asloy.
-- Результат: AFM_6_TEST.AFM_6_1_15
--
-- ФЛ за последние 6 месяцев выступает от имени и по поручению ЮЛ
-- (BEHALF_PERSON_MAINCODE) либо является выгодоприобретателем
-- (BENEFICIARY_MAINCODE) по операциям ЮЛ — как со стороны плательщика
-- (SELLER), так и со стороны получателя (CUSTOMER).
--
-- Порог двойной: сумма по паре больше 10 млн тенге И составляет не менее 25%
-- оборота ЮЛ. Условие записано умножением, чтобы не делить на ноль.
-- ФЛ не должно числиться у этого ЮЛ учредителем, руководителем или работником.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_15 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_15
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH table1 AS (
    SELECT DISTINCT
        BEHALF_PERSON_MAINCODE AS fl,
        BEHALF_PERSON_UR_NAME AS fl_name,
        SELLER_MAINCODE AS ul,
        BEHALF_PERSON_UR_NAME AS ben_name,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND date_diff('day', today(), DATE_OPER) > -180
      AND BEHALF_PERSON_MAINCODE != ''
      AND left(right(BEHALF_PERSON_MAINCODE,8),1) NOT IN ('4','5')
      AND SELLER_MAINCODE != ''
      AND left(right(SELLER_MAINCODE,8),1) IN ('4','5')

    UNION ALL

    SELECT DISTINCT
        BEHALF_PERSON_MAINCODE AS fl,
        BEHALF_PERSON_UR_NAME AS fl_name,
        CUSTOMER_MAINCODE AS ul,
        BEHALF_PERSON_UR_NAME AS ben_name,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND date_diff('day', today(), DATE_OPER) > -180
      AND BEHALF_PERSON_MAINCODE != ''
      AND left(right(BEHALF_PERSON_MAINCODE,8),1) NOT IN ('4','5')
      AND CUSTOMER_MAINCODE != ''
      AND left(right(CUSTOMER_MAINCODE,8),1) IN ('4','5')

    UNION ALL

    SELECT DISTINCT
        BENEFICIARY_MAINCODE AS fl,
        BENEFICIARY_UR_NAME AS fl_name,
        SELLER_MAINCODE AS ul,
        BENEFICIARY_UR_NAME AS ben_name,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND date_diff('day', today(), DATE_OPER) > -180
      AND BENEFICIARY_MAINCODE != ''
      AND left(right(BENEFICIARY_MAINCODE,8),1) NOT IN ('4','5')
      AND SELLER_MAINCODE != ''
      AND left(right(SELLER_MAINCODE,8),1) IN ('4','5')

    UNION ALL

    SELECT DISTINCT
        BENEFICIARY_MAINCODE AS fl,
        BENEFICIARY_UR_NAME AS fl_name,
        CUSTOMER_MAINCODE AS ul,
        BENEFICIARY_UR_NAME AS ben_name,
        OPER_TENGE_AMOUNT AS OPER_TENGE_AMOUNT1
    FROM pfr_dashboard.asloy
    WHERE OPER_TENGE_AMOUNT IS NOT NULL
      AND date_diff('day', today(), DATE_OPER) > -180
      AND BENEFICIARY_MAINCODE != ''
      AND left(right(BENEFICIARY_MAINCODE,8),1) NOT IN ('4','5')
      AND CUSTOMER_MAINCODE != ''
      AND left(right(CUSTOMER_MAINCODE,8),1) IN ('4','5')
),
total_ul AS (
    SELECT ul, sum(OPER_TENGE_AMOUNT1) AS total_amount
    FROM table1
    GROUP BY ul
),
pair AS (
    SELECT fl, fl_name, ul, ben_name, sum(OPER_TENGE_AMOUNT1) AS pair_amount
    FROM table1
    GROUP BY fl, fl_name, ul, ben_name
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
    p.fl AS benefeciary_iin_bin,
    if(right(left(p.fl,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(p.fl,5),1) IN ('1','2','3')
            AND right(left(p.fl,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-9' AS algorithm_code,
    2 AS priority,
    'СФМ_ФМ1' AS source,
    toString(today()) AS _actual_date,
    p.ben_name AS dop_info
FROM pair AS p
JOIN total_ul AS t ON p.ul = t.ul
LEFT JOIN table2 AS t2 ON p.ul = t2.tp_iin_bin
WHERE p.pair_amount >= 10000000
  AND p.pair_amount * 4 >= t.total_amount
  AND p.fl != t2.founder_iin_bin
  AND p.fl != t2.director_iin_bin
  AND p.fl != t2.employee_iin_bin
  AND t2.tp_iin_bin != '';
