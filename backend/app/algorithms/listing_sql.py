"""Запросы для страниц списков: ЮЛ, бенефициары, структуры владения.

Логика выявления БС здесь не меняется. Берётся тот же итоговый реестр, что и
в :mod:`app.algorithms.registry_sql` — те же семь полей из таблиц алгоритмов,
тот же расчёт ball1 / ball2 / ball3, то же правило имени бенефициара. Разница
только в разрезе: карточка компании считает одну компанию, а этим страницам
нужны сводки по всему реестру.

Как и в registry_sql, все колонки внутри выражений обязательно
квалифицируются псевдонимом таблицы. Запись ``toString(x) AS x`` без
префикса в ClickHouse 24+ разбирается как ссылка на создаваемый псевдоним,
и запрос падает с UNKNOWN_IDENTIFIER.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from app.algorithms import cleaning
from app.algorithms.registry_sql import (
    DOP_INFO_FIRST_PART_ALGORITHMS,
    build_keyed_union_sql,
    build_union_sql,
)
from app.core.config import settings

#: Разрешённые колонки сортировки списка ЮЛ: параметр из запроса
#: подставляется в SQL, поэтому принимается только из этого словаря.
COMPANY_SORT_COLUMNS = {
    "taxpayer_iin_bin": "d.taxpayer_iin_bin",
    "taxpayer_name": "d.taxpayer_name",
    "code_nd": "d.code_nd",
    "ownership_type": "d.ownership_type",
    "beneficiary_count": "d.beneficiary_count",
    "max_ball3": "d.max_ball3",
    "reg_start_date": "d.reg_start_date",
}

#: То же для списка бенефициаров
BENEFICIARY_SORT_COLUMNS = {
    "benefeciary_name": "r.benefeciary_name",
    "benefeciary_iin_bin": "r.benefeciary_key",
    "status": "r.status",
    "company_count": "r.company_count",
    "max_ball3": "r.max_ball3",
}


def _direction(order: str) -> str:
    return "ASC" if str(order).lower() == "asc" else "DESC"


def _scored_cte(result_tables: Iterable[str], *, with_details: bool) -> str:
    """Общая часть: реестр, свёрнутый до пар «компания — бенефициар» с ball3.

    :param with_details: тянуть ли статус, алгоритмы и dop_info. Для списка ЮЛ
        они не нужны, и без них запрос заметно легче.
    """
    union_sql = build_union_sql(result_tables)

    first_part_codes = ", ".join(
        f"'{code}'" for code in DOP_INFO_FIRST_PART_ALGORITHMS
    )
    iin_clean = cleaning.clean_iin("u.benefeciary_iin_bin")
    dop_name = cleaning.display_name("u.dop_info")
    key = cleaning.beneficiary_key("iin_clean", "dop_name")

    details = ",\n        status,\n        dop_info" if with_details else ""
    details_select = (
        "        u.status AS status,\n        u.dop_info AS dop_info,\n"
        if with_details
        else ""
    )

    # Чистка стоит ДО расчёта баллов: ключом сведения служит очищенный ИИН,
    # и если считать по грязному, проценты не сошлись бы с показанными
    # строками. Те же правила применяет карточка компании — см. registry_sql.
    return f"""cleaned AS (
    SELECT
        u.taxpayer_iin_bin AS taxpayer_iin_bin,
        {iin_clean} AS iin_clean,
        {dop_name} AS dop_name,
        u.algorithm_code AS algorithm_code,
        u.priority AS priority,
{details_select}        u.benefeciary_iin_bin AS raw_iin
    FROM (
{union_sql}
    ) AS u
),
base AS (
    SELECT DISTINCT
        taxpayer_iin_bin,
        iin_clean,
        -- Служебный ключ сведения; в поле ИИН он не показывается
        {key} AS benefeciary_key,
        dop_name,
        algorithm_code,
        priority{details}
    FROM cleaned
    -- Ни ИИН, ни имени — опознать лицо нельзя, это не бенефициар
    WHERE NOT (iin_clean = '' AND dop_name = '')
),
-- Один балл на сочетание «пара + алгоритм»: внутри алгоритма priority
-- постоянна, а строк на пару может быть много из-за JOIN с учредителями
algo AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_key AS benefeciary_key,
        b.algorithm_code AS algorithm_code,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_iin_bin, b.benefeciary_key, b.algorithm_code
),
ball1_t AS (
    SELECT a.taxpayer_iin_bin AS taxpayer_iin_bin, sum(a.priority) AS ball1
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin
),
ball2_t AS (
    SELECT
        a.taxpayer_iin_bin AS taxpayer_iin_bin,
        a.benefeciary_key AS benefeciary_key,
        sum(a.priority) AS ball2
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin, a.benefeciary_key
),
scored AS (
    SELECT
        b2.taxpayer_iin_bin AS taxpayer_iin_bin,
        b2.benefeciary_key AS benefeciary_key,
        if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2)) AS ball3
    FROM ball2_t AS b2
    LEFT JOIN ball1_t AS b1 ON b2.taxpayer_iin_bin = b1.taxpayer_iin_bin
)"""


# ---------------------------------------------------------------------------
# Список юридических лиц
# ---------------------------------------------------------------------------
def build_companies_list_sql(
    result_tables: Iterable[str],
    *,
    conditions: Optional[List[str]] = None,
    sort: str = "max_ball3",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Страница списка ЮЛ, отобранных по реестру (то есть имеющих БС).

    Общее количество строк приходит тем же запросом через ``count() OVER ()``:
    отдельный подсчёт означал бы второй проход по всему реестру.
    """
    sort_column = COMPANY_SORT_COLUMNS.get(sort, "max_ball3")
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    return f"""
WITH {_scored_cte(result_tables, with_details=False)},
summary AS (
    SELECT
        s.taxpayer_iin_bin AS taxpayer_iin_bin,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_iin_bin
),
-- Наименование для компаний, которых нет в справочнике ЮЛ: иностранных
-- и прочих. Тот же БИН обычно встречается в реестре как бенефициар, и там
-- рядом лежит строка сведений с названием — её и разбираем.
fallback_names AS (
    SELECT
        b.iin_clean AS taxpayer_iin_bin,
        argMin(b.dop_name, (b.priority, b.dop_name)) AS taxpayer_name
    FROM base AS b
    WHERE b.iin_clean != ''
      AND b.iin_clean IN (SELECT taxpayer_iin_bin FROM summary)
    GROUP BY b.iin_clean
),
dict AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
        ifNull(toString(any(c.category)), '') AS category,
        ifNull(toString(any(c.code_nd)), '') AS code_nd,
        ifNull(toString(any(c.address)), '') AS address,
        ifNull(toString(any(c.reg_start_date)), '') AS reg_start_date
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM summary)
    GROUP BY c.taxpayer_iin_bin
),
own AS (
    SELECT
        o.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(argMax(o.ownership_type, o.`_actual_date`)), '') AS ownership_type
    FROM {settings.DICT_OWNERSHIP} AS o
    WHERE o.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM summary)
    GROUP BY o.taxpayer_iin_bin
),
-- Государственные компании: по ТЗ бенефициары для них не определяются,
-- поэтому показатели обнуляются здесь же, до сортировки и фильтров.
-- Иначе такая компания встала бы в начало списка по риску, показывая ноль.
-- Список строится ОТ реестра, а справочник его дополняет. Прежде было
-- наоборот, и компания, которой в справочнике ЮЛ нет — иностранная или
-- любая другая, — в список не попадала вовсе, хотя бенефициары у неё
-- выявлены. Ссылка на такую компанию тоже никуда не вела.
rows AS (
    SELECT
        m.taxpayer_iin_bin AS taxpayer_iin_bin,
        if(COALESCE(d.taxpayer_name, '') != '',
            d.taxpayer_name,
            COALESCE(f.taxpayer_name, '')) AS taxpayer_name,
        COALESCE(d.category, '') AS category,
        COALESCE(d.code_nd, '') AS code_nd,
        COALESCE(d.address, '') AS address,
        COALESCE(d.reg_start_date, '') AS reg_start_date,
        -- Нет в справочнике — значит сведений о компании у нас нет
        COALESCE(d.taxpayer_iin_bin, '') = '' AS is_unknown,
        COALESCE(w.ownership_type, '') AS ownership_type,
        positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0
            AS is_state_owned,
        if(positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0,
            0, COALESCE(m.beneficiary_count, 0)) AS beneficiary_count,
        if(positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0,
            0, COALESCE(m.max_ball3, 0)) AS max_ball3
    FROM summary AS m
    LEFT JOIN dict AS d ON m.taxpayer_iin_bin = d.taxpayer_iin_bin
    LEFT JOIN fallback_names AS f ON m.taxpayer_iin_bin = f.taxpayer_iin_bin
    LEFT JOIN own AS w ON m.taxpayer_iin_bin = w.taxpayer_iin_bin
)
SELECT
    d.taxpayer_iin_bin AS taxpayer_iin_bin,
    d.taxpayer_name AS taxpayer_name,
    d.category AS category,
    d.code_nd AS code_nd,
    d.address AS address,
    d.reg_start_date AS reg_start_date,
    d.ownership_type AS ownership_type,
    d.is_state_owned AS is_state_owned,
    d.is_unknown AS is_unknown,
    d.beneficiary_count AS beneficiary_count,
    d.max_ball3 AS max_ball3,
    count() OVER () AS total_count
FROM rows AS d
{where_clause}
ORDER BY {sort_column} {_direction(order)}, d.taxpayer_iin_bin ASC
LIMIT {int(limit)} OFFSET {int(offset)}
""".strip()


