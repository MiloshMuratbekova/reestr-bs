-- ============================================================================
-- БС-1 — Реестр МЮ (Регистрационный БС, балл не присваивается)
-- Источник: AFM_2_10_TEST.AFM_2_10_2 — официальный реестр БС Министерства юстиции.
-- Результат: AFM_6_TEST.AFM_6_1_7
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_7;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_7
AS
SELECT distinct
	a.taxpayer_iin_bin as taxpayer_iin_bin
	, b.founder_iin_bin as founder_iin_bin
	, b.share_percentage  as share_percentage
	, c.employee_iin_bin as  director_iin_bin
	, a.benefeciary_iin_bin as benefeciary_iin_bin
	, if(right(left(a.benefeciary_iin_bin,5),1) = '5','Регистрационный БС - нерезидент',
			if(right(left(a.benefeciary_iin_bin,5),1) in ('1','2','3') and right(left(a.benefeciary_iin_bin,7),1)='0','Регистрационный БС - нерезидент',
				'Регистрационный БС'
			)
	) as status
	, 'БС-1' as algorithm_code
	, 0 as priority
	, 'МЮ_бс' as source
	, a.`_actual_date` as _actual_date
	, if(b.founder_name != '' AND b.founder_name IS NOT NULL,
     b.founder_name,
     a.benefeciary_name) as dop_info
FROM AFM_2_10_TEST.AFM_2_10_2 a
left join
(
	select
		taxpayer_iin_bin
		,founder_iin_bin
		, if(founder_ul_name like '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),founder_ul_name) as founder_name
		,share_percentage
	from AFM_2_1_TEST.AFM_2_1_5_1
	where `_actual_date` = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
) b
	on a.taxpayer_iin_bin = b.taxpayer_iin_bin
left join
	(
		select *
		from AFM_2_1_TEST.AFM_2_1_6_1
		where `_actual_date` = ( SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
	)c
	on a.taxpayer_iin_bin = c.taxpayer_iin_bin;

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_7 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_7
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_7;
