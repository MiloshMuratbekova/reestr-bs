"""Сборка портрета лица из витрин.

Шестнадцать запросов идут одновременно, каждый в свою витрину, и ответ
складывается по блокам. Ни один запрос не зависит от другого — это сделано
намеренно: витрины живут своей жизнью, и недоступность одной не должна
оставлять аналитика вообще без справки.

Чего здесь нет
--------------
Ни одной записи в базу: доступ только на чтение. Витрины не создаются
и не изменяются, разрешение имён идёт по системному словарю.

Про имена витрин
----------------
Часть витрин лежит в базе по умолчанию, часть — в pfr_dashboard, и на разных
стендах это различается. Поэтому имя из настроек проверяется по словарю,
а не принимается на веру: не найдя таблицу, служба пробует то же имя
в соседней базе, а не найдя и там — пропускает блок. Пропуск виден в ответе,
чтобы пустой блок не сошёл за «сведений нет».
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.algorithms import portrait_sql as ps
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse

logger = get_logger(__name__)

#: Где искать витрину, если по имени из настроек её нет
FALLBACK_DATABASES = ("pfr_dashboard", "figurant")

#: Найденные имена витрин. Состав баз за время работы не меняется,
#: а спрашивать словарь на каждую справку ни к чему.
_resolved: Dict[str, Optional[str]] = {}


async def _resolve(name: str) -> Optional[str]:
    """Полное имя витрины, если она существует, иначе None."""
    if name in _resolved:
        return _resolved[name]

    candidates: List[str] = []
    if "." in name:
        candidates.append(name)
        # То же имя в базе по умолчанию — на случай, если витрину перенесли
        candidates.append(name.split(".", 1)[1])
    else:
        candidates.append(f"{settings.CLICKHOUSE_DATABASE}.{name}")
        candidates.extend(f"{db}.{name}" for db in FALLBACK_DATABASES)

    for candidate in candidates:
        if "." not in candidate:
            continue
        database, table = candidate.split(".", 1)
        try:
            if await clickhouse.table_exists(database, table):
                _resolved[name] = candidate
                return candidate
        except ClickHouseError as exc:
            logger.warning("Не удалось проверить витрину %s: %s", candidate, exc)

    logger.info("Витрина %s не найдена — блок портрета пропущен", name)
    _resolved[name] = None
    return None


async def _rows(name: str, builder, params: Dict[str, Any]) -> Tuple[List[Dict], bool]:
    """Строки одной витрины. Второе значение — была ли витрина доступна."""
    table = await _resolve(name)
    if not table:
        return [], False
    try:
        return await clickhouse.fetch_all(builder(table), params), True
    except ClickHouseError as exc:
        logger.warning("Витрина %s не ответила: %s", table, exc)
        return [], False


async def _risks(iin: str) -> Tuple[List[str], bool]:
    """Метки из реестров риска — только по тем, что реально существуют."""
    available = []
    for table, column, label in ps.RISK_REGISTRIES:
        database, name = table.split(".", 1)
        try:
            if await clickhouse.table_exists(database, name):
                available.append((table, column, label))
        except ClickHouseError:
            continue
    if not available:
        return [], False

    try:
        rows = await clickhouse.fetch_all(ps.build_risks_sql(tuple(available)), {"iin": iin})
    except ClickHouseError as exc:
        logger.warning("Реестры риска не опрошены: %s", exc)
        return [], False
    # Метки не взаимоисключающие: одно лицо может быть должником,
    # подозреваемым и лудоманом сразу — берутся все
    return sorted({str(r.get("label") or "") for r in rows if r.get("label")}), True


def _split_neighbours(
    rows: List[Dict[str, Any]], known: set
) -> Dict[str, List[Dict[str, Any]]]:
    """Делит жильцов на соседей по квартире и по дому.

    Если в доме двенадцать человек и больше, это многоквартирный дом: из
    соседей по дому остаются только те, кто уже проходит по реестру. Иначе
    в справку попала бы сотня фамилий, ничего не значащих. В малом доме
    соседство само по себе связь, и остаются все.
    """
    same_flat = [r for r in rows if int(r.get("same_flat") or 0)]
    same_house = [r for r in rows if not int(r.get("same_flat") or 0)]

    if len(rows) >= settings.PORTRAIT_APARTMENT_HOUSE:
        same_house = [r for r in same_house if str(r.get("iin") or "") in known]

    return {
        "same_flat": same_flat,
        "same_house": same_house,
        "is_apartment_house": len(rows) >= settings.PORTRAIT_APARTMENT_HOUSE,
    }


async def _known_people(iins: List[str]) -> set:
    """Кто из перечисленных уже проходит по реестру как бенефициар."""
    if not iins:
        return set()
    from app.services import algorithm_service

    source = await algorithm_service.merged_source()
    if not source:
        return set()
    merged, _columns = source
    try:
        rows = await clickhouse.fetch_all(
            f"""
            SELECT DISTINCT ifNull(toString(m.benefeciary_iin_bin), '') AS iin
            FROM {merged} AS m
            WHERE ifNull(toString(m.benefeciary_iin_bin), '') IN {{iins:Array(String)}}
            """,
            {"iins": iins},
        )
    except ClickHouseError as exc:
        logger.warning("Список выявленных лиц не получен: %s", exc)
        return set()
    return {str(r.get("iin") or "") for r in rows}


async def build_portrait(iin: str) -> Dict[str, Any]:
    """Портрет одного лица: всё, что о нём известно витринам.

    Возвращает блоки identity, income, assets, debts, finmon, risks, special.
    Рядом с каждым блоком лежит признак ``available``: пустой блок при
    недоступной витрине и пустой блок при отсутствии сведений — разные вещи,
    и путать их в справке нельзя.
    """
    iin = (iin or "").strip()
    if not iin:
        return {"iin": "", "blocks": {}, "note": "ИИН не указан"}

    since = (date.today() - timedelta(days=365)).isoformat()
    base = {"iin": iin}

    tasks = {
        "finmon": _rows(
            settings.PORTRAIT_FINMON, ps.build_finmon_sql,
            {**base, "lim": settings.PORTRAIT_FINMON_LIMIT},
        ),
        "pension": _rows(
            settings.PORTRAIT_PENSION, ps.build_pension_sql, {**base, "since": since}
        ),
        "salary": _rows(settings.PORTRAIT_SALARY, ps.build_salary_sql, base),
        "gov": _rows(settings.PORTRAIT_GOV, ps.build_gov_sql, base),
        "assets": _rows(settings.PORTRAIT_ASSETS, ps.build_assets_sql, base),
        "debts": _rows(settings.PORTRAIT_DEBTS, ps.build_debts_sql, base),
        "address": _rows(settings.PORTRAIT_ADDRESS, ps.build_address_sql, base),
        "neighbours": _rows(
            settings.PORTRAIT_ADDRESS, ps.build_neighbours_sql,
            {**base, "lim": settings.PORTRAIT_NEIGHBOURS_LIMIT},
        ),
        "invalid": _rows(settings.PORTRAIT_INVALID, ps.build_invalid_sql, base),
        "narco": _rows(settings.PORTRAIT_NARCO, ps.build_narco_sql, base),
        "destructive": _rows(
            settings.PORTRAIT_DESTRUCTIVE, ps.build_destructive_sql, base
        ),
        "special": _rows(settings.PORTRAIT_SPECIAL, ps.build_special_sql, base),
        "erdr": _rows(settings.PORTRAIT_ERDR, ps.build_erdr_sql, base),
    }

    # Все витрины опрашиваются одновременно: последовательно шестнадцать
    # запросов складывались бы в неприемлемое ожидание
    names = list(tasks)
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    data: Dict[str, Tuple[List[Dict], bool]] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.warning("Блок портрета %s не собран: %s", name, result)
            data[name] = ([], False)
        else:
            data[name] = result

    risk_labels, risks_available = await _risks(iin)

    neighbour_rows, neighbours_available = data["neighbours"]
    known = await _known_people(
        [str(r.get("iin") or "") for r in neighbour_rows if r.get("iin")]
    )
    neighbours = _split_neighbours(neighbour_rows, known)

    address_rows, address_available = data["address"]
    pension_rows, pension_available = data["pension"]
    salary_rows, salary_available = data["salary"]

    # Официальный доход по ОПВ: взнос делится на ставку. Считается здесь,
    # а не в запросе, потому что складывается по всем работодателям.
    income_estimate = round(
        sum(float(r.get("income_estimate") or 0) for r in pension_rows), 2
    )
    # Стипендия при крупных оборотах — прямое несоответствие, поэтому
    # признак учащегося выносится отдельно
    is_student = any(str(r.get("kind_group") or "") == "стипендия" for r in salary_rows)

    return {
        "iin": iin,
        "identity": {
            "available": address_available,
            "address": address_rows[0] if address_rows else None,
            "neighbours_available": neighbours_available,
            **neighbours,
        },
        "income": {
            "available": pension_available or salary_available,
            "pension": pension_rows,
            "pension_available": pension_available,
            "income_estimate": income_estimate,
            "salary": salary_rows,
            "salary_available": salary_available,
            "is_student": is_student,
            "government": data["gov"][0],
            "government_available": data["gov"][1],
        },
        "assets": {
            "available": data["assets"][1],
            "deals": data["assets"][0],
            # Дарение и наследование считаются отдельно: полученное в дар
            # не оплачивалось своими средствами
            "purchased_total": round(
                sum(
                    float(r.get("amount") or 0)
                    for r in data["assets"][0]
                    if not int(r.get("is_gift") or 0)
                ),
                2,
            ),
            "gifted_count": sum(
                1 for r in data["assets"][0] if int(r.get("is_gift") or 0)
            ),
        },
        "debts": {"available": data["debts"][1], "items": data["debts"][0]},
        "finmon": {
            "available": data["finmon"][1],
            "messages": data["finmon"][0],
            "total_tenge": round(
                sum(float(r.get("amount_tenge") or 0) for r in data["finmon"][0]), 2
            ),
            "suspicious_count": sum(
                1 for r in data["finmon"][0] if str(r.get("susp") or "").strip()
            ),
        },
        # Блок заполняется всегда, даже пустой: отсутствие меток — тоже сведение
        "risks": {"available": risks_available, "labels": risk_labels},
        "special": {
            "invalid": data["invalid"][0][0] if data["invalid"][0] else None,
            "invalid_available": data["invalid"][1],
            "narco": [str(r.get("risk") or "") for r in data["narco"][0]],
            "narco_available": data["narco"][1],
            "destructive": [str(r.get("flag") or "") for r in data["destructive"][0]],
            "destructive_available": data["destructive"][1],
            "special_records": data["special"][0],
            "special_available": data["special"][1],
            "erdr": data["erdr"][0],
            "erdr_available": data["erdr"][1],
        },
    }
