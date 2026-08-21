"""Построение итоговой таблицы реестра БС.

Итоговая таблица не хранится — она строится запросом при каждом обращении,
как этого требует ТЗ. Из каждого алгоритма берутся поля taxpayer_iin_bin,
benefeciary_iin_bin, status, algorithm_code, priority, _actual_date, dop_info;
дальше подтягиваются справочники и считаются баллы ball1 / ball2 / ball3.

Расчёт баллов (по ТЗ):
    ball1 — сумма priority по всем строкам с данным taxpayer_iin_bin;
    ball2 — сумма priority по строкам с данной парой taxpayer_iin_bin + benefeciary_iin_bin;
    ball3 — ball2 / ball1 * 100, округление до двух знаков.

Уточнение к суммированию. Таблицы алгоритмов содержат несколько строк на одну
пару компания-бенефициар (следствие JOIN с учредителями и директорами), а
priority внутри одного алгоритма — константа. Поэтому балл берётся один раз
на сочетание «пара + алгоритм»: иначе ball1 и ball2 зависели бы от числа
учредителей компании, а не от сработавших алгоритмов, и ball3 потерял бы смысл.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from app.core.config import settings

# Алгоритмы, у которых имя бенефициара при отсутствии в справочнике ФЛ
# берётся из первой части dop_info до первой запятой (по ТЗ).
DOP_INFO_FIRST_PART_ALGORITHMS = ("БС-7", "БС-17")


def build_union_sql(result_tables: Iterable[str]) -> str:
    """UNION ALL по таблицам результатов алгоритмов — семь полей из ТЗ.

    Типы приводятся к общему виду: _actual_date в таблицах алгоритмов
    встречается и строкой, и датой; priority — целым разной ширины.

    Колонки обязательно квалифицируются псевдонимом таблицы (``src.``).
    Без него запись вида ``toString(taxpayer_iin_bin) AS taxpayer_iin_bin``
    в ClickHouse 24+ (новый анализатор, включён по умолчанию) разбирается
    как ссылка на создаваемый псевдоним, а не на колонку, и запрос падает:
    «Unknown expression or function identifier `taxpayer_iin_bin`.
    Maybe you meant: ['taxpayer_iin_bin']». В прежних версиях это работало,
    поэтому ошибка проявляется только на новых серверах.
    """
    tables = [t for t in result_tables if t]
    if not tables:
        raise ValueError("Нет ни одной активной таблицы результатов алгоритмов")

    parts: List[str] = []
    for table in tables:
        parts.append(
            f"""    SELECT
        toString(src.taxpayer_iin_bin) AS taxpayer_iin_bin,
        toString(src.benefeciary_iin_bin) AS benefeciary_iin_bin,
        toString(src.status) AS status,
        toString(src.algorithm_code) AS algorithm_code,
        toInt32(src.priority) AS priority,
        toString(src.`_actual_date`) AS _actual_date,
        toString(src.dop_info) AS dop_info
    FROM {table} AS src"""
        )
    return "\n    UNION ALL\n".join(parts)


def build_registry_sql(
    result_tables: Iterable[str],
    *,
    company_filter: Optional[str] = None,
    category_source: str = "ownership",
    extra_conditions: Optional[List[str]] = None,
    row_limit: Optional[int] = None,
) -> str:
    """Собирает SQL итогового реестра.

    :param result_tables: таблицы результатов активных алгоритмов
    :param company_filter: условие отбора компаний, подставляется в WHERE
        базовой выборки (например ``taxpayer_iin_bin = {bin:String}``).
        Указывать обязательно для карточек и поиска — иначе оконный расчёт
        пойдёт по всему реестру.
    :param category_source: откуда брать поле ``category`` —
        ``ownership`` (AFM_2_1_8, как указано в ТЗ) либо ``company``
        (AFM_2_1_9); фактический источник определяется на старте
        по системному словарю ClickHouse.
    :param extra_conditions: дополнительные условия на итоговую выборку
    """
    union_sql = build_union_sql(result_tables)
    base_where = f"WHERE {company_filter}" if company_filter else ""

    first_part_list = ", ".join(f"'{code}'" for code in DOP_INFO_FIRST_PART_ALGORITHMS)

    # Поле category читается только из той таблицы, где оно действительно есть,
    # иначе запрос упадёт на этапе разбора.
    if category_source == "ownership":
        category_expr = "own.category"
        ownership_category_select = ", any(o.category) AS category"
    else:
        category_expr = "comp.category"
        ownership_category_select = ""

    # Дополнительные условия дописываются к уже имеющемуся WHERE через AND.
    # Отдельным словом WHERE их писать нельзя — в запросе он уже есть
    # (фильтр из ТЗ по пустому бенефициару), и второй сломал бы разбор.
    having = ""
    if extra_conditions:
        having = "AND (" + " AND ".join(extra_conditions) + ")"

    # Ограничение числа строк ставится в самом запросе: даже если клиент
    # попросит больше, до него дойдёт только разрешённое количество
    limit_clause = f"LIMIT {int(row_limit)}" if row_limit else ""

    return f"""
