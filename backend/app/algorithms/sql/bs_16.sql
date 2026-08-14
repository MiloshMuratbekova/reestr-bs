-- ============================================================================
-- БС-16 — Ответ ЮЛ на запрос АФМ (Предполагаемый БС, балл 2)
-- Источник: AFM_2_6.AFM_2_6_9 — ответы юридических лиц на запросы АФМ
-- по своим бенефициарным собственникам.
-- Результат: AFM_6_TEST.AFM_6_1_22
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_22;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_22
AS
SELECT * FROM (
    SELECT
        a.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.founder_iin_bin,
        b.share_percentage,
        c.employee_iin_bin AS director_iin_bin,
        a.benefeciary_iin_bin,
        if(right(left(a.benefeciary_iin_bin,5),1)='5','Предполагаемый БС - нерезидент',
            if(right(left(a.benefeciary_iin_bin,5),1) IN ('1','2','3') AND right(left(a.benefeciary_iin_bin,7),1)='0',
                'Предполагаемый БС - нерезидент','Предполагаемый БС')) AS status,
        'БС-16' AS algorithm_code, 2 AS priority, 'Ответ_ЮЛ' AS source,
        toString(today()) AS _actual_date,
        a.benefeciary_name AS dop_info
    FROM AFM_2_6.AFM_2_6_9 a
    LEFT JOIN (
        SELECT taxpayer_iin_bin, founder_iin_bin,
            if(founder_ul_name LIKE '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name), founder_ul_name) AS founder_name,
            share_percentage
        FROM AFM_2_1_TEST.AFM_2_1_5_1
        WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
    ) b ON a.taxpayer_iin_bin=b.taxpayer_iin_bin
    LEFT JOIN (SELECT * FROM AFM_2_1_TEST.AFM_2_1_6_1
               WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)) c ON a.taxpayer_iin_bin=c.taxpayer_iin_bin
);

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_22 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_22
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_22;
