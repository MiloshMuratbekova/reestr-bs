"""Портрет лица: запросы к витринам по одному ИИН.

Каждая функция строит один запрос к одной витрине. Служба
:mod:`app.services.portrait_service` пускает их одновременно и собирает
ответ по блокам, поэтому здесь нет ни общего union, ни зависимостей между
запросами: недоступность одной витрины не должна ронять остальные.

Правила, общие для всех витрин
------------------------------
ИИН всюду приводится к строке. Без этого теряется ведущий ноль, и
сопоставление между источниками перестаёт сходиться — у части витрин ИИН
объявлен числом.

Имена колонок в источниках записаны по-разному: ``iin``, ``IIN``,
``iin_bin``, а в одной витрине — ``"IIN ANALIZIRUEMYI"``, с пробелом внутри
имени, из-за чего его обязательно брать в двойные кавычки.

Все значения подставляются параметрами запроса, а не текстом: сюда приходит
ввод пользователя.
"""

from __future__ import annotations

from typing import List, Tuple

from app.core.config import settings

#: Роли, в которых лицо может встретиться в сообщении финмониторинга.
#: У каждой роли свой набор колонок с одинаковым префиксом.
FINMON_ROLES = (
    ("SELLER", "продавец / отправитель"),
    ("CUSTOMER", "покупатель / получатель"),
    ("MEMBER", "участник"),
    ("BENEFICIARY", "бенефициар"),
    ("BEHALF_PERSON", "лицо, от имени которого совершается операция"),
    ("SELLER_REPRESENTATIVE", "представитель продавца"),
    ("CUSTOMER_REPRESENTATIVE", "представитель покупателя"),
    ("INSURED", "застрахованный"),
)

#: Роли, для которых второй стороной выступает продавец. Для всех
#: остальных ролей контрагентом считается покупатель.
FINMON_SELLER_SIDE = ("CUSTOMER", "CUSTOMER_REPRESENTATIVE")

#: Виды выплат из ФНО 200.05 и их укрупнённые группы.
#: Группа важнее суммы: трудовой доход обороты объясняет, а стипендия при
#: миллионных оборотах — наоборот, прямое несоответствие.
SALARY_KINDS = {
    1: ("Доход работника (зарплата)", "трудовой"),
    2: ("Доход по договору ГПХ", "трудовой"),
    3: ("Выигрыш", "разовый"),
    4: ("Пенсионные выплаты", "пенсия"),
    5: ("Вознаграждение по операциям репо", "пассивный"),
    6: ("Доход в виде вознаграждений", "пассивный"),
    7: ("Дивиденды", "пассивный"),
    8: ("Стипендия", "стипендия"),
    9: ("Доход по договору накопительного страхования", "пассивный"),
    10: ("Доход от личного подсобного хозяйства", "прочий"),
    11: ("Прочий облагаемый доход у источника выплаты", "прочий"),
}

#: Ставка обязательных пенсионных взносов. По ней взнос пересчитывается
#: в оценку официального дохода.
PENSION_RATE = 0.10

#: Реестры риска: таблица, колонка с ИИН, метка. Устроены одинаково —
#: попадание в список и есть метка. Колонка называется по-разному,
#: поэтому имя хранится рядом с таблицей.
RISK_REGISTRIES: Tuple[Tuple[str, str, str], ...] = (
    ("pfr_dashboard.kuis_03_2026", "iin", "Сиделец"),
    ("pfr_dashboard.spisok_samoogranichennyh", "iin", "Самоограничение"),
    ("pfr_dashboard.pod_strazhey", "iin", "Под стражей"),
    ("pfr_dashboard.podozrevayemye", "iin", "Подозреваемый"),
    ('pfr_dashboard.kpsisu', '"IIN ANALIZIRUEMYI"', "В розыске"),
    ("pfr_dashboard.dolzhniki", "iin_bin", "Должник"),
    ("pfr_dashboard.invalid", "iin", "Инвалид"),
    ("pfr_dashboard.pdl_2", "iin", "ПДЛ"),
    ("pfr_dashboard.forbes_kz", "IIN", "ФОРБС"),
    ("pfr_dashboard.ludomany", "IIN", "Лудоман"),
    ("pfr_dashboard.erdr", "iin", "ЕРДР"),
)