WITH base AS (
    SELECT DISTINCT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        status,
        algorithm_code,
        priority,
        _actual_date,
        dop_info
    FROM (
{union_sql}
    )
    {base_where}
),
-- Один балл на сочетание «пара + алгоритм»
algo AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_iin_bin AS benefeciary_iin_bin,
        b.algorithm_code AS algorithm_code,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_iin_bin, b.benefeciary_iin_bin, b.algorithm_code
),
ball1_t AS (
    SELECT taxpayer_iin_bin, sum(priority) AS ball1
    FROM algo
    GROUP BY taxpayer_iin_bin
),
ball2_t AS (
    SELECT taxpayer_iin_bin, benefeciary_iin_bin, sum(priority) AS ball2
    FROM algo
    GROUP BY taxpayer_iin_bin, benefeciary_iin_bin
),
-- Справочники сворачиваются до одной строки на идентификатор,
-- иначе LEFT JOIN размножит строки реестра
persons AS (
    SELECT p.taxpayer_iin_bin AS taxpayer_iin_bin, any(p.taxpayer_name) AS person_name
    FROM {settings.DICT_PERSONS} AS p
    WHERE p.taxpayer_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY p.taxpayer_iin_bin
),
companies AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        any(c.taxpayer_name) AS company_name,
        any(c.category) AS category
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM base)
    GROUP BY c.taxpayer_iin_bin
),
ownership AS (
    SELECT
        o.taxpayer_iin_bin AS taxpayer_iin_bin,
        any(o.ownership_type) AS ownership_type{ownership_category_select}
    FROM {settings.DICT_OWNERSHIP} AS o
    WHERE o.taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM base)
    GROUP BY o.taxpayer_iin_bin
),
documents AS (
    SELECT
        d.taxpayer_iin_bin AS taxpayer_iin_bin,
        concat('номер документа: ', any(d.doc_number), ', номер серии: ', any(d.doc_seria)) AS doc_info
    FROM {settings.DICT_DOCUMENTS} AS d
    WHERE d.taxpayer_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY d.taxpayer_iin_bin
),
shares AS (
    SELECT s.benefeciary_iin_bin AS benefeciary_iin_bin, any(s.share_percentage) AS share_percentage
    FROM {settings.DICT_SHARES} AS s
    WHERE s.benefeciary_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY s.benefeciary_iin_bin
),
-- Имя бенефициара определяется на уровне строки: правило подстановки
-- из dop_info зависит от кода алгоритма
named AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_iin_bin AS benefeciary_iin_bin,
        b.status AS status,
        b.algorithm_code AS algorithm_code,
        b.priority AS priority,
        b._actual_date AS _actual_date,
        b.dop_info AS dop_info,
        if(COALESCE(p.person_name, '') != '',
            p.person_name,
            if(b.algorithm_code IN ({first_part_list}),
                trim(BOTH ' ' FROM splitByChar(',', b.dop_info)[1]),
                b.dop_info)) AS benefeciary_name
    FROM base b
    LEFT JOIN persons p ON b.benefeciary_iin_bin = p.taxpayer_iin_bin
),
pairs AS (
    SELECT
        n.taxpayer_iin_bin AS taxpayer_iin_bin,
        n.benefeciary_iin_bin AS benefeciary_iin_bin,
        -- при нескольких сработавших алгоритмах побеждает статус с наименьшим
        -- баллом: регистрационный (priority 0) важнее предполагаемого
        argMin(n.status, n.priority) AS status,
        argMin(n.benefeciary_name, n.priority) AS benefeciary_name,
        argMin(n.dop_info, n.priority) AS dop_info,
        arraySort(groupUniqArray(n.algorithm_code)) AS algorithm_codes,
        min(n.priority) AS min_priority,
        max(n.`_actual_date`) AS _actual_date
    FROM named AS n
    GROUP BY n.taxpayer_iin_bin, n.benefeciary_iin_bin
)
SELECT
    pr.taxpayer_iin_bin AS taxpayer_iin_bin,
    COALESCE(comp.company_name, '') AS taxpayer_name,
    pr.benefeciary_iin_bin AS benefeciary_iin_bin,
    pr.benefeciary_name AS benefeciary_name,
    pr.status AS status,
    pr.algorithm_codes AS algorithm_codes,
    arrayStringConcat(pr.algorithm_codes, ', ') AS algorithms,
    pr.min_priority AS priority,
    COALESCE({category_expr}, '') AS category,
    COALESCE(own.ownership_type, '') AS ownership_type,
    COALESCE(doc.doc_info, '') AS document_info,
    COALESCE(sh.share_percentage, '') AS share_percentage,
    pr._actual_date AS _actual_date,
    pr.dop_info AS dop_info,
    b1.ball1 AS ball1,
    b2.ball2 AS ball2,
    if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2)) AS ball3
