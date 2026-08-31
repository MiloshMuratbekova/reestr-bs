-- ============================================================================
-- БС-13 — Взаимосвязанные ЮЛ по данным ЭСФ (Предполагаемый БС, балл 3)
-- Источники: AFM_2_1.esf_2025, AFM_2_1.esf_2026, pfr_dashboard.svz_overroll_table,
-- AFM_2_1.AFM_2_1_19; регистрационные БС берутся из AFM_6_1_7 и AFM_6_1_9.
-- Результат: AFM_6_TEST.AFM_6_1_19
--
-- Покупатель-ЮЛ за последние 12 месяцев приобрёл товаров и услуг более чем на
-- 50 млн тенге, и не менее половины этого объёма пришлось на одного
-- поставщика-ЮЛ. Если при этом БС или учредитель покупателя связан
-- родственными отношениями с учредителем либо руководителем поставщика,
-- или тот числится работником покупателя, — покупатель и поставщик признаются
-- группой взаимосвязанных лиц, и БС покупателя записывается обоим.
--
-- Объём ЭСФ измеряется сотнями миллионов строк, поэтому расчёт разбит на шаги
-- через промежуточные таблицы: одним запросом соединение не выполняется по
-- памяти. Промежуточные таблицы удаляются в конце.
--
-- Считается ПОСЛЕ БС-1 и БС-3: шаг 3 читает их таблицы результатов.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_customer SYNC;

CREATE TABLE AFM_6_TEST.tmp_esf_customer
ENGINE = MergeTree()
ORDER BY (assumeNotNull(IIN_CUSTOMER))
AS
SELECT
    IIN_CUSTOMER,
    sum(COALESCE(CAST(TURNOVER_SIZE AS Decimal(38,2)), 0)) AS YEARTURNOVER_SIZE
FROM (
    SELECT IIN_CUSTOMER, TURNOVER_SIZE
    FROM AFM_2_1.esf_2025
    WHERE date_diff('day', today(), TURNOVER_DATE) > -365
      AND IIN_SELLER != '' AND IIN_CUSTOMER != ''
      AND (IIN_SELLER LIKE '____4%' OR IIN_SELLER LIKE '____5%')
      AND (IIN_CUSTOMER LIKE '____4%' OR IIN_CUSTOMER LIKE '____5%')
      AND LENGTH(IIN_SELLER) = 12 AND LENGTH(IIN_CUSTOMER) = 12
      AND TURNOVER_SIZE IS NOT NULL
    UNION ALL
    SELECT IIN_CUSTOMER, TURNOVER_SIZE
    FROM AFM_2_1.esf_2026
    WHERE date_diff('day', today(), TURNOVER_DATE) > -365
      AND IIN_SELLER != '' AND IIN_CUSTOMER != ''
      AND (IIN_SELLER LIKE '____4%' OR IIN_SELLER LIKE '____5%')
      AND (IIN_CUSTOMER LIKE '____4%' OR IIN_CUSTOMER LIKE '____5%')
      AND LENGTH(IIN_SELLER) = 12 AND LENGTH(IIN_CUSTOMER) = 12
      AND TURNOVER_SIZE IS NOT NULL
)
GROUP BY IIN_CUSTOMER
HAVING sum(COALESCE(CAST(TURNOVER_SIZE AS Decimal(38,2)), 0)) >= 50000000;

DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_pairs SYNC;

CREATE TABLE AFM_6_TEST.tmp_esf_pairs
ENGINE = MergeTree()
ORDER BY (assumeNotNull(IIN_CUSTOMER), assumeNotNull(IIN_SELLER))
AS
SELECT
    p.IIN_CUSTOMER,
    p.IIN_SELLER,
    p.TOTALTURNOVER_SIZE,
    c.YEARTURNOVER_SIZE