def build_companies_enrich_sql(result_tables: Iterable[str]) -> str:
    """Показатели реестра для заранее отобранного перечня БИН.

    Используется режимом «все ЮЛ из справочника»: страница берётся из
    справочника, и только для неё считаются количество БС и вероятность.
    Без ограничения по списку такой разрез пришлось бы считать по всему
    справочнику юридических лиц.
    """
    keyed_sql = build_keyed_union_sql(
        build_union_sql(result_tables),
        ["algorithm_code", "priority"],
        where="WHERE u.taxpayer_iin_bin IN {bins:Array(String)}",
    )
    return f"""
WITH base AS (
{keyed_sql}
),
algo AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_key AS benefeciary_key,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_iin_bin, b.benefeciary_key, b.algorithm_code
),
ball1_t AS (
    SELECT a.taxpayer_iin_bin AS taxpayer_iin_bin, sum(a.priority) AS ball1
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin
),
ball2_t AS (
    SELECT
        a.taxpayer_iin_bin AS taxpayer_iin_bin,
        a.benefeciary_key AS benefeciary_key,
        sum(a.priority) AS ball2
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin, a.benefeciary_key
)
SELECT
    b2.taxpayer_iin_bin AS taxpayer_iin_bin,
    count(DISTINCT b2.benefeciary_key) AS beneficiary_count,
    max(if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2))) AS max_ball3
FROM ball2_t AS b2
LEFT JOIN ball1_t AS b1 ON b2.taxpayer_iin_bin = b1.taxpayer_iin_bin
GROUP BY b2.taxpayer_iin_bin
""".strip()