FROM pairs pr
LEFT JOIN ball1_t b1 ON pr.taxpayer_iin_bin = b1.taxpayer_iin_bin
LEFT JOIN ball2_t b2 ON pr.taxpayer_iin_bin = b2.taxpayer_iin_bin
    AND pr.benefeciary_iin_bin = b2.benefeciary_iin_bin
LEFT JOIN companies comp ON pr.taxpayer_iin_bin = comp.taxpayer_iin_bin
LEFT JOIN ownership own ON pr.taxpayer_iin_bin = own.taxpayer_iin_bin
LEFT JOIN documents doc ON pr.benefeciary_iin_bin = doc.taxpayer_iin_bin
LEFT JOIN shares sh ON pr.benefeciary_iin_bin = sh.benefeciary_iin_bin
-- Фильтр из ТЗ: исключаются строки, где пуст и ИИН, и имя бенефициара
WHERE NOT (pr.benefeciary_iin_bin = '' AND pr.benefeciary_name = '')
{having}
{limit_clause}
""".strip()


def build_company_summary_sql(
    result_tables: Iterable[str], company_filter: Optional[str] = None
) -> str:
    """Сводка по компаниям для страницы поиска.

    Возвращает количество уникальных бенефициаров и максимальный ball3
    по каждому taxpayer_iin_bin, попавшему в фильтр.

    Без фильтра считается весь реестр — так строятся дашборд и список ЮЛ.
    Запрос при этом тяжёлый, поэтому его результат кешируется в
    ``listing_service``, а не запрашивается на каждое обращение.
    """
    union_sql = build_union_sql(result_tables)
    where_clause = f"WHERE {company_filter}" if company_filter else ""
    return f"""
WITH base AS (
    -- Приведение типов уже сделано в объединении, повторять его здесь нельзя:
    -- «toString(x) AS x» новый анализатор ClickHouse принимает за ссылку
    -- на создаваемый псевдоним и запрос падает
    SELECT DISTINCT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        algorithm_code,
        priority
    FROM (
{union_sql}
    )
    {where_clause}
),
algo AS (
    SELECT
        b.taxpayer_iin_bin AS taxpayer_iin_bin,
        b.benefeciary_iin_bin AS benefeciary_iin_bin,
        b.algorithm_code AS algorithm_code,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_iin_bin, b.benefeciary_iin_bin, b.algorithm_code
),
ball2_t AS (
    SELECT
        a.taxpayer_iin_bin AS taxpayer_iin_bin,
        a.benefeciary_iin_bin AS benefeciary_iin_bin,
        sum(a.priority) AS ball2
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin, a.benefeciary_iin_bin
),
ball1_t AS (
    SELECT a.taxpayer_iin_bin AS taxpayer_iin_bin, sum(a.priority) AS ball1
    FROM algo AS a
    GROUP BY a.taxpayer_iin_bin
)
SELECT
    b2.taxpayer_iin_bin AS taxpayer_iin_bin,
    count(DISTINCT b2.benefeciary_iin_bin) AS beneficiary_count,
    max(if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2))) AS max_ball3
FROM ball2_t b2
LEFT JOIN ball1_t b1 ON b2.taxpayer_iin_bin = b1.taxpayer_iin_bin
GROUP BY b2.taxpayer_iin_bin
""".strip()


def build_stats_sql(result_tables: Iterable[str]) -> str:
    """Общая статистика реестра для /api/stats."""
    union_sql = build_union_sql(result_tables)
    return f"""
WITH base AS (
    SELECT DISTINCT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        status,
        algorithm_code,
        priority
    FROM (
{union_sql}
    )
    WHERE NOT (benefeciary_iin_bin = '' AND status = '')
)
SELECT
    count() AS total_rows,
    uniqExact(b.taxpayer_iin_bin) AS company_count,
    uniqExact(b.benefeciary_iin_bin) AS beneficiary_count,
    uniqExactIf(b.benefeciary_iin_bin, b.status LIKE 'Регистрационный%') AS registration_count,
    uniqExactIf(b.benefeciary_iin_bin, b.status LIKE 'Предполагаемый%') AS assumed_count,
    uniqExactIf(b.benefeciary_iin_bin, b.status LIKE '%нерезидент%') AS nonresident_count
FROM base AS b
""".strip()


def build_stats_by_algorithm_sql(result_tables: Iterable[str]) -> str:
    """Разрез статистики по алгоритмам."""
    union_sql = build_union_sql(result_tables)
    return f"""
SELECT
    d.algorithm_code AS algorithm_code,
    any(d.priority) AS priority,
    uniqExact(d.taxpayer_iin_bin) AS company_count,
    uniqExact(d.benefeciary_iin_bin) AS beneficiary_count,
    count() AS row_count
FROM (
    SELECT DISTINCT
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        algorithm_code,
        priority
    FROM (
{union_sql}
    )
) AS d
GROUP BY d.algorithm_code
ORDER BY d.algorithm_code
""".strip()