#: Признаки того, что актив получен даром, а не куплен. Полученное в дар
#: не оплачивалось своими средствами, и в вывод о несоответствии доходу
#: оно идти не должно.
GIFT_MARKS = ("дарен", "в дар", "наслед", "завещан")


def _text(column: str) -> str:
    """Колонка как непустая строка: витрины полны Nullable-полей."""
    return f"ifNull(toString({column}), '')"


# ---------------------------------------------------------------------------
# Финансовый мониторинг
# ---------------------------------------------------------------------------
def build_finmon_sql(table: str) -> str:
    """Сообщения финмониторинга, где лицо встречается в любой из восьми ролей.

    Колонок ``opisanie`` и ``dopinfo`` в этой витрине нет — обращение к ним
    роняло запрос целиком, поэтому их здесь и не должно появиться.
    """
    branches: List[str] = []
    for role, title in FINMON_ROLES:
        side = "SELLER" if role in FINMON_SELLER_SIDE else "CUSTOMER"
        branches.append(f"""    SELECT
        '{title}' AS role,
        {_text('a.MESS_ID')} AS mess_id,
        {_text('a.DATE_OPER')} AS date_oper,
        toFloat64OrZero({_text('a.OPER_TENGE_AMOUNT')}) AS amount_tenge,
        {_text('a.OPER_CURRENCY_CODE')} AS currency_code,
        toFloat64OrZero({_text('a.OPER_CURRENCY_AMOUNT')}) AS amount_currency,
        {_text('a.OPER_NAMETYPE')} AS oper_kind,
        {_text('a.OPER_SUSP')} AS susp,
        {_text('a.OPER_SUSP_FIRST')} AS susp_first,
        {_text('a.OPER_SUSP_SECOND')} AS susp_second,
        {_text('a.MESS_OPER_STATUS')} AS status,
        {_text('a.CFM_NAME')} AS cfm_name,
        {_text(f'a.{role}_UR_NAME')} AS participant_name,
        {_text(f'a.{side}_UR_NAME')} AS counterparty_name,
        {_text(f'a.{side}_MAINCODE')} AS counterparty_iin,
        {_text(f'a.{side}_COUNTRY_RESIDENCE')} AS counterparty_country,
        {_text(f'a.{side}_BANK_COUNTRY')} AS counterparty_bank_country,
        {_text(f'a.{side}_BANK_ACCOUNT')} AS counterparty_account
    FROM {table} AS a
    WHERE {_text(f'a.{role}_MAINCODE')} = {{iin:String}}""")

    union = "\n    UNION ALL\n".join(branches)
    return f"""
SELECT *
FROM (
{union}
)
ORDER BY date_oper DESC
LIMIT {{lim:UInt32}}
""".strip()


# ---------------------------------------------------------------------------
# Доходы
# ---------------------------------------------------------------------------
def build_pension_sql(table: str) -> str:
    """Пенсионные взносы по работодателям.

    Группировка по лицу И работодателю: за год человек мог сменить несколько
    мест работы, и в справке важно видеть каждое.

    Официальный доход оценивается как взнос, делённый на ставку ОПВ.
    """
    return f"""
SELECT
    {_text('p.P_NAME')} AS employer,
    count() AS payments,
    min({_text('p.PAY_DATE')}) AS first_payment,
    max({_text('p.PAY_DATE')}) AS last_payment,
    round(sum(toFloat64OrZero({_text('p.AMOUNT')})), 2) AS total_amount,
    round(sum(toFloat64OrZero({_text('p.AMOUNT')})) / {PENSION_RATE}, 2) AS income_estimate,
    countIf({_text('p.PAY_DATE')} >= {{since:String}}) AS payments_12m,
    round(sumIf(toFloat64OrZero({_text('p.AMOUNT')}),
        {_text('p.PAY_DATE')} >= {{since:String}}), 2) AS amount_12m
FROM {table} AS p
WHERE {_text('p.IIN')} = {{iin:String}}
GROUP BY employer
ORDER BY last_payment DESC
""".strip()