# ---------------------------------------------------------------------------
# Список бенефициаров
# ---------------------------------------------------------------------------
def build_beneficiaries_list_sql(
    result_tables: Iterable[str],
    *,
    conditions: Optional[List[str]] = None,
    sort: str = "max_ball3",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Реестр в разрезе бенефициаров: по одной строке на ИИН.

    Имя определяется по тому же правилу ТЗ, что и в карточке компании:
    справочник физических лиц, а при его отсутствии — dop_info, причём
    для БС-7 и БС-17 берётся часть строки до первой запятой.

    Строка сворачивается по алгоритму с наименьшим баллом приоритетности:
    регистрационные сведения (priority 0) достовернее предполагаемых.
    """
    sort_column = BENEFICIARY_SORT_COLUMNS.get(sort, "max_ball3")
    nonresident_status_expr = cleaning.nonresident_status("pp.status")
    display_iin_expr = cleaning.display_iin("r.iin_clean", "r.is_nonresident")
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    return f"""
WITH {_scored_cte(result_tables, with_details=True)},
-- Наименование юрлица-бенефициара — из справочника по БИН, как и в
-- карточке компании: dop_info у разных алгоритмов записан по-разному,
-- и один БИН получал бы разные названия.
beneficiary_names AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(any(c.taxpayer_name), '') AS company_name
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT iin_clean FROM base WHERE iin_clean != '')
    GROUP BY c.taxpayer_iin_bin
),
persons AS (
    SELECT
        p.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(any(p.taxpayer_name)), '') AS person_name
    FROM {settings.DICT_PERSONS} AS p
    WHERE p.taxpayer_iin_bin IN (SELECT iin_clean FROM base WHERE iin_clean != '')
    GROUP BY p.taxpayer_iin_bin
),
per_pair AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_key AS benefeciary_key,
        any(b.iin_clean) AS iin_clean,
        argMin(b.status, b.priority) AS status,
        -- Пара (балл, имя) в ключе сравнения: при равных баллах победитель
        -- иначе выбирался бы произвольно, и один ИИН назывался бы по-разному
        argMin(b.dop_name, (b.priority, b.dop_name)) AS dop_name,
        argMin(b.dop_info, (b.priority, b.dop_name)) AS dop_info,
        groupUniqArray(b.algorithm_code) AS algorithm_codes,
        min(b.priority) AS min_priority
    FROM base AS b
    GROUP BY b.taxpayer_iin_bin, b.benefeciary_key
),
pair_named AS (
    SELECT
        pp.taxpayer_iin_bin AS taxpayer_iin_bin,
        pp.benefeciary_key AS benefeciary_key,
        pp.iin_clean AS iin_clean,
        -- Нет настоящего ИИН — лицо нерезидент. Тип БС сохраняется,
        -- добавляется только пометка. Те же правила в карточке компании.
        if(pp.iin_clean = '',
            {nonresident_status_expr},
            if(right(left(pp.iin_clean, 5), 1) = '5'
                OR (right(left(pp.iin_clean, 5), 1) IN ('1', '2', '3')
                    AND right(left(pp.iin_clean, 7), 1) = '0'),
                {nonresident_status_expr},
                pp.status)) AS status,
        pp.algorithm_codes AS algorithm_codes,
        pp.min_priority AS min_priority,
        pp.dop_info AS dop_info,
        COALESCE(sc.ball3, 0) AS ball3,
        -- Справочник ФЛ ищется по настоящему ИИН; когда его нет, имя уже
        -- разобрано из dop_info на шаге чистки
        if(COALESCE(pr.person_name, '') != '',
            pr.person_name,
            if(COALESCE(bn.company_name, '') != '',
                bn.company_name,
                pp.dop_name)) AS benefeciary_name
    FROM per_pair AS pp
    LEFT JOIN persons AS pr ON pp.iin_clean = pr.taxpayer_iin_bin
    LEFT JOIN beneficiary_names AS bn ON pp.iin_clean = bn.taxpayer_iin_bin
    LEFT JOIN scored AS sc
        ON pp.taxpayer_iin_bin = sc.taxpayer_iin_bin
        AND pp.benefeciary_key = sc.benefeciary_key
),
rolled AS (
    SELECT
        pn.benefeciary_key AS benefeciary_key,
        any(pn.iin_clean) AS iin_clean,
        argMin(pn.benefeciary_name, (pn.min_priority, pn.benefeciary_name))
            AS benefeciary_name,
        argMin(pn.status, (pn.min_priority, pn.benefeciary_name)) AS status,
        arraySort(arrayDistinct(arrayFlatten(groupArray(pn.algorithm_codes)))) AS algorithm_codes,
        count(DISTINCT pn.taxpayer_iin_bin) AS company_count,
        max(pn.ball3) AS max_ball3,
        max(pn.status LIKE '%нерезидент%') AS is_nonresident,
        -- Исходная строка сведений: по ней модель дочищает имя при выводе
        argMin(pn.dop_info, (pn.min_priority, pn.benefeciary_name)) AS dop_info,
        min(pn.min_priority) AS min_priority
    FROM pair_named AS pn
    GROUP BY pn.benefeciary_key
)
SELECT
    r.benefeciary_key AS benefeciary_key,
    -- В поле ИИН только номер, слово «нерезидент» либо пусто
    {display_iin_expr} AS benefeciary_iin_bin,
    r.benefeciary_name AS benefeciary_name,
    r.status AS status,
    r.algorithm_codes AS algorithm_codes,
    arrayStringConcat(r.algorithm_codes, ', ') AS algorithms,
    r.company_count AS company_count,
    r.max_ball3 AS max_ball3,
    r.is_nonresident AS is_nonresident,
    r.dop_info AS dop_info,
    r.min_priority AS priority,
    count() OVER () AS total_count
