-- ============================================================================
-- БС-22 — КГД нерезиденты (Регистрационный БС, балл не присваивается)
-- Источник: AFM_2_1.AFM_2_1_kgd_nonresident — налоговое заявление
-- о регистрации ЮЛ-нерезидента.
-- Результат: AFM_6_TEST.AFM_6_1_28
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_28;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_28
AS
SELECT * FROM (
    SELECT
        k.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.founder_iin_bin, b.share_percentage,
        c.employee_iin_bin AS director_iin_bin,
        k.benefeciary_iin_bin,
        if(right(left(k.benefeciary_iin_bin,5),1)='5','Регистрационный БС - нерезидент',
            if(right(left(k.benefeciary_iin_bin,5),1) IN ('1','2','3') AND right(left(k.benefeciary_iin_bin,7),1)='0',
                'Регистрационный БС - нерезидент','Регистрационный БС')) AS status,
        'БС-22' AS algorithm_code, 0 AS priority, 'КГД_нерезидент' AS source,
        toString(today()) AS _actual_date,
        concat(COALESCE(k.benefeciary_name,''),
            if(COALESCE(k.benefeciary_foreign_id,'') != '', concat(', ИД в стране: ',k.benefeciary_foreign_id),''),
            if(COALESCE(k.benefeciary_citizenship,'') != '', concat(', гражданство: ',k.benefeciary_citizenship),''),
            if(COALESCE(k.share_percentage,'') != '', concat(', доля: ',k.share_percentage,'%'),'')) AS dop_info
    FROM AFM_2_1.AFM_2_1_kgd_nonresident k
    LEFT JOIN (SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage FROM AFM_2_1_TEST.AFM_2_1_5_1
               WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)) b ON k.taxpayer_iin_bin=b.taxpayer_iin_bin
    LEFT JOIN (SELECT taxpayer_iin_bin, employee_iin_bin FROM AFM_2_1_TEST.AFM_2_1_6_1
               WHERE _actual_date=(SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)) c ON k.taxpayer_iin_bin=c.taxpayer_iin_bin
    WHERE k.taxpayer_iin_bin != '' AND k.benefeciary_iin_bin != ''
);

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_28 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_28
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_28;
