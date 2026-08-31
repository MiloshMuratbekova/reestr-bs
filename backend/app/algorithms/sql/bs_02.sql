-- ============================================================================
-- БС-2 — Акционеры МФЦА (Регистрационный БС, балл 0)
-- Источник: AFM_2_11.AFM_2_11_2 — акционеры компаний, зарегистрированных в МФЦА.
-- Результат: AFM_6_TEST.AFM_6_1_8
--
-- В поле ИИН попадает только 12-значное число. Всё прочее — паспорт, КАЗ ИД,
-- иностранный идентификатор — переносится в dop_info: реестр сводится по ИИН,
-- и мусор в этом поле склеил бы разных людей в одного.
-- ============================================================================

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_8 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_8
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS
SELECT DISTINCT
    m.issuer_bin AS taxpayer_iin_bin,
    b.founder_iin_bin AS founder_iin_bin,
    b.share_percentage AS share_percentage,
    c.employee_iin_bin AS director_iin_bin,
    CASE
        WHEN match(COALESCE(m.shareholder_iin_bin,''), '^[0-9]{12}$')
            THEN m.shareholder_iin_bin
        ELSE ''
    END AS benefeciary_iin_bin,
    if(right(left(COALESCE(m.shareholder_iin_bin,''),5),1) = '5',
        'Регистрационный БС - нерезидент',
        if(right(left(COALESCE(m.shareholder_iin_bin,''),5),1) IN ('1','2','3')
            AND right(left(COALESCE(m.shareholder_iin_bin,''),7),1) = '0',
            'Регистрационный БС - нерезидент',
            'Регистрационный БС')) AS status,
    'БС-2' AS algorithm_code,
    0 AS priority,
    'МФЦА' AS source,
    m.`_actual_date` AS _actual_date,
    concat(
        if(COALESCE(m.voting_share,'') != '',
            concat(m.shareholder_name,
                ', количество: ', COALESCE(m.share_quantity,''),
                ', размещённые акции: ', COALESCE(m.outstanding_share,''),
                ', доля: ', m.voting_share),
            concat(COALESCE(m.shareholder_name,''),
                if(COALESCE(m.citizenship,'') != '',
                    concat(', гражданство: ', m.citizenship), ''),
                if(COALESCE(m.passport_number,'') != '',
                    concat(', паспорт: ', m.passport_number), ''),
                if(COALESCE(m.kaz_id,'') != '',
                    concat(', КАЗ ИД: ', m.kaz_id), ''))),
        if(NOT match(COALESCE(m.shareholder_iin_bin,''), '^[0-9]{12}$')
            AND COALESCE(m.shareholder_iin_bin,'') != ''
            AND m.shareholder_iin_bin != 'nan',
            concat(', документ: ', m.shareholder_iin_bin), '')
    ) AS dop_info
FROM AFM_2_11.AFM_2_11_2 AS m
LEFT JOIN (
    SELECT taxpayer_iin_bin, founder_iin_bin, share_percentage
    FROM AFM_2_1_TEST.AFM_2_1_5_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) AS b ON m.issuer_bin = b.taxpayer_iin_bin
LEFT JOIN (
    SELECT taxpayer_iin_bin, employee_iin_bin
    FROM AFM_2_1_TEST.AFM_2_1_6_1
    WHERE _actual_date = (SELECT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
) AS c ON m.issuer_bin = c.taxpayer_iin_bin
WHERE m.issuer_bin != ''
    AND m.shareholder_iin_bin != 'nan'
    AND COALESCE(m.shareholder_iin_bin,'') != ''
    AND m.shareholder_name IS NOT NULL
    AND m.shareholder_name != '';
