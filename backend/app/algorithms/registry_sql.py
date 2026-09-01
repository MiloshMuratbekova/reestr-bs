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

from app.algorithms import cleaning
from app.core.config import settings

# Алгоритмы, у которых имя бенефициара при отсутствии в справочнике ФЛ
# берётся из первой части dop_info до первой запятой.
#
# Перечень взят из итоговой таблицы AFM_6_1_99: у этих алгоритмов dop_info
# начинается с ФИО, а дальше через запятую идут сведения об источнике —
# гражданство, документ, доля. У остальных dop_info целиком является именем,
# и обрезать его по запятой нельзя.
DOP_INFO_FIRST_PART_ALGORITHMS = ("БС-7", "БС-14", "БС-17")


def build_union_sql(result_tables: Iterable[str]) -> str:
    """UNION ALL по таблицам результатов алгоритмов — семь полей из ТЗ.

    Типы приводятся к общему виду: _actual_date в таблицах алгоритмов
    встречается и строкой, и датой; priority — целым разной ширины.

    Каждое поле оборачивается в ifNull. Колонки таблиц алгоритмов на боевом
    сервере объявлены Nullable, а toString от Nullable возвращает Nullable —
    и дальше splitByChar по dop_info даёт Nullable(Array(String)), который
    ClickHouse запрещает: «Nested type Array(String) cannot be inside Nullable
    type». Снимая Nullable здесь, у самого источника, мы избавляем от него
    весь остальной запрос разом.

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
        ifNull(toString(src.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
        ifNull(toString(src.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
        ifNull(toString(src.status), '') AS status,
        ifNull(toString(src.algorithm_code), '') AS algorithm_code,
        ifNull(toInt32OrZero(toString(src.priority)), 0) AS priority,
        ifNull(toString(src.`_actual_date`), '') AS _actual_date,
        ifNull(toString(src.dop_info), '') AS dop_info
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
    resolution_map: Optional[str] = None,
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

    # ------------------------------------------------------------------
    # Доведение бенефициара до физического лица.
    #
    # Бенефициарный собственник по определению — физическое лицо. Часть
    # алгоритмов возвращает юридическое: акционером числится ТОО, учредителем
    # с долей 25% — другая компания. Такое ЮЛ не ответ, а промежуточное звено.
    #
    # Сама раскрутка цепочки здесь не выполняется — она посчитана заранее
    # и лежит в карте UL_RESOLUTION_TABLE (см. build_ul_resolution_sql).
    # Причина простая: перебор по всем алгоритмам на четыре уровня — это
    # около сотни обращений к таблицам, и вставлять его в КАЖДЫЙ запрос
    # реестра нельзя, запрос переставал планироваться за разумное время.
    # Карта строится один раз, в конце ночного пересчёта.
    # ------------------------------------------------------------------
    owner_join = ""
    resolved_expr = "r.benefeciary_iin_bin"
    if resolution_map:
        owner_join = (
            f"LEFT JOIN {resolution_map} AS w"
            " ON r.benefeciary_iin_bin = w.ul_iin_bin"
        )
        resolved_expr = (
            "if(left(right(r.benefeciary_iin_bin, 8), 1) IN ('4', '5')"
            " AND COALESCE(w.fl_iin_bin, '') != '',"
            " w.fl_iin_bin, r.benefeciary_iin_bin)"
        )

    # Бенефициарный собственник — всегда физическое лицо. Юридическое,
    # которое не удалось развернуть до ФЛ даже за четыре уровня, в реестр
    # не попадает: это не ответ, а тупик в цепочке владения.
    #
    # Отсев делается в base, до расчёта баллов, а не в конце. Иначе такая
    # строка входила бы в ball1 компании и занижала вероятность настоящих
    # бенефициаров — при том что сама в выдаче не показывалась бы.
    base_conditions: List[str] = []
    if company_filter:
        base_conditions.append(f"({company_filter})")
    if resolution_map:
        # Признак ЮЛ проверяется по настоящему ИИН, а не по ключу: у ключа
        # вида «нерезидент: …» никакой структуры БИН нет, и правило пятого
        # знака к нему неприменимо.
        base_conditions.append(
            "(iin_clean = '' OR left(right(iin_clean, 8), 1) NOT IN ('4', '5'))"
        )
    base_where = ("WHERE " + " AND ".join(base_conditions)) if base_conditions else ""

    # Выражения приведения данных в порядок — см. app.algorithms.cleaning
    clean_iin_expr = cleaning.clean_iin("r.benefeciary_iin_bin")
    if resolution_map:
        clean_iin_expr = cleaning.clean_iin(f"({resolved_expr})")
    quoted_expr = cleaning.quoted_name("c.dop_info")
    first_part_expr = cleaning.first_part("c.dop_info")
    key_expr = cleaning.beneficiary_key("k.iin_clean", "k.benefeciary_name")
    nonresident_status_expr = cleaning.nonresident_status("k.status")
    persons_table = settings.DICT_PERSONS

    # Отбор по компании можно применить ещё до подстановки: замена меняет
    # бенефициара, но никогда не трогает taxpayer_iin_bin. Для карточки
    # компании это решающее — иначе пришлось бы разворачивать весь реестр.
    prefilter = ""
    if company_filter and "benefeciary_iin_bin" not in company_filter:
        prefilter = f"WHERE {company_filter}"

    # Ограничение числа строк ставится в самом запросе: даже если клиент
    # попросит больше, до него дойдёт только разрешённое количество
    limit_clause = f"LIMIT {int(row_limit)}" if row_limit else ""

    return f"""
