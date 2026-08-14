-- ============================================================================
-- БС-4 — Учредители с признаком некорректности 3 (Предполагаемый БС, балл 3)
-- ЮЛ, у которых сумма долей учредителей > 0, но вне диапазона [99.9; 100.1].
-- Доля учредителя пересчитывается относительно фактической суммы долей.
-- Результат: AFM_6_TEST.AFM_6_1_10
--
-- ПРАВКА СИНТАКСИСА (логика не изменена), см. docs/sql-fixes.md:
--   в ТЗ было  «on a.taxpayer_iin_bin = table1.taxpayer_iin_bin»
--   выполняется «on a.taxpayer_iin_bin = b.taxpayer_iin_bin»
--   (CTE table1 подключён под псевдонимом b; обращение по имени CTE после
--    присвоения псевдонима ClickHouse не разрешает).
-- ============================================================================

DROP VIEW IF EXISTS AFM_6_TEST.v_AFM_6_1_10;

CREATE VIEW AFM_6_TEST.v_AFM_6_1_10
AS
with table1 as
(
	select
		taxpayer_iin_bin
		, founder_iin_bin
		,founder_name
		, sum(g) as share_per
	from
	(
		select taxpayer_iin_bin
		,founder_iin_bin
		,founder_name
		,trunc(cast(share as Decimal(10,2)),2) as g
		from
			(
			select
				taxpayer_iin_bin
				, founder_iin_bin
				, if(founder_ul_name like '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),founder_ul_name) as founder_name
				, replace(share_percentage,',','.') as share
			from AFM_2_1_TEST.AFM_2_1_5_1
			where share_percentage like '%,%'
				and share_percentage not like ''
				AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
			) a
			union all
		select
			taxpayer_iin_bin
			, founder_iin_bin
			, if(founder_ul_name like '', concat(founder_last_name,' ',founder_first_name,' ',founder_part_name),founder_ul_name) as founder_name
			, floor(cast(concat(share_percentage,'.00') as Decimal(10,2)),2) as g
		from AFM_2_1_TEST.AFM_2_1_5_1
		where share_percentage not like '%,%'
			and share_percentage not like '0'
			and share_percentage not like ''
			AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
		)
	group by taxpayer_iin_bin
		,founder_iin_bin
		,founder_name
),
table2 as
(
	select
		taxpayer_iin_bin
		, sum(g) as total_share
	from
	(
		select
			taxpayer_iin_bin
			, trunc(cast(share as Decimal(10,2)),2) as g
		from
			(
			select
				taxpayer_iin_bin
				, replace(share_percentage,',','.') as share
			from AFM_2_1_TEST.AFM_2_1_5_1
			where share_percentage like '%,%'
				and share_percentage not like ''
				AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
			) a
			union all
			select
				taxpayer_iin_bin
				, floor(cast(concat(share_percentage,'.00') as Decimal(10,2)),2) as g
			from AFM_2_1_TEST.AFM_2_1_5_1
			where share_percentage not like '%,%'
				and share_percentage not like '0'
				and share_percentage not like ''
				AND _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_5_1)
	)
	group by taxpayer_iin_bin
	having total_share <> 0.00 and (total_share < 99.9 or total_share > 100.1)
)
select distinct
	a.taxpayer_iin_bin as taxpayer_iin_bin
	, b.founder_iin_bin as founder_iin_bin
	, toString(cast(share_per as Decimal(10,4)) /cast(total_share as Decimal(10,4)) * 100.0000) as share_percentage
	, d.employee_iin_bin as  director_iin_bin
	, b.founder_iin_bin as benefeciary_iin_bin
	, if(right(left(b.founder_iin_bin,5),1) = '5','Предполагаемый БС - нерезидент',
			if(right(left(b.founder_iin_bin,5),1) in ('1','2','3') and right(left(b.founder_iin_bin,7),1)='0','Предполагаемый БС - нерезидент',
				'Предполагаемый БС'
			)
		) as status
	, 'БС-4' as algorithm_code
	, 3 as priority
	, 'МЮ_учредители' as source
	, toString(today()) as `_actual_date`
	, b.founder_name as dop_info
from table2 a
left join table1 b
	on a.taxpayer_iin_bin = b.taxpayer_iin_bin
left JOIN
	(
		SELECT *
		FROM AFM_2_1_TEST.AFM_2_1_6_1
		WHERE _actual_date = (SELECT DISTINCT max(_actual_date) FROM AFM_2_1_TEST.AFM_2_1_6_1)
	)d
	on d.taxpayer_iin_bin = b.taxpayer_iin_bin
where cast(share_per as Decimal(10,4)) /cast(total_share as Decimal(10,4)) * 100.0000 >= 25 and left(right(b.founder_iin_bin,8),1) not in ('4','5') and b.founder_iin_bin not like '';

DROP TABLE IF EXISTS AFM_6_TEST.AFM_6_1_10 SYNC;

CREATE TABLE AFM_6_TEST.AFM_6_1_10
ENGINE = MergeTree
ORDER BY (assumeNotNull(taxpayer_iin_bin))
AS SELECT * FROM AFM_6_TEST.v_AFM_6_1_10;