FROM rolled AS r
{where_clause}
ORDER BY {sort_column} {_direction(order)}, r.benefeciary_key ASC
LIMIT {int(limit)} OFFSET {int(offset)}
""".strip()


# ---------------------------------------------------------------------------
# Дашборд
# ---------------------------------------------------------------------------
def build_dashboard_summary_sql(result_tables: Iterable[str]) -> str:
    """Показатели дашборда, считающиеся по всему реестру за один проход."""
    return f"""
WITH {_scored_cte(result_tables, with_details=False)},
per_company AS (
    SELECT
        s.taxpayer_iin_bin AS taxpayer_iin_bin,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_iin_bin
)
SELECT
    count() AS companies_with_bs,
    countIf(c.max_ball3 > 70) AS high_risk_count,
    countIf(c.max_ball3 >= 40 AND c.max_ball3 <= 70) AS medium_risk_count,
    countIf(c.max_ball3 < 40) AS low_risk_count
FROM per_company AS c
""".strip()


def build_top_companies_sql(result_tables: Iterable[str], *, by: str, limit: int = 10) -> str:
    """Топ компаний — по количеству бенефициаров либо по уровню риска."""
    order_column = "max_ball3" if by == "risk" else "beneficiary_count"
    return f"""
WITH {_scored_cte(result_tables, with_details=False)},
per_company AS (
    SELECT
        s.taxpayer_iin_bin AS taxpayer_iin_bin,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_iin_bin
    ORDER BY {order_column} DESC, s.taxpayer_iin_bin ASC
    LIMIT {int(limit)}
),
dict AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
        ifNull(toString(any(c.code_nd)), '') AS code_nd
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM per_company)
    GROUP BY c.taxpayer_iin_bin
)
SELECT
    p.taxpayer_iin_bin AS taxpayer_iin_bin,
    COALESCE(d.taxpayer_name, '') AS taxpayer_name,
    COALESCE(d.code_nd, '') AS code_nd,
    p.beneficiary_count AS beneficiary_count,
    p.max_ball3 AS max_ball3