WITH raw AS (
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
    {prefilter}
),
-- Приведение ИИН в порядок: заглушки 000000000, «-», «нет» и текст вместо
-- номера обнуляются. Делается до всего остального, потому что дальше ИИН
-- служит ключом сведения.
cleaned AS (
    SELECT
        r.taxpayer_iin_bin AS taxpayer_iin_bin,
        {clean_iin_expr} AS iin_clean,
        r.status AS status,
        r.algorithm_code AS algorithm_code,
        r.priority AS priority,
        r.`_actual_date` AS _actual_date,
        r.dop_info AS dop_info
    FROM raw AS r
    {owner_join}
),
persons AS (
    SELECT
        p.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(any(p.taxpayer_name), '') AS person_name
    FROM {persons_table} AS p
    WHERE p.taxpayer_iin_bin IN (SELECT iin_clean FROM cleaned WHERE iin_clean != '')
    GROUP BY p.taxpayer_iin_bin
),
-- Имя, ключ и статус считаются здесь, ДО расчёта баллов. Иначе ball1 и ball2
-- сложились бы по грязному ИИН, а в выдаче стоял бы чистый — и проценты
-- перестали бы сходиться с показанными строками.
keyed AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        c.iin_clean AS iin_clean,
        c.status AS status,
        c.algorithm_code AS algorithm_code,
        c.priority AS priority,
        c.`_actual_date` AS _actual_date,
        c.dop_info AS dop_info,
        -- Имя: справочник ФЛ, затем наименование из кавычек, затем правило
        -- «до первой запятой» для алгоритмов, где dop_info начинается с ФИО
        if(COALESCE(pr.person_name, '') != '',
            pr.person_name,
            if({quoted_expr} != '',
                {quoted_expr},
                if(c.algorithm_code IN ({first_part_list}),
                    {first_part_expr},
                    c.dop_info))) AS benefeciary_name
    FROM cleaned AS c
    LEFT JOIN persons AS pr ON c.iin_clean = pr.taxpayer_iin_bin
),
base AS (
    SELECT * FROM (
        SELECT
            k.taxpayer_iin_bin AS taxpayer_iin_bin,
            k.iin_clean AS iin_clean,
            -- Ключ сведения: настоящий ИИН, а при его отсутствии — «нерезидент»
            -- с именем. Одно только слово «нерезидент» склеило бы разных
            -- иностранцев одной компании в одну строку.
            {key_expr} AS benefeciary_iin_bin,
            k.benefeciary_name AS benefeciary_name,
            -- Нет настоящего ИИН — значит казахстанского номера у лица нет,
            -- и это нерезидент. Тип БС при этом сохраняется.
            if(k.iin_clean = '',
                {nonresident_status_expr},
                if(right(left(k.iin_clean, 5), 1) = '5'
                    OR (right(left(k.iin_clean, 5), 1) IN ('1', '2', '3')
                        AND right(left(k.iin_clean, 7), 1) = '0'),
                    {nonresident_status_expr},
                    k.status)) AS status,
            k.algorithm_code AS algorithm_code,
            k.priority AS priority,
            k.`_actual_date` AS _actual_date,
            k.dop_info AS dop_info
        FROM keyed AS k
        -- Строки без ИИН и без имени опознать нельзя — они не бенефициары
        WHERE NOT (k.iin_clean = '' AND k.benefeciary_name = '')
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
    WHERE d.taxpayer_iin_bin IN (SELECT iin_clean FROM base WHERE iin_clean != '')
    GROUP BY d.taxpayer_iin_bin
),
-- Доля участия берётся по колонке taxpayer_iin_bin таблицы долей: в ней
-- лежит идентификатор самого владельца, а не компании. Так же соединяет
-- итоговая таблица AFM_6_1_99 (a11 по t.benefeciary_iin_bin).
shares AS (
    SELECT s.taxpayer_iin_bin AS holder_iin_bin, any(s.share_percentage) AS share_percentage
    FROM {settings.DICT_SHARES} AS s
    WHERE s.taxpayer_iin_bin != ''
      AND s.taxpayer_iin_bin IN (SELECT iin_clean FROM base WHERE iin_clean != '')
    GROUP BY s.taxpayer_iin_bin
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
    FROM base AS n
    GROUP BY n.taxpayer_iin_bin, n.benefeciary_iin_bin
)
SELECT
    pr.taxpayer_iin_bin AS taxpayer_iin_bin,
    COALESCE(comp.company_name, '') AS taxpayer_name,
    pr.benefeciary_iin_bin AS benefeciary_iin_bin,
    pr.benefeciary_name AS benefeciary_name,
    -- Статус уже уточнён в base: там известен настоящий ИИН, до того как
    -- он подменяется ключом «нерезидент: …». Здесь берётся готовое значение
    -- по алгоритму с наименьшим баллом.
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
LEFT JOIN shares sh ON pr.benefeciary_iin_bin = sh.holder_iin_bin
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