FROM (
    SELECT
        IIN_CUSTOMER,
        IIN_SELLER,
        sum(COALESCE(CAST(TURNOVER_SIZE AS Decimal(38,2)), 0)) AS TOTALTURNOVER_SIZE
    FROM (
        SELECT IIN_CUSTOMER, IIN_SELLER, TURNOVER_SIZE
        FROM AFM_2_1.esf_2025
        WHERE date_diff('day', today(), TURNOVER_DATE) > -365
          AND IIN_SELLER != '' AND IIN_CUSTOMER != ''
          AND (IIN_SELLER LIKE '____4%' OR IIN_SELLER LIKE '____5%')
          AND (IIN_CUSTOMER LIKE '____4%' OR IIN_CUSTOMER LIKE '____5%')
          AND LENGTH(IIN_SELLER) = 12 AND LENGTH(IIN_CUSTOMER) = 12
          AND TURNOVER_SIZE IS NOT NULL
        UNION ALL
        SELECT IIN_CUSTOMER, IIN_SELLER, TURNOVER_SIZE
        FROM AFM_2_1.esf_2026
        WHERE date_diff('day', today(), TURNOVER_DATE) > -365
          AND IIN_SELLER != '' AND IIN_CUSTOMER != ''
          AND (IIN_SELLER LIKE '____4%' OR IIN_SELLER LIKE '____5%')
          AND (IIN_CUSTOMER LIKE '____4%' OR IIN_CUSTOMER LIKE '____5%')
          AND LENGTH(IIN_SELLER) = 12 AND LENGTH(IIN_CUSTOMER) = 12
          AND TURNOVER_SIZE IS NOT NULL
    )
    GROUP BY IIN_CUSTOMER, IIN_SELLER
) AS p
JOIN AFM_6_TEST.tmp_esf_customer AS c ON p.IIN_CUSTOMER = c.IIN_CUSTOMER
-- Доля поставщика не менее 50% всего объёма покупателя
WHERE p.TOTALTURNOVER_SIZE * 2 >= c.YEARTURNOVER_SIZE;

DROP TABLE IF EXISTS AFM_6_TEST.tmp_bs_buyer SYNC;

CREATE TABLE AFM_6_TEST.tmp_bs_buyer
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT taxpayer_iin_bin, benefeciary_iin_bin, dop_info AS benefeciary_name
FROM AFM_6_TEST.AFM_6_1_7
WHERE benefeciary_iin_bin != ''
  AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
UNION ALL
SELECT taxpayer_iin_bin, benefeciary_iin_bin, dop_info AS benefeciary_name
FROM AFM_6_TEST.AFM_6_1_9
WHERE benefeciary_iin_bin != ''
  AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
UNION ALL
SELECT
    taxpayer_iin_bin,
    founder_iin_bin AS benefeciary_iin_bin,
    if(founder_ul_name LIKE '',
        concat(founder_last_name, ' ', founder_first_name, ' ', founder_part_name),
        founder_ul_name) AS benefeciary_name
FROM AFM_2_1_TEST.AFM_2_1_5_1
WHERE taxpayer_iin_bin != ''
  AND founder_iin_bin != ''
  AND left(right(founder_iin_bin,8),1) NOT IN ('4','5')
  AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
  AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs);

DROP TABLE IF EXISTS AFM_6_TEST.tmp_seller_founders SYNC;

CREATE TABLE AFM_6_TEST.tmp_seller_founders
ENGINE = MergeTree()
ORDER BY (assumeNotNull(tp_iin_bin))
AS
SELECT DISTINCT
    a.taxpayer_iin_bin AS tp_iin_bin,
    a.founder_iin_bin AS founder_iin_bin,
    a.share_percentage AS share_percentage,
    b.director_iin_bin AS director_iin_bin
FROM (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE taxpayer_iin_bin != ''
      AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_SELLER FROM AFM_6_TEST.tmp_esf_pairs)
      AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS a
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin AS director_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE taxpayer_iin_bin != ''
      AND _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS b ON a.taxpayer_iin_bin = b.taxpayer_iin_bin;

DROP TABLE IF EXISTS AFM_6_TEST.tmp_links SYNC;

CREATE TABLE AFM_6_TEST.tmp_links
ENGINE = MergeTree()
ORDER BY (assumeNotNull(iin_1), assumeNotNull(iin_2))
AS
SELECT iin_1, iin_2
FROM pfr_dashboard.svz_overroll_table
WHERE vid_sviazi = 'rod_sviaz'
  AND (
      iin_1 IN (SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.tmp_bs_buyer)
      OR iin_2 IN (SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.tmp_bs_buyer)
  )