FROM per_company AS p
LEFT JOIN dict AS d ON p.taxpayer_iin_bin = d.taxpayer_iin_bin
ORDER BY {order_column} DESC, p.taxpayer_iin_bin ASC
""".strip()


def build_total_companies_sql() -> str:
    """Всего юридических лиц в справочнике."""
    return f"""
SELECT uniqExact(c.taxpayer_iin_bin) AS total_companies
FROM {settings.DICT_COMPANIES} AS c
""".strip()


# ---------------------------------------------------------------------------
# Структуры владения
# ---------------------------------------------------------------------------
def build_founders_of_sql(actual_only: bool = True) -> str:
    """Учредители перечня компаний.

    Тип учредителя определяется по заполненности ``founder_ul_name``: это
    признак самих данных МЮ, а не расчёт — юридическое лицо записывается
    наименованием, физическое — фамилией, именем и отчеством.
    """
    actual_filter = (
        f"AND f.`_actual_date` = (SELECT max(`_actual_date`) FROM {settings.TBL_FOUNDERS})"
        if actual_only
        else ""
    )
    return f"""
SELECT DISTINCT
    toString(f.taxpayer_iin_bin) AS taxpayer_iin_bin,
    ifNull(toString(f.founder_iin_bin), '') AS founder_iin_bin,
    ifNull(if(f.founder_ul_name = '',
        concat(f.founder_last_name, ' ', f.founder_first_name, ' ', f.founder_part_name),
        f.founder_ul_name), '') AS founder_name,
    if(ifNull(toString(f.founder_ul_name), '') = '', 'person', 'company') AS founder_kind,
    ifNull(toString(f.share_percentage), '') AS share_percentage
FROM {settings.TBL_FOUNDERS} AS f
WHERE f.taxpayer_iin_bin IN {{bins:Array(String)}}
  {actual_filter}
""".strip()


def build_companies_of_founder_sql() -> str:
    """Компании, где указанное лицо числится учредителем."""
    return f"""
SELECT DISTINCT
    toString(f.taxpayer_iin_bin) AS taxpayer_iin_bin,
    ifNull(toString(f.share_percentage), '') AS share_percentage
FROM {settings.TBL_FOUNDERS} AS f
WHERE f.founder_iin_bin = {{iin:String}}
  AND f.`_actual_date` = (SELECT max(`_actual_date`) FROM {settings.TBL_FOUNDERS})
LIMIT {{lim:UInt32}}
""".strip()


def build_companies_of_director_sql() -> str:
    """Компании, где указанное лицо числится руководителем."""
    return f"""
SELECT DISTINCT toString(d.taxpayer_iin_bin) AS taxpayer_iin_bin
FROM {settings.TBL_DIRECTORS} AS d
WHERE d.employee_iin_bin = {{iin:String}}
  AND d.`_actual_date` = (SELECT max(`_actual_date`) FROM {settings.TBL_DIRECTORS})
LIMIT {{lim:UInt32}}
""".strip()


def build_company_names_sql() -> str:
    """Наименования и тип собственности для перечня БИН."""
    return f"""
SELECT
    c.taxpayer_iin_bin AS taxpayer_iin_bin,
    ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
    ifNull(toString(any(c.code_nd)), '') AS code_nd
FROM {settings.DICT_COMPANIES} AS c
WHERE c.taxpayer_iin_bin IN {{bins:Array(String)}}
GROUP BY c.taxpayer_iin_bin
""".strip()


def build_person_name_sql() -> str:
    """ФИО физического лица из справочника."""
    return f"""
SELECT ifNull(toString(any(p.taxpayer_name)), '') AS taxpayer_name
FROM {settings.DICT_PERSONS} AS p
WHERE p.taxpayer_iin_bin = {{iin:String}}
GROUP BY p.taxpayer_iin_bin
""".strip()
