-- ============================================================================
-- БС-13 — ЭСФ связи (Предполагаемый БС, балл 3)
-- Источник: AFM_2_1.esf_2025 + AFM_2_1.esf_2026 (~485 млн строк), 12 месяцев.
-- Покупатель-ЮЛ с приобретением > 50 млн тенге закупает у поставщика-ЮЛ
-- 50% и более объёма. БС покупателя (БС-1 / БС-3) или его ФЛ-учредитель
-- имеет родственную связь с учредителем/директором поставщика, либо
-- учредитель/директор поставщика числится работником покупателя.
-- Результат пишется и для покупателя, и для поставщика.
--
-- Из-за объёма ЭСФ расчёт идёт через промежуточные таблицы (шаги 1–5),
-- которые удаляются в конце.
--
-- ЗАВИСИМОСТИ: AFM_6_TEST.AFM_6_1_7 (БС-1), AFM_6_TEST.AFM_6_1_9 (БС-3)
-- Результат: AFM_6_TEST.AFM_6_1_19
-- ============================================================================

-- --- Подготовка: убираем возможные остатки прошлого прогона -----------------
DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_customer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_pairs SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_bs_buyer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_seller_founders SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_links SYNC;

-- --- Шаг 1: покупатели с годовым приобретением более 50 млн тенге -----------
CREATE TABLE AFM_6_TEST.tmp_esf_customer
ENGINE = MergeTree()
ORDER BY IIN_CUSTOMER
AS
SELECT
    IIN_CUSTOMER,
    sum(TURNOVER_SIZE) AS total_turnover
FROM (
    SELECT IIN_CUSTOMER, TURNOVER_SIZE
    FROM AFM_2_1.esf_2025
    WHERE date_diff('day', today(), TURNOVER_DATE) > -365
        AND length(IIN_CUSTOMER) = 12 AND length(IIN_SELLER) = 12
        AND left(right(IIN_CUSTOMER,8),1) IN ('4','5')
        AND left(right(IIN_SELLER,8),1) IN ('4','5')
        AND position(IIN_CUSTOMER, '"') = 0
        AND position(IIN_SELLER, '"') = 0
    UNION ALL
    SELECT IIN_CUSTOMER, TURNOVER_SIZE
    FROM AFM_2_1.esf_2026
    WHERE date_diff('day', today(), TURNOVER_DATE) > -365
        AND length(IIN_CUSTOMER) = 12 AND length(IIN_SELLER) = 12
        AND left(right(IIN_CUSTOMER,8),1) IN ('4','5')
        AND left(right(IIN_SELLER,8),1) IN ('4','5')
        AND position(IIN_CUSTOMER, '"') = 0
        AND position(IIN_SELLER, '"') = 0
)
GROUP BY IIN_CUSTOMER
HAVING sum(TURNOVER_SIZE) > 50000000;

-- --- Шаг 2: пары покупатель-поставщик с долей поставщика 50% и более --------
CREATE TABLE AFM_6_TEST.tmp_esf_pairs
ENGINE = MergeTree()
ORDER BY (IIN_CUSTOMER, IIN_SELLER)
AS
SELECT
    p.IIN_CUSTOMER AS IIN_CUSTOMER,
    p.IIN_SELLER AS IIN_SELLER,
    p.pair_turnover AS pair_turnover,
    c.total_turnover AS total_turnover
FROM (
    SELECT IIN_CUSTOMER, IIN_SELLER, sum(TURNOVER_SIZE) AS pair_turnover
    FROM (
        SELECT IIN_CUSTOMER, IIN_SELLER, TURNOVER_SIZE
        FROM AFM_2_1.esf_2025
        WHERE date_diff('day', today(), TURNOVER_DATE) > -365
            AND length(IIN_CUSTOMER) = 12 AND length(IIN_SELLER) = 12
            AND left(right(IIN_CUSTOMER,8),1) IN ('4','5')
            AND left(right(IIN_SELLER,8),1) IN ('4','5')
            AND position(IIN_CUSTOMER, '"') = 0
            AND position(IIN_SELLER, '"') = 0
        UNION ALL
        SELECT IIN_CUSTOMER, IIN_SELLER, TURNOVER_SIZE
        FROM AFM_2_1.esf_2026
        WHERE date_diff('day', today(), TURNOVER_DATE) > -365
            AND length(IIN_CUSTOMER) = 12 AND length(IIN_SELLER) = 12
            AND left(right(IIN_CUSTOMER,8),1) IN ('4','5')
            AND left(right(IIN_SELLER,8),1) IN ('4','5')
            AND position(IIN_CUSTOMER, '"') = 0
            AND position(IIN_SELLER, '"') = 0
    )
    GROUP BY IIN_CUSTOMER, IIN_SELLER
) p
JOIN AFM_6_TEST.tmp_esf_customer c ON p.IIN_CUSTOMER = c.IIN_CUSTOMER
WHERE p.pair_turnover * 2 >= c.total_turnover;

-- --- Шаг 3: БС-1, БС-3 и ФЛ-учредители покупателей --------------------------
CREATE TABLE AFM_6_TEST.tmp_bs_buyer
ENGINE = MergeTree()
ORDER BY taxpayer_iin_bin
AS
SELECT DISTINCT taxpayer_iin_bin, benefeciary_iin_bin, benefeciary_name
FROM (
    SELECT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        dop_info AS benefeciary_name
    FROM AFM_6_TEST.AFM_6_1_7
    WHERE benefeciary_iin_bin != ''
        AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
    UNION ALL
    SELECT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        dop_info AS benefeciary_name
    FROM AFM_6_TEST.AFM_6_1_9
    WHERE benefeciary_iin_bin != ''
        AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
    UNION ALL
    SELECT
        taxpayer_iin_bin,
        founder_iin_bin AS benefeciary_iin_bin,
        if(founder_ul_name LIKE '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name), founder_ul_name) AS benefeciary_name
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
        AND founder_iin_bin != ''
        AND left(right(founder_iin_bin,8),1) < '4'
        AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_CUSTOMER FROM AFM_6_TEST.tmp_esf_pairs)
);