UNION ALL
SELECT iin_2 AS iin_1, iin_1 AS iin_2
FROM pfr_dashboard.svz_overroll_table
WHERE vid_sviazi = 'rod_sviaz'
  AND (
      iin_1 IN (SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.tmp_bs_buyer)
      OR iin_2 IN (SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.tmp_bs_buyer)
  );

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_19 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_19
ENGINE = MergeTree()
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
WITH
buyer_employees AS (
    SELECT DISTINCT employee_iin_bin, taxpayer_iin_bin
    FROM AFM_2_1.AFM_2_1_19
    WHERE employee_iin_bin != '' AND taxpayer_iin_bin != ''
      AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
),
result AS (
    SELECT DISTINCT
        ep.IIN_CUSTOMER AS IIN_CUSTOMER,
        ep.IIN_SELLER AS IIN_SELLER,
        sf.founder_iin_bin AS founder_iin_bin,
        sf.share_percentage AS share_percentage,
        sf.director_iin_bin AS director_iin_bin,
        bs.benefeciary_iin_bin AS benefeciary_iin_bin,
        bs.benefeciary_name AS benefeciary_name
    FROM AFM_6_TEST.tmp_esf_pairs AS ep
    JOIN AFM_6_TEST.tmp_bs_buyer AS bs ON ep.IIN_CUSTOMER = bs.taxpayer_iin_bin
    JOIN AFM_6_TEST.tmp_seller_founders AS sf ON ep.IIN_SELLER = sf.tp_iin_bin
    LEFT JOIN buyer_employees AS be_founder
        ON sf.founder_iin_bin = be_founder.employee_iin_bin
        AND ep.IIN_CUSTOMER = be_founder.taxpayer_iin_bin
    LEFT JOIN buyer_employees AS be_director
        ON sf.director_iin_bin = be_director.employee_iin_bin
        AND ep.IIN_CUSTOMER = be_director.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.tmp_links AS lnk_f
        ON bs.benefeciary_iin_bin = lnk_f.iin_1
        AND sf.founder_iin_bin = lnk_f.iin_2
    LEFT JOIN AFM_6_TEST.tmp_links AS lnk_d
        ON bs.benefeciary_iin_bin = lnk_d.iin_1
        AND sf.director_iin_bin = lnk_d.iin_2
    WHERE (
        be_founder.employee_iin_bin != ''
        OR be_director.employee_iin_bin != ''
        OR lnk_f.iin_2 != ''
        OR lnk_d.iin_2 != ''
    )
    AND bs.benefeciary_iin_bin != ''
)
SELECT DISTINCT
    r.IIN_CUSTOMER AS taxpayer_iin_bin,
    r.founder_iin_bin AS founder_iin_bin,
    r.share_percentage AS share_percentage,
    r.director_iin_bin AS director_iin_bin,
    r.benefeciary_iin_bin AS benefeciary_iin_bin,
    if(right(left(r.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(r.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(r.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-13' AS algorithm_code,
    3 AS priority,
    'ЭСФ_связи' AS source,
    toString(today()) AS _actual_date,
    r.benefeciary_name AS dop_info
FROM result AS r
UNION ALL
SELECT DISTINCT
    r.IIN_SELLER AS taxpayer_iin_bin,
    r.founder_iin_bin AS founder_iin_bin,
    r.share_percentage AS share_percentage,
    r.director_iin_bin AS director_iin_bin,
    r.benefeciary_iin_bin AS benefeciary_iin_bin,
    if(right(left(r.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(r.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(r.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент',
            'Предполагаемый БС')) AS status,
    'БС-13' AS algorithm_code,
    3 AS priority,
    'ЭСФ_связи' AS source,
    toString(today()) AS _actual_date,
    r.benefeciary_name AS dop_info
FROM result AS r;

DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_customer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_pairs SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_bs_buyer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_seller_founders SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_links SYNC;