def build_salary_sql(table: str) -> str:
    """Выплаты по налоговой отчётности ФНО 200.05, с группой вида выплаты."""
    kinds = ", ".join(
        f"{code}, '{name}'" for code, (name, _group) in SALARY_KINDS.items()
    )
    groups = ", ".join(
        f"{code}, '{group}'" for code, (_name, group) in SALARY_KINDS.items()
    )
    return f"""
SELECT
    {_text('f.iin_bin')} AS employer_bin,
    toInt32OrZero({_text('f.period_year')}) AS year,
    toInt32OrZero({_text('f.period_quarter')}) AS quarter,
    toInt32OrZero({_text('f.field_200_05_D')}) AS kind_code,
    transform(toInt32OrZero({_text('f.field_200_05_D')}),
        [{", ".join(str(c) for c in SALARY_KINDS)}],
        [{", ".join(repr(v[0]).replace(chr(34), chr(39)) for v in SALARY_KINDS.values())}],
        'Неизвестный вид') AS kind_name,
    transform(toInt32OrZero({_text('f.field_200_05_D')}),
        [{", ".join(str(c) for c in SALARY_KINDS)}],
        [{", ".join(repr(v[1]).replace(chr(34), chr(39)) for v in SALARY_KINDS.values())}],
        'прочий') AS kind_group,
    round(sum(toFloat64OrZero({_text('f.field_200_05_H')})), 2) AS gross,
    round(sum(toFloat64OrZero({_text('f.field_200_05_S')})), 2) AS net
FROM {table} AS f
WHERE {_text('f.field_200_05_C')} = {{iin:String}}
GROUP BY employer_bin, year, quarter, kind_code, kind_name, kind_group
ORDER BY year DESC, quarter DESC
""".strip()


def build_gov_sql(table: str) -> str:
    """Числится ли лицо работником государственного органа."""
    return f"""
SELECT DISTINCT
    {_text('g.P_NAME')} AS organ,
    {_text('g.P_RNN')} AS organ_rnn
FROM {table} AS g
WHERE {_text('g.IIN')} = {{iin:String}}
""".strip()


# ---------------------------------------------------------------------------
# Активы
# ---------------------------------------------------------------------------
def build_assets_sql(table: str) -> str:
    """Сделки с активами: лицо как участник, покупатель или продавец.

    Ветка участника исключает строки, где лицо и так покупатель или
    продавец, иначе одна сделка посчиталась бы дважды.

    Дарение и наследование отделяются от покупки по маркерам в тексте:
    полученное в дар не оплачивалось своими средствами.
    """
    gift = " OR ".join(
        f"positionCaseInsensitive(concat({_text('t.oper')}, ' ', {_text('t.dopinfo')}),"
        f" '{mark}') > 0"
        for mark in GIFT_MARKS
    )
    fields = f"""        {_text('t.aktivy')} AS asset,
        {_text('t.oper')} AS oper,
        {_text('t.num_doc')} AS doc_number,
        {_text('t.dopinfo')} AS dop_info,
        {_text('t.database')} AS source,
        {_text('t.date')} AS date,
        round(toFloat64OrZero({_text('t.summ')}), 2) AS amount,
        ({gift}) AS is_gift"""

    return f"""
SELECT *
FROM (
    SELECT 'участник' AS role,
{fields}
    FROM {table} AS t
    WHERE {_text('t.iin_bin')} = {{iin:String}}
      AND {_text('t.iin_bin_pokup')} != {{iin:String}}
      AND {_text('t.iin_bin_prod')} != {{iin:String}}

    UNION ALL

    SELECT 'покупатель' AS role,
{fields}
    FROM {table} AS t
    WHERE {_text('t.iin_bin_pokup')} = {{iin:String}}

    UNION ALL

    SELECT 'продавец' AS role,
{fields}
    FROM {table} AS t
    WHERE {_text('t.iin_bin_prod')} = {{iin:String}}
)
ORDER BY date DESC
""".strip()


# ---------------------------------------------------------------------------
# Долги
# ---------------------------------------------------------------------------
def build_debts_sql(table: str) -> str:
    """Исполнительные производства, по которым человек должен до сих пор."""
    return f"""
SELECT
    {_text('d.fio_dolz')} AS debtor_name,
    {_text('d.vzyskatel')} AS creditor,
    round(toFloat64OrZero({_text('d.summ')}), 2) AS amount,
    {_text('d.kategoria')} AS category,
    {_text('d.date_ip_start')} AS started_at,
    {_text('d.number_ip')} AS number,
    {_text('d.organ_vid_ispolnitelny_dok')} AS organ,
    {_text('d.date_zapreta_vezd')} AS travel_ban_date,
    {_text('d.status')} AS status
FROM {table} AS d
WHERE {_text('d.iin_bin')} = {{iin:String}}
  AND positionCaseInsensitive({_text('d.status')}, 'на исполнении') > 0
ORDER BY started_at DESC
""".strip()


