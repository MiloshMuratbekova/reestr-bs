"""Цепочка косвенного владения — та, по которой работает БС-5.

Зачем
-----
БС-5 признаёт физлицо предполагаемым бенефициаром, если оно владеет компанией
косвенно: через одно или несколько юридических лиц, и накопленная доля
достигла 25 процентов. Но в таблицу результата попадает только конечное
физлицо и итоговая доля — промежуточные звенья теряются, и по карточке
не видно, откуда взялся вывод.

Здесь цепочка восстанавливается заново, по тому же справочнику учредителей
AFM_2_1_5_1 и по тем же правилам: доля каждого следующего уровня умножается
на долю предыдущего, юрлицо определяется пятым знаком справа восьмизначной
части кода, государственные компании исключаются.

Почему рекурсией
----------------
В самом алгоритме десять уровней выписаны явно — рекурсивных запросов
ClickHouse раньше не понимал. Здесь отбор идёт по одной компании, и цепочка
пишется через WITH RECURSIVE: путь собирается в массив, поэтому видно
не только конечное лицо, но и каждое звено между ним и компанией.
Повтор узла в пути обрывает обход — иначе кольцевое владение зациклило бы
запрос.

Требуется ClickHouse 24.4 или новее. Поддержка проверяется заранее,
см. ``algorithm_service.supports_recursive_cte``.
"""

from __future__ import annotations

from app.core.config import settings

#: Признак юрлица из ТЗ: пятый знак справа восьмизначной части кода
IS_UL = "left(right({col}, 8), 1) IN ('4', '5')"

#: На сколько уровней раскручивается цепочка — столько же, сколько в БС-5
MAX_DEPTH = 10

#: Доля, начиная с которой косвенное владение считается значимым
MIN_SHARE = 25.0


def build_ownership_chain_sql() -> str:
    """Цепочки от компании до физических лиц, с долей на каждом шаге.

    Параметры запроса: ``bin`` — БИН компании. Возвращает по строке на путь:
    массив звеньев, массив долей по шагам, накопленную долю и глубину.
    """
    return f"""
WITH RECURSIVE founders AS (
    SELECT
        ifNull(toString(f.taxpayer_iin_bin), '') AS company,
        ifNull(toString(f.founder_iin_bin), '') AS founder,
        toFloat64OrZero(replaceAll(replaceAll(
            ifNull(toString(f.share_percentage), '0'), ',', '.'), '%', '')) AS share
    FROM {settings.TBL_FOUNDERS} AS f
    WHERE f.`_actual_date` = (
              SELECT max(`_actual_date`) FROM {settings.TBL_FOUNDERS}
          )
      AND ifNull(toString(f.taxpayer_iin_bin), '') != ''
      AND ifNull(toString(f.founder_iin_bin), '') != ''
      AND ifNull(toString(f.taxpayer_iin_bin), '') != ifNull(toString(f.founder_iin_bin), '')
      -- Государственная собственность из расчёта исключается, как и в БС-5
      AND ifNull(toString(f.taxpayer_iin_bin), '') NOT IN (
          SELECT DISTINCT ifNull(toString(o.taxpayer_iin_bin), '')
          FROM {settings.DICT_OWNERSHIP} AS o
          WHERE o.ownership_type LIKE '%Государственная%'
            AND o.`_actual_date` = (
                    SELECT max(`_actual_date`) FROM {settings.DICT_OWNERSHIP}
                )
      )
),
chain AS (
    SELECT
        f.founder AS node,
        [f.company, f.founder] AS path,
        [f.share] AS shares,
        f.share AS acc_share,
        1 AS depth
    FROM founders AS f
    WHERE f.company = {{bin:String}}

    UNION ALL

    SELECT
        f.founder AS node,
        arrayPushBack(c.path, f.founder) AS path,
        arrayPushBack(c.shares, f.share) AS shares,
        c.acc_share * f.share / 100.0 AS acc_share,
        c.depth + 1 AS depth
    FROM chain AS c
    JOIN founders AS f ON c.node = f.company
    WHERE c.depth < {MAX_DEPTH}
      -- Дальше идём только через юрлица: физлицо — конец цепочки
      AND {IS_UL.format(col='c.node')}
      -- Узел, уже встречавшийся в пути, обрывает обход: кольцевое
      -- владение иначе крутилось бы до предела глубины
      AND NOT has(c.path, f.founder)
)
SELECT
    c.path AS path,
    arrayMap(x -> round(x, 2), c.shares) AS shares,
    round(c.acc_share, 2) AS acc_share,
    c.depth AS depth,
    NOT ({IS_UL.format(col='c.node')}) AS ends_with_person,
    c.acc_share >= {MIN_SHARE} AS meets_threshold
FROM chain AS c
ORDER BY c.acc_share DESC, c.depth ASC
LIMIT {{lim:UInt32}}
""".strip()


def build_chain_names_sql() -> str:
    """Наименования и ФИО для звеньев цепочки, по их кодам.

    Юрлица берутся из справочника организаций, физлица — из справочника
    физических лиц. Что не нашлось, останется без имени: подставлять сюда
    разбор строк ни к чему, звенья — это всегда настоящие коды.
    """
    return f"""
SELECT iin, any(name) AS name
FROM (
    SELECT
        ifNull(toString(c.taxpayer_iin_bin), '') AS iin,
        ifNull(toString(c.taxpayer_name), '') AS name
    FROM {settings.DICT_COMPANIES} AS c
    WHERE ifNull(toString(c.taxpayer_iin_bin), '') IN {{codes:Array(String)}}
      AND ifNull(toString(c.taxpayer_name), '') != ''

    UNION ALL

    SELECT
        ifNull(toString(p.taxpayer_iin_bin), '') AS iin,
        ifNull(toString(p.taxpayer_name), '') AS name
    FROM {settings.DICT_PERSONS} AS p
    WHERE ifNull(toString(p.taxpayer_iin_bin), '') IN {{codes:Array(String)}}
      AND ifNull(toString(p.taxpayer_name), '') != ''
)
GROUP BY iin
""".strip()
