-- ============================================================================
-- БС-3 — Учредители с долей 25% и более (Регистрационный БС, балл не присваивается)
-- ЮЛ без признаков некорректности 1 и 2: учредители указаны, сумма долей
-- в диапазоне [99.9; 100.1]. Государственные компании исключены.
-- Результат: AFM_6_TEST.AFM_6_1_9
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_9;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_9
AS
with table1 as
(
	select
		taxpayer_iin_bin
		,if(substring(',',1,length(share_percentage))=',' and share_percentage != '',cast(replace(share_percentage,',','.') as Decimal(10,2)),floor(cast(concat(share_percentage,'.00') as Decimal(10,2)),2)) as share_percentage
		,founder_iin_bin
		, if(founder_ul_name like '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),founder_ul_name) as founder_name
		,`_actual_date`
	from AFM_2_1_TEST.AFM_2_1_5_1
	WHERE _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
	AND taxpayer_iin_bin in
	(
		select taxpayer_iin_bin
		from AFM_2_1.AFM_2_1_8
		where ownership_type not like 'Государственная собственность'
			AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1.AFM_2_1_8)
	)
	and
	(
		taxpayer_iin_bin in
		(
			select taxpayer_iin_bin
			from (
				select taxpayer_iin_bin, trunc(cast(share as Decimal(10,2)),2) as g
				from
				(
					select taxpayer_iin_bin, replace(share_percentage,',','.') as share
					from AFM_2_1_TEST.AFM_2_1_5_1
					where share_percentage like '%,%' and share_percentage not like ''
						AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
				) a
				union all
				select taxpayer_iin_bin, floor(cast(concat(share_percentage,'.00') as Decimal(10,2)),2) as g
				from AFM_2_1_TEST.AFM_2_1_5_1
				where share_percentage not like '%,%' and share_percentage not like '0' and share_percentage not like ''
					AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
				) b
			group by taxpayer_iin_bin
			having sum(g) >= 99.9 and sum(g) <= 100.1
		)
		or
		taxpayer_name in
		(
			select taxpayer_name
			from (
				select taxpayer_name, trunc(cast(share as Decimal(10,2)),2) as g
				from
				(
					select taxpayer_name, replace(share_percentage,',','.') as share
					from AFM_2_1_TEST.AFM_2_1_5_1
					where share_percentage like '%,%' and share_percentage not like '' and founder_iin_bin like ''
						AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
				) a
				union all
				select taxpayer_name, floor(cast(concat(share_percentage,'.00') as Decimal(10,2)),2) as g
				from AFM_2_1_TEST.AFM_2_1_5_1
				where share_percentage not like '%,%' and share_percentage not like '0' and share_percentage not like '' and founder_iin_bin like ''
					AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
				) b
			group by taxpayer_name
			having sum(g) >= 99.9 and sum(g) <= 100.1
		)
	)
)
select distinct
	a.taxpayer_iin_bin as taxpayer_iin_bin
	, founder_iin_bin
	, toString(share_percentage) as share_percentage
	, b.employee_iin_bin as  director_iin_bin
	, founder_iin_bin as benefeciary_iin_bin
	, if(right(left(founder_iin_bin,5),1) = '5','Регистрационный БС - нерезидент',
			if(right(left(founder_iin_bin,5),1) in ('1','2','3') and right(left(founder_iin_bin,7),1)='0','Регистрационный БС - нерезидент',
				'Регистрационный БС'
			)
		) as status
	,'БС-3' as algorithm_code
	, 0 as priority
	, 'МЮ_учредители' as source
	, toString(today()) as _actual_date
	, founder_name as dop_info
from (
select *
from table1
where share_percentage >= 25.0 and left(right(founder_iin_bin,8),1) <'4'
)a
left JOIN
	(
		SELECT *
		FROM AFM_2_1_TEST.AFM_2_1_6_1
		WHERE _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)

	)b
	on a.taxpayer_iin_bin = b.taxpayer_iin_bin;

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_9 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_9
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_9;