# ---------------------------------------------------------------------------
# Адрес и соседи
# ---------------------------------------------------------------------------
def build_address_sql(table: str) -> str:
    """Адрес регистрации лица."""
    return f"""
SELECT DISTINCT
    {_text('m.strana')} AS country,
    {_text('m.oblast')} AS region,
    {_text('m.gorod')} AS city,
    {_text('m.rayon')} AS district,
    {_text('m.mikro_rayon')} AS micro_district,
    {_text('m.dom')} AS house,
    {_text('m.podezd')} AS entrance,
    {_text('m.kvartira')} AS flat
FROM {table} AS m
WHERE {_text('m.iin')} = {{iin:String}}
""".strip()


def build_neighbours_sql(table: str) -> str:
    """Кто ещё прописан по тому же адресу.

    Совпадение проверяется по области, городу, району, микрорайону и дому.
    Адреса без цифры в номере дома отбрасываются: без номера это уже
    микрорайон целиком, и совпадение по нему пустое.
    """
    return f"""
WITH mine AS (
    SELECT
        {_text('m.oblast')} AS region,
        {_text('m.gorod')} AS city,
        {_text('m.rayon')} AS district,
        {_text('m.mikro_rayon')} AS micro_district,
        {_text('m.dom')} AS house,
        {_text('m.kvartira')} AS flat
    FROM {table} AS m
    WHERE {_text('m.iin')} = {{iin:String}}
      AND match({_text('m.dom')}, '[0-9]')
    LIMIT 1
)
SELECT
    {_text('n.iin')} AS iin,
    {_text('n.kvartira')} AS flat,
    {_text('n.dom')} AS house,
    -- Та же квартира — прямое соседство; тот же дом — соседство слабее
    {_text('n.kvartira')} = (SELECT flat FROM mine) AS same_flat
FROM {table} AS n
WHERE {_text('n.iin')} != {{iin:String}}
  AND {_text('n.iin')} != ''
  AND {_text('n.oblast')} = (SELECT region FROM mine)
  AND {_text('n.gorod')} = (SELECT city FROM mine)
  AND {_text('n.rayon')} = (SELECT district FROM mine)
  AND {_text('n.mikro_rayon')} = (SELECT micro_district FROM mine)
  AND {_text('n.dom')} = (SELECT house FROM mine)
GROUP BY iin, flat, house, same_flat
LIMIT {{lim:UInt32}}
""".strip()


# ---------------------------------------------------------------------------
# Особые учёты
# ---------------------------------------------------------------------------
def build_invalid_sql(table: str) -> str:
    """Инвалидность и социальные выплаты — последняя запись по лицу.

    В витрине копится история, поэтому по каждому полю берётся значение
    с наибольшей датой актуальности.
    """
    fields = (
        ("fio", "fio"),
        ("region", "region"),
        ("gruppa_invalidnosti", "group_name"),
        ("stepen_utraty_trudosposobnosty", "capacity_loss"),
        ("prichina_ustanovlenye_invalidnosty", "reason"),
        ("srok_ustanovlenye_invalidnosty", "term"),
        ("data_pervichnogo_ustanovlenye_invalidnosty", "first_established"),
        ("summa_ezhemesechnih_soc_viplaty", "monthly_payment"),
        ("naimenovanye_soc_viplaty", "payment_name"),
        ("svedenya_soc_podderji_obsh_summa", "support_total"),
        ("svedenya_soc_podderji_vid_pomoshi_kolichestvo", "support_kinds"),
    )
    columns = ",\n".join(
        f"    argMax({_text('i.' + source)}, {_text('i.actual_date')}) AS {alias}"
        for source, alias in fields
    )
    return f"""
SELECT
{columns},
    max({_text('i.actual_date')}) AS actual_date
FROM {table} AS i
WHERE {_text('i.iin')} = {{iin:String}}
""".strip()


