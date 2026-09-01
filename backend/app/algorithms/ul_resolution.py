"""Карта раскрытия юридических лиц до конечных физических.

Зачем
-----
Бенефициарный собственник по определению — физическое лицо. Часть алгоритмов
возвращает бенефициаром юридическое: акционером числится ТОО, учредителем
с долей 25 процентов — другая компания. Такое ЮЛ не ответ, а промежуточное
звено, и его надо раскрыть: у ЮЛ-А бенефициаром может оказаться ЮЛ-Б, у того
ЮЛ-В, и только дальше физическое лицо.

Два способа получить карту
--------------------------
Первый — таблицей. Она строится один раз, последним шагом пересчёта, а
реестр подставляет физлицо одним LEFT JOIN к маленькой таблице. Так и было
задумано: раскрутка на четыре уровня, записанная явными join-ами, разворачивается
внутри ClickHouse примерно в две сотни обращений к таблицам, и вставленная
в каждый запрос реестра она планировалась около сорока секунд.

Второй — подзапросом, рекурсивным обходом. Он нужен, когда учётная запись
имеет только права на чтение и создать таблицу нельзя. Тот же обход, записанный
через WITH RECURSIVE, обращается к объединению таблиц дважды вместо десяти раз,
и запрос реестра планируется за считанные секунды. Результат совпадает
с табличной картой: сверено на цепочках глубиной до четырёх.

Выбор делает :func:`app.services.algorithm_service.resolution_map_if_ready`.

Что попадает в карту
--------------------
Пары «юрлицо → его конечный бенефициар-физлицо». Побеждает физлицо, найденное
на меньшей глубине цепочки; при равной глубине — по более сильному признаку
(порядок таблиц задаёт вызывающий: сначала регистрационные алгоритмы, затем
предполагаемые).
"""

from __future__ import annotations

from typing import List

from app.core.config import settings

#: Имя таблицы с картой раскрытия
UL_RESOLUTION_TABLE = f"{settings.REGISTRY_DATABASE}.AFM_6_1_ul_map"

#: На сколько уровней раскручивается цепочка ЮЛ → ЮЛ → … → ФЛ
UL_RESOLUTION_DEPTH = 4

#: Признак юридического лица из ТЗ: пятый знак справа восьмизначной части БИН
_IS_UL = "left(right({col}, 8), 1) IN ('4', '5')"
_IS_FL = "left(right({col}, 8), 1) NOT IN ('4', '5')"


def _edges_union(tables: List[str]) -> str:
    """Пары «компания — её бенефициар» по всем алгоритмам, с рангом источника."""
    parts = []
    for rank, table in enumerate(tables, start=1):
        parts.append(
            f"""    SELECT
        ifNull(toString(o.taxpayer_iin_bin), '') AS ul,
        ifNull(toString(o.benefeciary_iin_bin), '') AS child,
        {rank} AS rank
    FROM {table} AS o
    WHERE ifNull(toString(o.taxpayer_iin_bin), '') != ''
      AND ifNull(toString(o.benefeciary_iin_bin), '') != ''"""
        )
    return "\n    UNION ALL\n".join(parts)


def _depth_selects() -> str:
    """Ветки по глубине: d1 — физлицо сразу, dN — через N-1 юрлиц."""
    blocks = [
        "    SELECT a.ul AS ul, a.child AS fl, a.rank AS rank, 1 AS depth\n"
        "    FROM edges AS a\n"
        f"    WHERE {_IS_FL.format(col='a.child')}"
    ]

    for step in range(2, UL_RESOLUTION_DEPTH + 1):
        aliases = [chr(96 + index) for index in range(1, step + 1)]
        joins = "".join(
            f"    JOIN edges AS {aliases[index]}"
            f" ON {aliases[index - 1]}.child = {aliases[index]}.ul\n"
            for index in range(1, step)
        )
        # Все звенья цепочки, кроме последнего, обязаны быть юрлицами
        chain = "\n      AND ".join(
            _IS_UL.format(col=f"{alias}.child") for alias in aliases[:-1]
        )
        last = aliases[-1]
        blocks.append(
            f"    SELECT a.ul AS ul, {last}.child AS fl,"
            f" {last}.rank AS rank, {step} AS depth\n"
            f"    FROM edges AS a\n"
            f"{joins}"
            f"    WHERE {chain}\n"
            f"      AND {_IS_FL.format(col=f'{last}.child')}\n"
            # Цепочка не должна возвращаться к исходному юрлицу
            f"      AND a.ul != {last}.child"
        )

    return "\n    UNION ALL\n".join(blocks)


def build_ul_resolution_sql(
    ranked_tables: List[str], *, target: str = UL_RESOLUTION_TABLE
) -> List[str]:
    """Операторы построения карты. Пустой список — если считать не из чего."""
    tables = [table for table in ranked_tables if table]
    if not tables:
        return []

    return [
        f"DROP TABLE IF EXISTS {target} SYNC",
        f"""CREATE TABLE {target}
ENGINE = MergeTree
ORDER BY (assumeNotNull(ul_iin_bin))
AS
WITH edges AS (
    SELECT DISTINCT s.ul AS ul, s.child AS child, s.rank AS rank
    FROM (
{_edges_union(tables)}
    ) AS s
    WHERE {_IS_UL.format(col='s.ul')}
)
SELECT
    a.ul AS ul_iin_bin,
    argMin(a.fl, (a.depth, a.rank)) AS fl_iin_bin,
    min(a.depth) AS depth
FROM (
{_depth_selects()}
) AS a
GROUP BY a.ul""",
    ]


def build_ul_map_subquery(ranked_tables: List[str]) -> str:
    """Та же карта, но подзапросом — для режима чтения, где таблицу не создать.

    Обход записан через WITH RECURSIVE: подъём по цепочке владения идёт, пока
    очередное звено остаётся юридическим лицом, но не глубже
    :data:`UL_RESOLUTION_DEPTH`. Условие ``ch.ul != e.child`` обрывает петли,
    когда компания через цепочку владеет сама собой.

    Правило выбора то же, что у табличной карты: побеждает физлицо с меньшей
    глубиной, при равной — из более сильного алгоритма (ранг источника).

    Пустая строка — если считать не из чего.
    """
    tables = [table for table in ranked_tables if table]
    if not tables:
        return ""

    return f"""(
    WITH RECURSIVE edges AS (
        SELECT DISTINCT s.ul AS ul, s.child AS child, s.rank AS rank
        FROM (
{_edges_union(tables)}
        ) AS s
        WHERE {_IS_UL.format(col='s.ul')}
    ),
    chain AS (
        SELECT e.ul AS ul, e.child AS child, e.rank AS rank, 1 AS depth
        FROM edges AS e
        UNION ALL
        SELECT ch.ul AS ul, e.child AS child, e.rank AS rank, ch.depth + 1 AS depth
        FROM chain AS ch
        JOIN edges AS e ON ch.child = e.ul
        WHERE ch.depth < {UL_RESOLUTION_DEPTH}
          AND {_IS_UL.format(col='ch.child')}
          AND ch.ul != e.child
    )
    SELECT
        ch.ul AS ul_iin_bin,
        argMin(ch.child, (ch.depth, ch.rank)) AS fl_iin_bin,
        min(ch.depth) AS depth
    FROM chain AS ch
    WHERE {_IS_FL.format(col='ch.child')}
    GROUP BY ch.ul
)"""
