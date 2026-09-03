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


def build_union_sql(
    result_tables: Iterable[str], named_tables: Iterable[str] = ()
) -> str:
    """UNION ALL по таблицам результатов алгоритмов — семь полей из ТЗ.

    :param named_tables: таблицы, у которых есть колонка ``taxpayer_name``.
        Ею различаются иностранные организации: в сводной таблице у них
        вместо БИН стоит одинаковый текст «Иностранная компания», и без
        наименования все они слились бы в одну.

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

    # Наименование компании есть только в сводной таблице; у таблиц отдельных
    # алгоритмов такой колонки нет, и спрашивать её у них нельзя — запрос
    # упадёт на разборе. Для них подставляется пустая строка.
    named = {t for t in named_tables if t}

    parts: List[str] = []
    for table in tables:
        taxpayer_name = (
            "ifNull(toString(src.taxpayer_name), '')"
            if table in named
            else "''"
        )
        parts.append(
            f"""    SELECT
        ifNull(toString(src.taxpayer_iin_bin), '') AS taxpayer_iin_bin,
        {taxpayer_name} AS taxpayer_name,
        ifNull(toString(src.benefeciary_iin_bin), '') AS benefeciary_iin_bin,
        ifNull(toString(src.status), '') AS status,
        ifNull(toString(src.algorithm_code), '') AS algorithm_code,
        ifNull(toInt32OrZero(toString(src.priority)), 0) AS priority,
        ifNull(toString(src.`_actual_date`), '') AS _actual_date,
        ifNull(toString(src.dop_info), '') AS dop_info
    FROM {table} AS src"""
        )
    return "\n    UNION ALL\n".join(parts)


def build_keyed_union_sql(
    union_sql: str, passthrough: List[str], *, where: str = ""
) -> str:
    """Объединение, приведённое в порядок: очищенный ИИН и ключ сведения.

    Нужен сводкам и статистике. Без него они считали бы по сырому полю:
    заглушки 000000000 и «-» шли бы за отдельных бенефициаров, а один и тот
    же нерезидент, записанный двумя алгоритмами по-разному, — за двоих.
    Числа на дашборде тогда не сходятся с содержимым карточек.
    """
    iin_clean = cleaning.clean_iin("u.benefeciary_iin_bin")
    bin_clean = cleaning.clean_bin("u.taxpayer_iin_bin")
    name = cleaning.display_name("u.dop_info")
    key = cleaning.beneficiary_key("k.iin_clean", "k.benefeciary_name")
    company = cleaning.company_key("k.bin_clean", "k.taxpayer_name")
    inner = "".join(f"        u.{column} AS {column},\n" for column in passthrough)
    outer = "".join(f"        k.{column} AS {column},\n" for column in passthrough)
    return f"""    SELECT DISTINCT
        {company} AS taxpayer_key,
        k.bin_clean AS bin_clean,
        k.taxpayer_name AS taxpayer_name,
        {key} AS benefeciary_key,
        k.iin_clean AS iin_clean,
        k.benefeciary_name AS benefeciary_name,
{outer}        1 AS _keyed
    FROM (
        SELECT
            {bin_clean} AS bin_clean,
            u.taxpayer_name AS taxpayer_name,
            {iin_clean} AS iin_clean,
            {name} AS benefeciary_name,
{inner}        1 AS _raw
        FROM (
{union_sql}
        ) AS u
        {where}
    ) AS k
    -- Ни ИИН, ни имени — опознать лицо нечем
    WHERE NOT (k.iin_clean = '' AND k.benefeciary_name = '')"""


def build_registry_sql(
    result_tables: Iterable[str],
    *,
    named_tables: Iterable[str] = (),
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
    union_sql = build_union_sql(result_tables, named_tables)

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

    # Бенефициарный собственник — всегда физическое лицо. Юридическое сначала
    # разворачивается по цепочке владения (см. resolution_map). Если даже за
    # четыре уровня физлицо не нашлось, строка НЕ отбрасывается, а помечается
    # «цепочка не раскрыта»: скрывать зацепку хуже, чем показать её с оговоркой,
    # иначе карточка молчит при непустой таблице результатов.
    #
    # Помеченные строки считаются в ball1 наравне с остальными — проценты
    # должны сходиться с тем, что показано.
    base_conditions: List[str] = []
    if company_filter:
        base_conditions.append(f"({company_filter})")
    base_where = ("WHERE " + " AND ".join(base_conditions)) if base_conditions else ""

    # Выражения приведения данных в порядок — см. app.algorithms.cleaning
    clean_iin_expr = cleaning.clean_iin("r.benefeciary_iin_bin")
    if resolution_map:
        clean_iin_expr = cleaning.clean_iin(f"({resolved_expr})")
    quoted_expr = cleaning.quoted_name("c.dop_info")
    first_part_expr = cleaning.first_part("c.dop_info")
    key_expr = cleaning.beneficiary_key("k.iin_clean", "k.benefeciary_name")
    nonresident_status_expr = cleaning.nonresident_status("k.status")
    unresolved_status_expr = cleaning.unresolved_ul_status("k.status")
    display_name_expr = cleaning.display_name("c.dop_info")
    display_iin_expr = cleaning.display_iin_with_id(
        "pr.iin_clean", "pr.is_nonresident", "pr.dop_info"
    )
    is_ul_expr = cleaning.IS_UL.format(col="k.iin_clean")
    clean_bin_expr = cleaning.clean_bin("r.taxpayer_iin_bin")
    company_key_expr = cleaning.company_key("c.bin_clean", "c.taxpayer_name")
    display_bin_expr = cleaning.display_company_bin("pr.bin_clean")
    persons_table = settings.DICT_PERSONS
    companies_table = settings.DICT_COMPANIES

    # Отбор по компании можно применить ещё до подстановки: замена меняет
    # бенефициара, но никогда не трогает taxpayer_iin_bin. Для карточки
    # компании это решающее — иначе пришлось бы разворачивать весь реестр.
    prefilter = ""
    if company_filter and "taxpayer_key" in company_filter:
        # У иностранных организаций в сыром поле стоит одинаковый текст,
        # а ключ собирается позже, из наименования. Поэтому здесь они
        # пропускаются все, а нужную выберет условие по ключу в base.
        raw_filter = company_filter.replace("taxpayer_key", "taxpayer_iin_bin")
        prefilter = (
            f"WHERE ({raw_filter})"
            f" OR taxpayer_iin_bin = '{cleaning.FOREIGN_COMPANY}'"
        )

    # Ограничение числа строк ставится в самом запросе: даже если клиент
    # попросит больше, до него дойдёт только разрешённое количество
    limit_clause = f"LIMIT {int(row_limit)}" if row_limit else ""

    return f"""