def build_narco_sql(table: str) -> str:
    """Учёт по наркотикам: категория риска."""
    return f"""
SELECT DISTINCT {_text('n.risk')} AS risk
FROM {table} AS n
WHERE {_text('n.iin')} = {{iin:String}}
""".strip()


def build_destructive_sql(table: str) -> str:
    """Учёт по деструктивным течениям: признак."""
    return f"""
SELECT DISTINCT {_text('d.flag')} AS flag
FROM {table} AS d
WHERE {_text('d.iin')} = {{iin:String}}
""".strip()


def build_special_sql(table: str) -> str:
    """Спецучёт. Витрина лежит в отдельной базе, имя пишется целиком."""
    return f"""
SELECT DISTINCT
    {_text('s.region')} AS region,
    {_text('s.code')} AS code,
    {_text('s.disease_name')} AS name,
    {_text('s.class_block')} AS class_block,
    {_text('s.status')} AS status,
    {_text('s.medorg')} AS medorg
FROM {table} AS s
WHERE {_text('s.iin')} = {{iin:String}}
""".strip()


# ---------------------------------------------------------------------------
# Реестры риска
# ---------------------------------------------------------------------------
def build_risks_sql(registries: Tuple[Tuple[str, str, str], ...]) -> str:
    """Метки из реестров риска одним объединённым запросом.

    Метки не взаимоисключающие: одно лицо может быть должником,
    подозреваемым и лудоманом сразу, поэтому берутся все.
    """
    if not registries:
        return ""
    parts = [
        f"    SELECT '{label}' AS label FROM {table} AS r"
        f" WHERE {_text(f'r.{column}' if not column.startswith(chr(34)) else 'r.' + column)}"
        f" = {{iin:String}} LIMIT 1"
        for table, column, label in registries
    ]
    return "\n    UNION ALL\n".join(parts)


def build_erdr_sql(table: str) -> str:
    """Дела досудебного расследования: статья и дата, а не только факт.

    Экономическая статья десятилетней давности и свежее дело по отмыванию —
    разный вес, поэтому в карточку идёт содержание.
    """
    return f"""
SELECT
    {_text('e.date_registration')} AS registered_at,
    {_text('e.kvalifikacya')} AS qualification,
    {_text('e.opisanye_prestuplenya')} AS description
FROM {table} AS e
WHERE {_text('e.iin')} = {{iin:String}}
ORDER BY registered_at DESC
""".strip()


#: Метки риска, по которым можно отбирать списки. Ключ приходит из запроса,
#: поэтому в SQL подставляется не он, а заранее известное имя таблицы.
RISK_FILTERS = {
    "erdr": ("ЕРДР", "pfr_dashboard.erdr", "iin"),
    "invalid": ("Инвалид", "pfr_dashboard.invalid", "iin"),
    "debtor": ("Должник", "pfr_dashboard.dolzhniki", "iin_bin"),
    "pdl": ("ПДЛ", "pfr_dashboard.pdl_2", "iin"),
    "ludoman": ("Лудоман", "pfr_dashboard.ludomany", "IIN"),
    "forbes": ("ФОРБС", "pfr_dashboard.forbes_kz", "IIN"),
    "wanted": ("В розыске", "pfr_dashboard.kpsisu", '"IIN ANALIZIRUEMYI"'),
    "suspect": ("Подозреваемый", "pfr_dashboard.podozrevayemye", "iin"),
    "custody": ("Под стражей", "pfr_dashboard.pod_strazhey", "iin"),
    "prisoner": ("Сиделец", "pfr_dashboard.kuis_03_2026", "iin"),
    "selflimit": ("Самоограничение", "pfr_dashboard.spisok_samoogranichennyh", "iin"),
}


def build_risk_iins_sql(keys: List[str]) -> str:
    """Подзапрос: ИИН всех лиц, попавших хотя бы в один из реестров.

    Возвращает пустую строку, если ключи не заданы или незнакомы — тогда
    отбор просто не применяется. Имена таблиц берутся из словаря выше,
    ввод пользователя в SQL не попадает.
    """
    parts = [
        f"SELECT {_text('r.' + RISK_FILTERS[key][2])} AS iin"
        f" FROM {RISK_FILTERS[key][1]} AS r"
        for key in keys
        if key in RISK_FILTERS
    ]
    return "\n    UNION ALL\n    ".join(parts)