-- --- Шаг 4: учредители и директора поставщиков ------------------------------
CREATE TABLE AFM_6_TEST.tmp_seller_founders
ENGINE = MergeTree()
ORDER BY tp_iin_bin
AS
SELECT DISTINCT
    f.taxpayer_iin_bin AS tp_iin_bin,
    f.founder_iin_bin AS founder_iin_bin,
    f.share_percentage AS share_percentage,
    d.employee_iin_bin AS director_iin_bin
FROM (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
        AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_SELLER FROM AFM_6_TEST.tmp_esf_pairs)
) f
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
        AND taxpayer_iin_bin IN (SELECT DISTINCT IIN_SELLER FROM AFM_6_TEST.tmp_esf_pairs)
) d ON f.taxpayer_iin_bin = d.taxpayer_iin_bin;

-- --- Шаг 5: родственные связи БС покупателей (в обе стороны) ----------------
CREATE TABLE AFM_6_TEST.tmp_links
ENGINE = MergeTree()
ORDER BY (iin_1, iin_2)
AS
SELECT DISTINCT iin_1, iin_2
FROM (
    SELECT iin_1 AS iin_1, iin_2 AS iin_2
    FROM pfr_dashboard.svz_overroll_table
    WHERE vid_sviazi = 'rod_sviaz'
    UNION ALL
    SELECT iin_2 AS iin_1, iin_1 AS iin_2
    FROM pfr_dashboard.svz_overroll_table
    WHERE vid_sviazi = 'rod_sviaz'
)
WHERE iin_1 IN (SELECT DISTINCT benefeciary_iin_bin FROM AFM_6_TEST.tmp_bs_buyer);

-- --- Шаг 6: итоговый результат ----------------------------------------------
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
        ep.IIN_CUSTOMER,
        ep.IIN_SELLER,
        sf.founder_iin_bin,
        sf.share_percentage,
        sf.director_iin_bin,
        bs.benefeciary_iin_bin,
        bs.benefeciary_name
    FROM AFM_6_TEST.tmp_esf_pairs ep
    JOIN AFM_6_TEST.tmp_bs_buyer bs ON ep.IIN_CUSTOMER = bs.taxpayer_iin_bin
    JOIN AFM_6_TEST.tmp_seller_founders sf ON ep.IIN_SELLER = sf.tp_iin_bin
    LEFT JOIN buyer_employees be_founder
        ON sf.founder_iin_bin = be_founder.employee_iin_bin
        AND ep.IIN_CUSTOMER = be_founder.taxpayer_iin_bin
    LEFT JOIN buyer_employees be_director
        ON sf.director_iin_bin = be_director.employee_iin_bin
        AND ep.IIN_CUSTOMER = be_director.taxpayer_iin_bin
    LEFT JOIN AFM_6_TEST.tmp_links lnk_f
        ON bs.benefeciary_iin_bin = lnk_f.iin_1
        AND sf.founder_iin_bin = lnk_f.iin_2
    LEFT JOIN AFM_6_TEST.tmp_links lnk_d
        ON bs.benefeciary_iin_bin = lnk_d.iin_1
        AND sf.director_iin_bin = lnk_d.iin_2
    WHERE (
        be_founder.employee_iin_bin IS NOT NULL
        OR be_director.employee_iin_bin IS NOT NULL
        OR lnk_f.iin_2 IS NOT NULL
        OR lnk_d.iin_2 IS NOT NULL
    )
    AND bs.benefeciary_iin_bin != ''
)
SELECT DISTINCT
    r.IIN_CUSTOMER AS taxpayer_iin_bin,
    r.founder_iin_bin, r.share_percentage, r.director_iin_bin,
    r.benefeciary_iin_bin,
    if(right(left(r.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(r.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(r.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент', 'Предполагаемый БС')) AS status,
    'БС-13' AS algorithm_code,
    3 AS priority, 'ЭСФ_связи' AS source,
    toString(today()) AS _actual_date,
    r.benefeciary_name AS dop_info
FROM result r
UNION ALL
SELECT DISTINCT
    r.IIN_SELLER AS taxpayer_iin_bin,
    r.founder_iin_bin, r.share_percentage, r.director_iin_bin,
    r.benefeciary_iin_bin,
    if(right(left(r.benefeciary_iin_bin,5),1) = '5', 'Предполагаемый БС - нерезидент',
        if(right(left(r.benefeciary_iin_bin,5),1) IN ('1','2','3')
            AND right(left(r.benefeciary_iin_bin,7),1) = '0',
            'Предполагаемый БС - нерезидент', 'Предполагаемый БС')) AS status,
    'БС-13' AS algorithm_code,
    3 AS priority, 'ЭСФ_связи' AS source,
    toString(today()) AS _actual_date,
    r.benefeciary_name AS dop_info
FROM result r;

-- --- Чистим все временные таблицы -------------------------------------------
DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_customer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_esf_pairs SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_bs_buyer SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_seller_founders SYNC;
DROP TABLE IF EXISTS AFM_6_TEST.tmp_links SYNC;
