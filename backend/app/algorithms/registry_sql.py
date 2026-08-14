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
    """
    tables = [t for t in result_tables if t]
    if not tables:
        raise ValueError("Нет ни одной активной таблицы результатов алгоритмов")

    parts: List[str] = []
    for table in tables:
        parts.append(
            f"""    SELECT
        toString(taxpayer_iin_bin) AS taxpayer_iin_bin,
        toString(benefeciary_iin_bin) AS benefeciary_iin_bin,
        toString(status) AS status,
        toString(algorithm_code) AS algorithm_code,
        toInt32(priority) AS priority,
        toString(_actual_date) AS _actual_date,
        toString(dop_info) AS dop_info
    FROM {table}"""
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
        ownership_category_select = ", any(category) AS category"
    else:
        category_expr = "comp.category"
        ownership_category_select = ""

    having = ""
    if extra_conditions:
        having = "WHERE " + " AND ".join(extra_conditions)

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
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        algorithm_code,
        any(priority) AS priority
    FROM base
    GROUP BY taxpayer_iin_bin, benefeciary_iin_bin, algorithm_code
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
    SELECT taxpayer_iin_bin, any(taxpayer_name) AS person_name
    FROM {settings.DICT_PERSONS}
    WHERE taxpayer_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY taxpayer_iin_bin
),
companies AS (
    SELECT taxpayer_iin_bin, any(taxpayer_name) AS company_name, any(category) AS category
    FROM {settings.DICT_COMPANIES}
    WHERE taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM base)
    GROUP BY taxpayer_iin_bin
),
ownership AS (
    SELECT taxpayer_iin_bin, any(ownership_type) AS ownership_type{ownership_category_select}
    FROM {settings.DICT_OWNERSHIP}
    WHERE taxpayer_iin_bin IN (SELECT taxpayer_iin_bin FROM base)
    GROUP BY taxpayer_iin_bin
),
documents AS (
    SELECT
        taxpayer_iin_bin,
        concat('номер документа: ', any(doc_number), ', номер серии: ', any(doc_seria)) AS doc_info
    FROM {settings.DICT_DOCUMENTS}
    WHERE taxpayer_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY taxpayer_iin_bin
),
shares AS (
    SELECT benefeciary_iin_bin, any(share_percentage) AS share_percentage
    FROM {settings.DICT_SHARES}
    WHERE benefeciary_iin_bin IN (SELECT benefeciary_iin_bin FROM base)
    GROUP BY benefeciary_iin_bin
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
        taxpayer_iin_bin,
        benefeciary_iin_bin,
        -- при нескольких сработавших алгоритмах побеждает статус с наименьшим
        -- баллом: регистрационный (priority 0) важнее предполагаемого
        argMin(status, priority) AS status,
        argMin(benefeciary_name, priority) AS benefeciary_name,
        argMin(dop_info, priority) AS dop_info,
        arraySort(groupUniqArray(algorithm_code)) AS algorithm_codes,
        min(priority) AS min_priority,
        max(_actual_date) AS _actual_date
    FROM named
    GROUP BY taxpayer_iin_bin, benefeciary_iin_bin
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


def build_company_summary_sql(result_tables: Iterable[str], company_filter: str) -> str:
    """Сводка по компаниям для страницы поиска.

    Возвращает количество уникальных бенефициаров и максимальный ball3
    по каждому taxpayer_iin_bin, попавшему в фильтр.
    """
    union_sql = build_union_sql(result_tables)
    return f"""
WITH base AS (
    SELECT DISTINCT
        toString(taxpayer_iin_bin) AS taxpayer_iin_bin,
        toString(benefeciary_iin_bin) AS benefeciary_iin_bin,
        toString(algorithm_code) AS algorithm_code,
        toInt32(priority) AS priority
    FROM (
{union_sql}
    )
    WHERE {company_filter}
),
algo AS (
    SELECT taxpayer_iin_bin, benefeciary_iin_bin, algorithm_code, any(priority) AS priority
    FROM base
    GROUP BY taxpayer_iin_bin, benefeciary_iin_bin, algorithm_code
),
ball2_t AS (
    SELECT taxpayer_iin_bin, benefeciary_iin_bin, sum(priority) AS ball2
    FROM algo
    GROUP BY taxpayer_iin_bin, benefeciary_iin_bin
),
ball1_t AS (
    SELECT taxpayer_iin_bin, sum(priority) AS ball1
    FROM algo
    GROUP BY taxpayer_iin_bin
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
        toString(taxpayer_iin_bin) AS taxpayer_iin_bin,
        toString(benefeciary_iin_bin) AS benefeciary_iin_bin,
        toString(status) AS status,
        toString(algorithm_code) AS algorithm_code,
        toInt32(priority) AS priority
    FROM (
{union_sql}
    )
    WHERE NOT (benefeciary_iin_bin = '' AND status = '')
)
SELECT
    count() AS total_rows,
    uniqExact(taxpayer_iin_bin) AS company_count,
    uniqExact(benefeciary_iin_bin) AS beneficiary_count,
    uniqExactIf(benefeciary_iin_bin, status LIKE 'Регистрационный%') AS registration_count,
    uniqExactIf(benefeciary_iin_bin, status LIKE 'Предполагаемый%') AS assumed_count,
    uniqExactIf(benefeciary_iin_bin, status LIKE '%нерезидент%') AS nonresident_count
FROM base
""".strip()


def build_stats_by_algorithm_sql(result_tables: Iterable[str]) -> str:
    """Разрез статистики по алгоритмам."""
    union_sql = build_union_sql(result_tables)
    return f"""
SELECT
    algorithm_code,
    any(priority) AS priority,
    uniqExact(taxpayer_iin_bin) AS company_count,
    uniqExact(benefeciary_iin_bin) AS beneficiary_count,
    count() AS row_count
FROM (
    SELECT DISTINCT
        toString(taxpayer_iin_bin) AS taxpayer_iin_bin,
        toString(benefeciary_iin_bin) AS benefeciary_iin_bin,
        toString(algorithm_code) AS algorithm_code,
        toInt32(priority) AS priority
    FROM (
{union_sql}
    )
)
GROUP BY algorithm_code
ORDER BY algorithm_code
""".strip()