WITH raw AS (
    SELECT DISTINCT
        taxpayer_iin_bin,
        taxpayer_name,
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
        {clean_bin_expr} AS bin_clean,
        r.taxpayer_name AS taxpayer_name,
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
-- Наименование юрлица-бенефициара берётся из справочника по его БИН, а не из
-- dop_info. В dop_info одна и та же организация у разных алгоритмов записана
-- по-разному, и один БИН получал бы разные названия. Справочник даёт одно.
beneficiary_names AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        ifNull(any(c.taxpayer_name), '') AS company_name
    FROM {companies_table} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT iin_clean FROM cleaned WHERE iin_clean != '')
    GROUP BY c.taxpayer_iin_bin
),
-- Имя, ключ и статус считаются здесь, ДО расчёта баллов. Иначе ball1 и ball2
-- сложились бы по грязному ИИН, а в выдаче стоял бы чистый — и проценты
-- перестали бы сходиться с показанными строками.
keyed AS (
    SELECT
        c.bin_clean AS bin_clean,
        c.taxpayer_name AS taxpayer_name,
        -- Ключ компании: БИН, а у иностранной — слово с наименованием.
        -- Одно только слово склеило бы все иностранные организации в одну.
        {company_key_expr} AS taxpayer_key,
        c.iin_clean AS iin_clean,
        c.status AS status,
        c.algorithm_code AS algorithm_code,
        c.priority AS priority,
        c.`_actual_date` AS _actual_date,
        c.dop_info AS dop_info,
        -- В поле имени должно остаться только имя. По убыванию надёжности:
        -- справочник физлиц, справочник организаций, разбор строки сведений.
        -- Справочники стоят первыми потому, что дают одно и то же имя для
        -- одного ИИН независимо от того, какой алгоритм нашёл лицо.
        if(COALESCE(pr.person_name, '') != '',
            pr.person_name,
            if(COALESCE(bn.company_name, '') != '',
                bn.company_name,
                {display_name_expr})) AS benefeciary_name
    FROM cleaned AS c
    LEFT JOIN persons AS pr ON c.iin_clean = pr.taxpayer_iin_bin
    LEFT JOIN beneficiary_names AS bn ON c.iin_clean = bn.taxpayer_iin_bin
),
base AS (
    SELECT * FROM (
        SELECT
            k.bin_clean AS bin_clean,
            -- Настоящий БИН доступен и под прежним именем: по нему можно
            -- отбирать компанию, не зная служебного ключа
            k.bin_clean AS taxpayer_iin_bin,
            k.taxpayer_name AS taxpayer_name,
            k.taxpayer_key AS taxpayer_key,
            k.iin_clean AS iin_clean,
            -- Ключ сведения — служебный. Настоящий ИИН, а при его отсутствии
            -- «нерезидент» с именем: одно только слово «нерезидент» склеило бы
            -- разных иностранцев одной компании в одну строку. В поле ИИН этот
            -- ключ не показывается, для показа есть benefeciary_iin_bin ниже.
            {key_expr} AS benefeciary_key,
            k.benefeciary_name AS benefeciary_name,
            -- Признак нерезидента: своего ИИН нет либо он выдан иностранцу
            (k.iin_clean = ''
                OR right(left(k.iin_clean, 5), 1) = '5'
                OR (right(left(k.iin_clean, 5), 1) IN ('1', '2', '3')
                    AND right(left(k.iin_clean, 7), 1) = '0')) AS is_nonresident,
            -- Порядок важен. Сначала юрлицо: если после раскрутки ИИН всё ещё
            -- принадлежит организации, цепочка не сошлась. Затем нерезидент:
            -- нет настоящего ИИН — значит казахстанского номера у лица нет.
            -- Тип БС в обоих случаях сохраняется.
            if({is_ul_expr},
                {unresolved_status_expr},
                if(k.iin_clean = ''
                    OR right(left(k.iin_clean, 5), 1) = '5'
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
        b.taxpayer_key AS taxpayer_key,
        b.benefeciary_key AS benefeciary_key,
        b.algorithm_code AS algorithm_code,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_key, b.benefeciary_key, b.algorithm_code
),
ball1_t AS (
    SELECT taxpayer_key, sum(priority) AS ball1
    FROM algo
    GROUP BY taxpayer_key
),
ball2_t AS (
    SELECT taxpayer_key, benefeciary_key, sum(priority) AS ball2
    FROM algo
    GROUP BY taxpayer_key, benefeciary_key
),
-- Справочники сворачиваются до одной строки на идентификатор,
-- иначе LEFT JOIN размножит строки реестра
companies AS (
    SELECT
        c.taxpayer_iin_bin AS taxpayer_iin_bin,
        any(c.taxpayer_name) AS company_name,
        any(c.category) AS category
    FROM {settings.DICT_COMPANIES} AS c
    WHERE c.taxpayer_iin_bin IN (SELECT bin_clean FROM base WHERE bin_clean != '')
    GROUP BY c.taxpayer_iin_bin
),
ownership AS (
    SELECT
        o.taxpayer_iin_bin AS taxpayer_iin_bin,
        any(o.ownership_type) AS ownership_type{ownership_category_select}
    FROM {settings.DICT_OWNERSHIP} AS o
    WHERE o.taxpayer_iin_bin IN (SELECT bin_clean FROM base WHERE bin_clean != '')
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
        n.taxpayer_key AS taxpayer_key,
        any(n.bin_clean) AS bin_clean,
        argMin(n.taxpayer_name, (n.priority, n.taxpayer_name)) AS source_company_name,
        n.benefeciary_key AS benefeciary_key,
        any(n.iin_clean) AS iin_clean,
        max(n.is_nonresident) AS is_nonresident,
        -- при нескольких сработавших алгоритмах побеждает статус с наименьшим
        -- баллом: регистрационный (priority 0) важнее предполагаемого
        argMin(n.status, n.priority) AS status,
        -- Ключ сравнения — пара (балл, само имя). Без имени в ключе при двух
        -- алгоритмах с равным баллом победитель выбирался бы произвольно,
        -- и один и тот же ИИН мог называться по-разному в карточке и в списке.
        argMin(n.benefeciary_name, (n.priority, n.benefeciary_name)) AS benefeciary_name,
        argMin(n.dop_info, (n.priority, n.benefeciary_name)) AS dop_info,
        arraySort(groupUniqArray(n.algorithm_code)) AS algorithm_codes,
        min(n.priority) AS min_priority,
        max(n.`_actual_date`) AS _actual_date
    FROM base AS n
    GROUP BY n.taxpayer_key, n.benefeciary_key
)
SELECT
    -- Служебный ключ компании: по нему строятся ссылки и сведение
    pr.taxpayer_key AS taxpayer_key,
    -- В поле БИН только номер либо слово «Иностранная компания»
    {display_bin_expr} AS taxpayer_iin_bin,
    -- Наименование: справочник ЮЛ, затем то, что дала сводная таблица
    if(COALESCE(comp.company_name, '') != '',
        comp.company_name,
        pr.source_company_name) AS taxpayer_name,
    -- Служебный ключ: по нему строятся ссылки и сведение
    pr.benefeciary_key AS benefeciary_key,
    -- В поле ИИН только номер, слово «нерезидент» либо пусто
    {display_iin_expr} AS benefeciary_iin_bin,
    pr.is_nonresident AS is_nonresident,
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
LEFT JOIN ball1_t b1 ON pr.taxpayer_key = b1.taxpayer_key
LEFT JOIN ball2_t b2 ON pr.taxpayer_key = b2.taxpayer_key
    AND pr.benefeciary_key = b2.benefeciary_key
LEFT JOIN companies comp ON pr.bin_clean = comp.taxpayer_iin_bin
LEFT JOIN ownership own ON pr.bin_clean = own.taxpayer_iin_bin
LEFT JOIN documents doc ON pr.iin_clean = doc.taxpayer_iin_bin
LEFT JOIN shares sh ON pr.iin_clean = sh.holder_iin_bin
-- Фильтр из ТЗ: исключаются строки, где пуст и ИИН, и имя бенефициара
WHERE NOT (pr.benefeciary_key = '' AND pr.benefeciary_name = '')
{having}
{limit_clause}
""".strip()


def build_company_summary_sql(
    result_tables: Iterable[str],
    company_filter: Optional[str] = None,
    named_tables: Iterable[str] = (),
) -> str:
    """Сводка по компаниям для страницы поиска.

    Возвращает количество уникальных бенефициаров и максимальный ball3
    по каждому taxpayer_iin_bin, попавшему в фильтр.

    Без фильтра считается весь реестр — так строятся дашборд и список ЮЛ.
    Запрос при этом тяжёлый, поэтому его результат кешируется в
    ``listing_service``, а не запрашивается на каждое обращение.
    """
    union_sql = build_union_sql(result_tables, named_tables)
    where_clause = f"WHERE {company_filter}" if company_filter else ""
    keyed_sql = build_keyed_union_sql(
        union_sql, ["algorithm_code", "priority"], where=where_clause
    )
    return f"""
WITH base AS (
{keyed_sql}
),
algo AS (
    SELECT
        b.taxpayer_key AS taxpayer_key,
        any(b.bin_clean) AS bin_clean,
        b.benefeciary_key AS benefeciary_key,
        b.algorithm_code AS algorithm_code,
        any(b.priority) AS priority
    FROM base AS b
    GROUP BY b.taxpayer_key, b.benefeciary_key, b.algorithm_code
),
ball2_t AS (
    SELECT
        a.taxpayer_key AS taxpayer_key,
        any(a.bin_clean) AS bin_clean,
        a.benefeciary_key AS benefeciary_key,
        sum(a.priority) AS ball2
    FROM algo AS a
    GROUP BY a.taxpayer_key, a.benefeciary_key
),
ball1_t AS (
    SELECT a.taxpayer_key AS taxpayer_key, sum(a.priority) AS ball1
    FROM algo AS a
    GROUP BY a.taxpayer_key
)
SELECT
    b2.taxpayer_key AS taxpayer_key,
    any(b2.bin_clean) AS bin_clean,
    count(DISTINCT b2.benefeciary_key) AS beneficiary_count,
    max(if(b1.ball1 = 0, 0, round(b2.ball2 / b1.ball1 * 100, 2))) AS max_ball3
FROM ball2_t b2
LEFT JOIN ball1_t b1 ON b2.taxpayer_key = b1.taxpayer_key
GROUP BY b2.taxpayer_key
""".strip()


def build_stats_sql(
    result_tables: Iterable[str], named_tables: Iterable[str] = ()
) -> str:
    """Общая статистика реестра для /api/stats."""
    union_sql = build_union_sql(result_tables, named_tables)
    keyed_sql = build_keyed_union_sql(
        union_sql, ["status", "algorithm_code", "priority"]
    )
    return f"""
WITH base AS (
{keyed_sql}
)
SELECT
    count() AS total_rows,
    uniqExact(b.taxpayer_key) AS company_count,
    uniqExact(b.benefeciary_key) AS beneficiary_count,
    uniqExactIf(b.benefeciary_key, b.status LIKE 'Регистрационный%') AS registration_count,
    uniqExactIf(b.benefeciary_key, b.status LIKE 'Предполагаемый%') AS assumed_count,
    -- Нерезидент опознаётся по отсутствию настоящего ИИН, а не по тексту
    -- статуса: пометка проставляется позже, при сборке реестра
    uniqExactIf(b.benefeciary_key, b.iin_clean = '') AS nonresident_count
FROM base AS b
""".strip()


def build_stats_by_algorithm_sql(
    result_tables: Iterable[str], named_tables: Iterable[str] = ()
) -> str:
    """Разрез статистики по алгоритмам."""
    union_sql = build_union_sql(result_tables, named_tables)
    keyed_sql = build_keyed_union_sql(union_sql, ["algorithm_code", "priority"])
    return f"""
SELECT
    d.algorithm_code AS algorithm_code,
    any(d.priority) AS priority,
    uniqExact(d.taxpayer_key) AS company_count,
    uniqExact(d.benefeciary_key) AS beneficiary_count,
    count() AS row_count
FROM (
{keyed_sql}
) AS d
GROUP BY d.algorithm_code
ORDER BY d.algorithm_code
""".strip()


def build_empty_reason_sql(
    result_tables: Iterable[str], named_tables: Iterable[str] = ()
) -> str:
    """Почему по компании ничего не показано, хотя строки в источнике есть.

    Считается по тому же объединению и той же чистке, что и реестр, но без
    расчёта баллов: нужен не результат, а причина отсева. Запрос выполняется
    только когда карточка вышла пустой, поэтому на обычную выдачу не влияет.

    Отдаёт по одной строке: сколько записей нашлось всего, сколько из них
    указывают на юрлицо (его надо раскрутить до физлица, и если цепочка
    не сошлась — строка выпадает), сколько не опознать вовсе, и какие
    алгоритмы эту компанию нашли.
    """
    union_sql = build_union_sql(result_tables, named_tables)
    first_part_list = ", ".join(f"'{code}'" for code in DOP_INFO_FIRST_PART_ALGORITHMS)
    iin_clean = cleaning.clean_iin("u.benefeciary_iin_bin")
    name = cleaning.name_from_dop("u.dop_info", "u.algorithm_code", first_part_list)

    return f"""
WITH cleaned AS (
    SELECT
        {iin_clean} AS iin_clean,
        {name} AS benefeciary_name,
        u.algorithm_code AS algorithm_code
    FROM (
{union_sql}
    ) AS u
    WHERE u.taxpayer_iin_bin = {{bin:String}}
)
SELECT
    count() AS rows_total,
    countIf(c.iin_clean != ''
        AND left(right(c.iin_clean, 8), 1) IN ('4', '5')) AS ul_rows,
    countIf(c.iin_clean = '' AND c.benefeciary_name = '') AS unidentified_rows,
    arraySort(groupUniqArray(c.algorithm_code)) AS algorithms
FROM cleaned AS c
"""


def build_company_name_fallback_sql(
    result_tables: Iterable[str], named_tables: Iterable[str] = ()
) -> str:
    """Наименование компании, которой нет в справочнике юридических лиц.

    Такое бывает у иностранных организаций: бенефициары у них выявлены,
    а в справочнике ЮЛ записи нет. Тот же БИН обычно встречается в реестре
    как бенефициар, и рядом лежит строка сведений с названием — её и
    разбираем теми же правилами, что и имя бенефициара.
    """
    union_sql = build_union_sql(result_tables, named_tables)
    iin_clean = cleaning.clean_iin("u.benefeciary_iin_bin")
    name = cleaning.display_name("u.dop_info")
    return f"""
SELECT argMin(k.name, (k.priority, k.name)) AS taxpayer_name
FROM (
    SELECT
        {iin_clean} AS iin_clean,
        {name} AS name,
        u.priority AS priority
    FROM (
{union_sql}
    ) AS u
) AS k
WHERE k.iin_clean = {{bin:String}} AND k.name != ''
"""
