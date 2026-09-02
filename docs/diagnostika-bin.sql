-- Куда девается бенефициар: по шагам, для одного БИН.
-- Подставьте БИН вместо ЗНАЧЕНИЕ и выполните целиком.
WITH raw AS (
    SELECT 'БС-1' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_7 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-2' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_8 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-3' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_9 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-4' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_10 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-5' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_11 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-6' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_12 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-7' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_13 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-8' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_14 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-9' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_15 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-10' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_16 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-11' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_17 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-12' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_18 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-13' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_19 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-15' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_21 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-16' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_22 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-22' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_28 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-17' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_23 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-18' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_24 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-19' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_25 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-20' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_26 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-21' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_27 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-23' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_29 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
    UNION ALL
    SELECT 'БС-24' AS algorithm_code,
           ifNull(toString(t.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
           ifNull(toString(t.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
           ifNull(toString(t.dop_info), '') AS dop_info
    FROM AFM_6_TEST.AFM_6_1_30 AS t
    WHERE ifNull(toString(t.taxpayer_iin_bin), '') = {bin:String}
),
cleaned AS (
    SELECT r.algorithm_code, r.benefeciary_iin_bin AS iin_raw,
           if(match(trimBoth(r.benefeciary_iin_bin), '^[0-9]{12}$') AND trimBoth(r.benefeciary_iin_bin) != '000000000000' AND lowerUTF8(trimBoth(r.benefeciary_iin_bin)) NOT IN ('-', '--', '0', '000000000', '000000000000', 'нет', 'отсутствует'), trimBoth(r.benefeciary_iin_bin), '') AS iin_clean, r.dop_info
    FROM raw AS r
)
SELECT
    c.algorithm_code                                              AS `алгоритм`,
    c.iin_raw                                                     AS `иин_в_таблице`,
    c.iin_clean                                                   AS `иин_после_чистки`,
    if(c.iin_clean = '', 'ИИН отброшен как заглушка', '')         AS `замечание_1`,
    if(c.iin_clean = '' AND c.dop_info = '',
       'нет ни ИИН, ни имени — строка выпадает', '')              AS `замечание_2`,
    if(c.iin_clean != '' AND left(right(c.iin_clean, 8), 1) IN ('4','5'),
       'бенефициар — ЮЛ, нужна раскрутка до ФЛ', '')              AS `замечание_3`,
    substring(c.dop_info, 1, 60)                                  AS `сведения`
FROM cleaned AS c
ORDER BY c.algorithm_code
