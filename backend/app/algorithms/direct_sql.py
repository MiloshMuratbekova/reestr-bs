"""Чтение реестра прямо из готовой сводной таблицы.

Зачем отдельный модуль
----------------------
Сводную таблицу AFM_6_1_99_merged организация собирает своим скриптом и уже
там приводит данные в порядок: убирает невидимые символы, отсеивает заглушки
вместо ИИН, вычищает служебный текст из ФИО, схлопывает повторы, подставляет
наименования компаний по шести источникам и разворачивает юрлицо-бенефициара
до конечного физлица.

Поэтому здесь ничего не пересчитывается. Поля берутся как есть: ИИН, ФИО,
наименование компании, статус, доля, документ, сведения. Никаких справочников,
никакого разбора строк, никакой раскрутки цепочек — всё это уже сделано
в источнике, и повторять его значило бы спорить с ним.

Что всё-таки считается
----------------------
Только баллы из ТЗ, и только по самой сводной таблице:
    ball1 — сумма priority по всем строкам компании;
    ball2 — сумма priority по паре «компания — бенефициар»;
    ball3 — ball2 / ball1 * 100.
Балл берётся один раз на сочетание «пара + алгоритм»: строк на пару может
быть несколько, а priority внутри алгоритма постоянна.

Ключи сведения
--------------
Сводная таблица группирует строки по (компания, бенефициар, ФИО, алгоритм).
Там, где идентификатора нет, лица различаются именем — здесь ровно то же:
у компании без БИН к ключу добавляется наименование, у бенефициара без ИИН —
ФИО. Иначе все иностранные организации слились бы в одну строку, а разные
иностранцы одной компании — в одного человека.

Когда этот модуль не используется
---------------------------------
Если сводной таблицы нет или у неё не тот состав колонок, реестр собирается
по таблицам отдельных алгоритмов — см. :mod:`app.algorithms.registry_sql`.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from app.core.config import settings

#: Как источник помечает организацию без казахстанского БИН
FOREIGN_COMPANY = "Иностранная компания"

#: Колонки, которые обязаны быть в сводной таблице для прямого чтения.
#: Проверяются перед использованием: без любой из них запрос не собрать.
REQUIRED_COLUMNS = frozenset({
    "taxpayer_iin_bin",
    "taxpayer_name",
    "benefeciary_iin_bin",
    "benefeciary_name",
    "status",
    "algorithm_code",
    "priority",
    "_actual_date",
    "dop_info",
})

#: Необязательные колонки: если их нет, подставляется пустая строка
OPTIONAL_COLUMNS = ("category", "doc", "share_percentage")

#: Разрешённые колонки сортировки списка ЮЛ
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
    "benefeciary_iin_bin": "r.benefeciary_iin_bin",
    "status": "r.status",
    "company_count": "r.company_count",
    "max_ball3": "r.max_ball3",
}


def _direction(order: str) -> str:
    return "ASC" if str(order).lower() == "asc" else "DESC"


def _column(name: str, available: Iterable[str]) -> str:
    """Колонка таблицы либо пустая строка, если её там нет."""
    return f"ifNull(toString(m.{name}), '')" if name in set(available) else "''"


def build_rows_cte(
    merged_table: str,
    columns: Iterable[str],
    *,
    where: str = "",
) -> str:
    """Строки сводной таблицы как есть, плюс два служебных ключа.

    Ключи нужны только для сведения и ссылок; в показываемые поля они
    не попадают. Всё остальное берётся из таблицы без изменений.
    """
    available = set(columns)
    category = _column("category", available)
    doc = _column("doc", available)
    share = _column("share_percentage", available)
    where_clause = f"WHERE {where}" if where else ""

    return f"""rows AS (
    SELECT
        ifNull(toString(m.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
        ifNull(toString(m.taxpayer_name), '') AS taxpayer_name,
        ifNull(toString(m.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
        ifNull(toString(m.benefeciary_name), '') AS benefeciary_name,
        ifNull(toString(m.status), '') AS status,
        ifNull(toString(m.algorithm_code), '') AS algorithm_code,
        ifNull(toInt32OrZero(toString(m.priority)), 0) AS priority,
        ifNull(toString(m.`_actual_date`), '') AS _actual_date,
        ifNull(toString(m.dop_info), '') AS dop_info,
        {category} AS category,
        {doc} AS document_info,
        {share} AS share_percentage,
        -- Ключ компании: сам БИН, а у иностранной — с наименованием, иначе
        -- все они склеятся в одну строку под общим текстом
        if(match(ifNull(toString(m.taxpayer_iin_bin), ''), '^[0-9]{{12}}$'),
            ifNull(toString(m.taxpayer_iin_bin), ''),
            concat(ifNull(toString(m.taxpayer_iin_bin), '{FOREIGN_COMPANY}'), ': ',
                   ifNull(toString(m.taxpayer_name), ''))) AS taxpayer_key,
        -- Ключ бенефициара: идентификатор, а при его отсутствии — ФИО.
        -- Так же различает лиц и сама сводная таблица.
        if(ifNull(toString(m.benefeciary_iin_bin), '') != '',
            ifNull(toString(m.benefeciary_iin_bin), ''),
            concat('нерезидент: ', ifNull(toString(m.benefeciary_name), ''))) AS benefeciary_key,
        -- Признак нерезидента читается из статуса, который проставил источник
        positionCaseInsensitive(ifNull(toString(m.status), ''), 'нерезидент') > 0
            AS is_nonresident
    FROM {merged_table} AS m
    {where_clause}
)"""


#: Баллы из ТЗ. Считаются по строкам сводной таблицы и больше ни по чему.
BALLS_CTE = """algo AS (
    SELECT
        r.taxpayer_key AS taxpayer_key,
        r.benefeciary_key AS benefeciary_key,
        r.algorithm_code AS algorithm_code,
        any(r.priority) AS priority
    FROM rows AS r
    GROUP BY r.taxpayer_key, r.benefeciary_key, r.algorithm_code
),
ball1_t AS (
    SELECT a.taxpayer_key AS taxpayer_key, sum(a.priority) AS ball1
    FROM algo AS a
    GROUP BY a.taxpayer_key
),
ball2_t AS (
    SELECT
        a.taxpayer_key AS taxpayer_key,
        a.benefeciary_key AS benefeciary_key,
        sum(a.priority) AS ball2
    FROM algo AS a
    GROUP BY a.taxpayer_key, a.benefeciary_key
),
scored AS (
    SELECT
        b2.taxpayer_key AS taxpayer_key,
        b2.benefeciary_key AS benefeciary_key,
        b1.ball1 AS ball1,
        b2.ball2 AS ball2,
        if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2)) AS ball3
    FROM ball2_t AS b2
    LEFT JOIN ball1_t AS b1 ON b2.taxpayer_key = b1.taxpayer_key
)"""


#: Тип собственности — единственное, чего в сводной таблице нет.
#: Он нужен правилу ТЗ о государственных компаниях и потому берётся
#: из справочника, а не из данных о бенефициарах.
def _ownership_cte(source: str) -> str:
    return f"""ownership AS (
    SELECT
        o.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(argMax(o.ownership_type, o.`_actual_date`)), '') AS ownership_type
    FROM {settings.DICT_OWNERSHIP} AS o
    WHERE o.taxpayer_iin_bin IN (SELECT {source} FROM rows)
    GROUP BY o.taxpayer_iin_bin
)"""


# ---------------------------------------------------------------------------
# Реестр: карточка компании, профиль бенефициара, выгрузка целиком
# ---------------------------------------------------------------------------
def build_registry_sql(
    merged_table: str,
    columns: Iterable[str],
    *,
    company_filter: Optional[str] = None,
    extra_conditions: Optional[List[str]] = None,
    row_limit: Optional[int] = None,
) -> str:
    """Реестр прямо из сводной таблицы.

    :param company_filter: условие по ключам (``taxpayer_key``,
        ``benefeciary_key``) либо по сырым полям таблицы.
    """
    having = ""
    if extra_conditions:
        having = "AND (" + " AND ".join(extra_conditions) + ")"
    where = company_filter or ""
    limit_clause = f"LIMIT {int(row_limit)}" if row_limit else ""

    return f"""
WITH {build_rows_cte(merged_table, columns)},
paired AS (
    SELECT
        r.taxpayer_key AS taxpayer_key,
        any(r.taxpayer_iin_bin) AS taxpayer_iin_bin,
        any(r.taxpayer_name) AS taxpayer_name,
        r.benefeciary_key AS benefeciary_key,
        any(r.benefeciary_iin_bin) AS benefeciary_iin_bin,
        any(r.benefeciary_name) AS benefeciary_name,
        -- При нескольких алгоритмах побеждает строка с наименьшим баллом:
        -- регистрационный признак (0) сильнее предполагаемого
        -- Регистрационный признак сильнее предполагаемого: если лицо
        -- нашлось и тем, и другим, показывается регистрационный. Ключ
        -- сравнения ставит такие строки первыми независимо от балла.
        argMin(r.status, (if(r.status LIKE 'Регистрационный%', 0, 1), r.priority))
            AS status,
        argMin(r.dop_info, r.priority) AS dop_info,
        argMin(r.category, r.priority) AS category,
        argMin(r.document_info, r.priority) AS document_info,
        argMin(r.share_percentage, r.priority) AS share_percentage,
        max(r.is_nonresident) AS is_nonresident,
        arraySort(groupUniqArray(r.algorithm_code)) AS algorithm_codes,
        min(r.priority) AS min_priority,
        max(r.`_actual_date`) AS _actual_date
    FROM rows AS r
    GROUP BY r.taxpayer_key, r.benefeciary_key
),
{BALLS_CTE},
{_ownership_cte("taxpayer_iin_bin")}
SELECT
    p.taxpayer_key AS taxpayer_key,
    p.taxpayer_iin_bin AS taxpayer_iin_bin,
    p.taxpayer_name AS taxpayer_name,
    p.benefeciary_key AS benefeciary_key,
    p.benefeciary_iin_bin AS benefeciary_iin_bin,
    p.benefeciary_name AS benefeciary_name,
    p.is_nonresident AS is_nonresident,
    p.status AS status,
    p.algorithm_codes AS algorithm_codes,
    arrayStringConcat(p.algorithm_codes, ', ') AS algorithms,
    p.min_priority AS priority,
    p.category AS category,
    COALESCE(own.ownership_type, '') AS ownership_type,
    p.document_info AS document_info,
    p.share_percentage AS share_percentage,
    p._actual_date AS _actual_date,
    p.dop_info AS dop_info,
    s.ball1 AS ball1,
    s.ball2 AS ball2,
    s.ball3 AS ball3
FROM paired AS p
LEFT JOIN scored AS s
    ON p.taxpayer_key = s.taxpayer_key AND p.benefeciary_key = s.benefeciary_key
LEFT JOIN ownership AS own ON p.taxpayer_iin_bin = own.taxpayer_iin_bin
WHERE {where or "1"}
{having}
{limit_clause}
""".strip()


# ---------------------------------------------------------------------------
# Сводка по компаниям
# ---------------------------------------------------------------------------
def build_company_summary_sql(
    merged_table: str,
    columns: Iterable[str],
    company_filter: Optional[str] = None,
) -> str:
    """Число бенефициаров и максимальный ball3 по каждой компании."""
    where = f"WHERE {company_filter}" if company_filter else ""
    return f"""
WITH {build_rows_cte(merged_table, columns)},
{BALLS_CTE}
SELECT
    s.taxpayer_key AS taxpayer_key,
    any(r.taxpayer_iin_bin) AS taxpayer_iin_bin,
    count(DISTINCT s.benefeciary_key) AS beneficiary_count,
    max(s.ball3) AS max_ball3
FROM scored AS s
INNER JOIN rows AS r ON s.taxpayer_key = r.taxpayer_key
{where}
GROUP BY s.taxpayer_key
""".strip()


# ---------------------------------------------------------------------------
# Списки
# ---------------------------------------------------------------------------
def build_companies_list_sql(
    merged_table: str,
    columns: Iterable[str],
    *,
    conditions: Optional[List[str]] = None,
    sort: str = "max_ball3",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Страница списка юридических лиц."""
    sort_column = COMPANY_SORT_COLUMNS.get(sort, "d.max_ball3")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return f"""
WITH {build_rows_cte(merged_table, columns)},
{BALLS_CTE},
summary AS (
    SELECT
        s.taxpayer_key AS taxpayer_key,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_key
),
company AS (
    SELECT
        r.taxpayer_key AS taxpayer_key,
        any(r.taxpayer_iin_bin) AS taxpayer_iin_bin,
        any(r.taxpayer_name) AS taxpayer_name,
        any(r.category) AS category
    FROM rows AS r
    GROUP BY r.taxpayer_key
),
{_ownership_cte("taxpayer_iin_bin")},
dict AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(any(c.code_nd)), '') AS code_nd,
        ifNull(toString(any(c.address)), '') AS address,
        ifNull(toString(any(c.reg_start_date)), '') AS reg_start_date
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM company)
    GROUP BY c.taxpayer_iin_bin
),
-- Государственные компании: по ТЗ бенефициары для них не определяются,
-- поэтому показатели обнуляются до сортировки и фильтров
listed AS (
    SELECT
        c.taxpayer_key AS taxpayer_key,
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        c.taxpayer_name AS taxpayer_name,
        c.category AS category,
        COALESCE(k.code_nd, '') AS code_nd,
        COALESCE(k.address, '') AS address,
        COALESCE(k.reg_start_date, '') AS reg_start_date,
        COALESCE(w.ownership_type, '') AS ownership_type,
        positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0
            AS is_state_owned,
        COALESCE(k.taxpayer_iin_bin, '') = '' AS is_unknown,
        if(positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0,
            0, COALESCE(m.beneficiary_count, 0)) AS beneficiary_count,
        if(positionCaseInsensitive(COALESCE(w.ownership_type, ''), 'Государственная') > 0,
            0, COALESCE(m.max_ball3, 0)) AS max_ball3
    FROM company AS c
    LEFT JOIN summary AS m ON c.taxpayer_key = m.taxpayer_key
    LEFT JOIN dict AS k ON c.taxpayer_iin_bin = k.taxpayer_iin_bin
    LEFT JOIN ownership AS w ON c.taxpayer_iin_bin = w.taxpayer_iin_bin
)
SELECT
    d.taxpayer_key AS taxpayer_key,
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
FROM listed AS d
{where_clause}
ORDER BY {sort_column} {_direction(order)}, d.taxpayer_key ASC
LIMIT {int(limit)} OFFSET {int(offset)}
""".strip()


def build_beneficiaries_list_sql(
    merged_table: str,
    columns: Iterable[str],
    *,
    conditions: Optional[List[str]] = None,
    sort: str = "max_ball3",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Страница списка бенефициаров, свёрнутого по одному лицу."""
    sort_column = BENEFICIARY_SORT_COLUMNS.get(sort, "r.max_ball3")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return f"""
WITH {build_rows_cte(merged_table, columns)},
{BALLS_CTE},
per_pair AS (
    SELECT
        r.taxpayer_key AS taxpayer_key,
        r.benefeciary_key AS benefeciary_key,
        any(r.benefeciary_iin_bin) AS benefeciary_iin_bin,
        any(r.benefeciary_name) AS benefeciary_name,
        argMin(r.status, (if(r.status LIKE 'Регистрационный%', 0, 1), r.priority))
            AS status,
        argMin(r.dop_info, r.priority) AS dop_info,
        max(r.is_nonresident) AS is_nonresident,
        groupUniqArray(r.algorithm_code) AS algorithm_codes,
        min(r.priority) AS min_priority
    FROM rows AS r
    GROUP BY r.taxpayer_key, r.benefeciary_key
),
rolled AS (
    SELECT
        p.benefeciary_key AS benefeciary_key,
        any(p.benefeciary_iin_bin) AS benefeciary_iin_bin,
        argMin(p.benefeciary_name, (p.min_priority, p.benefeciary_name))
            AS benefeciary_name,
        argMin(p.status,
            (if(p.status LIKE 'Регистрационный%', 0, 1), p.min_priority)) AS status,
        argMin(p.dop_info, (p.min_priority, p.benefeciary_name)) AS dop_info,
        max(p.is_nonresident) AS is_nonresident,
        arraySort(arrayDistinct(arrayFlatten(groupArray(p.algorithm_codes))))
            AS algorithm_codes,
        count(DISTINCT p.taxpayer_key) AS company_count,
        max(COALESCE(s.ball3, 0)) AS max_ball3,
        min(p.min_priority) AS min_priority
    FROM per_pair AS p
    LEFT JOIN scored AS s
        ON p.taxpayer_key = s.taxpayer_key AND p.benefeciary_key = s.benefeciary_key
    GROUP BY p.benefeciary_key
)
SELECT
    r.benefeciary_key AS benefeciary_key,
    r.benefeciary_iin_bin AS benefeciary_iin_bin,
    r.benefeciary_name AS benefeciary_name,
    r.status AS status,
    r.algorithm_codes AS algorithm_codes,
    arrayStringConcat(r.algorithm_codes, ', ') AS algorithms,
    r.company_count AS company_count,
    r.max_ball3 AS max_ball3,
    r.is_nonresident AS is_nonresident,
    r.min_priority AS priority,
    count() OVER () AS total_count
FROM rolled AS r
{where_clause}
ORDER BY {sort_column} {_direction(order)}, r.benefeciary_key ASC
LIMIT {int(limit)} OFFSET {int(offset)}
""".strip()


# ---------------------------------------------------------------------------
# Показатели
# ---------------------------------------------------------------------------
def build_stats_sql(merged_table: str, columns: Iterable[str]) -> str:
    """Общая статистика реестра."""
    return f"""
WITH {build_rows_cte(merged_table, columns)}
SELECT
    count() AS total_rows,
    uniqExact(r.taxpayer_key) AS company_count,
    uniqExact(r.benefeciary_key) AS beneficiary_count,
    uniqExactIf(r.benefeciary_key, r.status LIKE 'Регистрационный%') AS registration_count,
    uniqExactIf(r.benefeciary_key, r.status LIKE 'Предполагаемый%') AS assumed_count,
    uniqExactIf(r.benefeciary_key, r.is_nonresident) AS nonresident_count
FROM rows AS r
""".strip()


def build_stats_by_algorithm_sql(merged_table: str, columns: Iterable[str]) -> str:
    """Разрез статистики по алгоритмам."""
    return f"""
WITH {build_rows_cte(merged_table, columns)}
SELECT
    r.algorithm_code AS algorithm_code,
    any(r.priority) AS priority,
    uniqExact(r.taxpayer_key) AS company_count,
    uniqExact(r.benefeciary_key) AS beneficiary_count,
    count() AS row_count
FROM rows AS r
GROUP BY r.algorithm_code
ORDER BY r.algorithm_code
""".strip()


def build_dashboard_summary_sql(merged_table: str, columns: Iterable[str]) -> str:
    """Сводка для дашборда."""
    return f"""
WITH {build_rows_cte(merged_table, columns)},
{BALLS_CTE},
per_company AS (
    SELECT
        s.taxpayer_key AS taxpayer_key,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_key
)
SELECT
    count() AS companies_with_bs,
    countIf(c.max_ball3 > 70) AS high_risk_count,
    countIf(c.max_ball3 >= 40 AND c.max_ball3 <= 70) AS medium_risk_count,
    countIf(c.max_ball3 < 40) AS low_risk_count
FROM per_company AS c
""".strip()


def build_top_companies_sql(
    merged_table: str, columns: Iterable[str], *, by: str, limit: int = 10
) -> str:
    """Топ компаний по риску либо по числу бенефициаров."""
    order_column = "max_ball3" if by == "risk" else "beneficiary_count"
    return f"""
WITH {build_rows_cte(merged_table, columns)},
{BALLS_CTE},
per_company AS (
    SELECT
        s.taxpayer_key AS taxpayer_key,
        count(DISTINCT s.benefeciary_key) AS beneficiary_count,
        max(s.ball3) AS max_ball3
    FROM scored AS s
    GROUP BY s.taxpayer_key
    ORDER BY {order_column} DESC, s.taxpayer_key ASC
    LIMIT {int(limit)}
),
company AS (
    SELECT
        r.taxpayer_key AS taxpayer_key,
        any(r.taxpayer_iin_bin) AS taxpayer_iin_bin,
        any(r.taxpayer_name) AS taxpayer_name
    FROM rows AS r
    WHERE r.taxpayer_key IN (SELECT taxpayer_key FROM per_company)
    GROUP BY r.taxpayer_key
),
dict AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(toString(any(c.code_nd)), '') AS code_nd
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM company)
    GROUP BY c.taxpayer_iin_bin
)
SELECT
    p.taxpayer_key AS taxpayer_key,
    n.taxpayer_iin_bin AS taxpayer_iin_bin,
    n.taxpayer_name AS taxpayer_name,
    COALESCE(k.code_nd, '') AS code_nd,
    p.beneficiary_count AS beneficiary_count,
    p.max_ball3 AS max_ball3
FROM per_company AS p
INNER JOIN company AS n ON p.taxpayer_key = n.taxpayer_key
LEFT JOIN dict AS k ON n.taxpayer_iin_bin = k.taxpayer_iin_bin
ORDER BY {order_column} DESC, p.taxpayer_key ASC
""".strip()


def build_company_head_sql(merged_table: str, columns: Iterable[str]) -> str:
    """Реквизиты компании, какие есть в сводной таблице.

    Нужны, когда компании нет в справочнике ЮЛ: наименование у неё всё равно
    есть — организация подставляет его в сводную по шести источникам.
    """
    return f"""
WITH {build_rows_cte(merged_table, columns)}
SELECT
    r.taxpayer_key AS taxpayer_key,
    any(r.taxpayer_iin_bin) AS taxpayer_iin_bin,
    any(r.taxpayer_name) AS taxpayer_name,
    any(r.category) AS category
FROM rows AS r
WHERE r.taxpayer_key = {{bin:String}} OR r.taxpayer_iin_bin = {{bin:String}}
GROUP BY r.taxpayer_key
LIMIT 1
""".strip()
