"""Реестр БС: поиск компаний, карточка компании, статистика.

Итоговый реестр не материализуется — он рассчитывается запросом к ClickHouse
при каждом обращении, поверх таблиц результатов алгоритмов.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.registry_sql import (
    build_company_summary_sql,
    build_registry_sql,
    build_stats_by_algorithm_sql,
    build_stats_sql,
)
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse
from app.services import algorithm_service
from app.services.settings_service import clamp_rows, runtime

logger = get_logger(__name__)

#: Определяется один раз на старте: в ТЗ поле category берётся из AFM_2_1_8,
#: но в словаре таблиц оно описано у AFM_2_1_9. Смотрим, где оно есть на самом деле.
_category_source: str = "ownership"


async def detect_category_source() -> str:
    """Выясняет, в какой таблице реально лежит поле category."""
    global _category_source
    database, table = settings.DICT_OWNERSHIP.split(".", 1)
    try:
        has_category = await clickhouse.fetch_value(
            "SELECT count() FROM system.columns "
            "WHERE database = {db:String} AND table = {tbl:String} AND name = 'category'",
            {"db": database, "tbl": table},
            default=0,
        )
        _category_source = "ownership" if int(has_category or 0) > 0 else "company"
    except ClickHouseError as exc:
        logger.warning("Не удалось определить источник поля category: %s", exc)
        _category_source = "company"

    logger.info(
        "Поле category берётся из %s",
        settings.DICT_OWNERSHIP if _category_source == "ownership" else settings.DICT_COMPANIES,
    )
    return _category_source


def category_source() -> str:
    """Определённый на старте источник поля category — нужен другим сервисам."""
    return _category_source


def is_state_owned(ownership_type: Optional[str]) -> bool:
    """Государственная компания — по признаку из AFM_2_1_8.

    Для таких компаний БС не отображаются, вместо списка выводится предупреждение.
    """
    return bool(ownership_type) and "Государственная" in ownership_type


def sort_beneficiaries(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Сначала регистрационные (priority 0), затем предполагаемые по убыванию ball3."""
    return sorted(
        rows,
        key=lambda row: (
            0 if int(row.get("priority") or 0) == 0 else 1,
            -float(row.get("ball3") or 0),
            str(row.get("benefeciary_name") or ""),
        ),
    )


# ---------------------------------------------------------------------------
# Компания
# ---------------------------------------------------------------------------
async def get_company_info(bin_value: str) -> Optional[Dict[str, Any]]:
    """Реквизиты компании из AFM_2_1_9 и тип собственности из AFM_2_1_8."""
    # Все текстовые поля приводятся к непустой строке: справочники содержат
    # Nullable-колонки, а интерфейс ожидает строку и показывает прочерк сам.
    company = await clickhouse.fetch_one(
        f"""
        SELECT
            toString(c.taxpayer_iin_bin) AS taxpayer_iin_bin,
            ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
            ifNull(toString(any(c.category)), '') AS category,
            ifNull(toString(any(c.reg_start_date)), '') AS reg_start_date,
            ifNull(toString(any(c.address)), '') AS address,
            ifNull(toString(any(c.code_nd)), '') AS code_nd
        FROM {settings.DICT_COMPANIES} AS c
        WHERE c.taxpayer_iin_bin = {{bin:String}}
        GROUP BY c.taxpayer_iin_bin
        """,
        {"bin": bin_value},
    )
    if not company:
        return None

    ownership = await clickhouse.fetch_one(
        f"""
        SELECT ifNull(toString(o.ownership_type), '') AS ownership_type
        FROM {settings.DICT_OWNERSHIP} AS o
        WHERE o.taxpayer_iin_bin = {{bin:String}}
        ORDER BY o.`_actual_date` DESC
        LIMIT 1
        """,
        {"bin": bin_value},
    )
    ownership_type = (ownership or {}).get("ownership_type", "") or ""

    company["ownership_type"] = ownership_type
    company["is_state_owned"] = is_state_owned(ownership_type)
    return company


async def get_founders(bin_value: str) -> List[Dict[str, Any]]:
    """Учредители на последнюю дату актуальности."""
    return await clickhouse.fetch_all(
        f"""
        SELECT DISTINCT
            ifNull(toString(f.founder_iin_bin), '') AS founder_iin_bin,
            ifNull(if(f.founder_ul_name = '',
               concat(f.founder_last_name, ' ', f.founder_first_name, ' ', f.founder_part_name),
               f.founder_ul_name), '') AS founder_name,
            ifNull(toString(f.share_percentage), '') AS share_percentage,
            toString(f.`_actual_date`) AS _actual_date
        FROM {settings.TBL_FOUNDERS} AS f
        WHERE f.taxpayer_iin_bin = {{bin:String}}
          AND f.`_actual_date` = (SELECT max(`_actual_date`) FROM {settings.TBL_FOUNDERS})
        ORDER BY founder_name
        """,
        {"bin": bin_value},
    )


async def get_directors(bin_value: str) -> List[Dict[str, Any]]:
    """Руководители на последнюю дату актуальности."""
    return await clickhouse.fetch_all(
        f"""
        SELECT DISTINCT
            ifNull(toString(d.employee_iin_bin), '') AS director_iin_bin,
            ifNull(concat(d.employee_last_name, ' ', d.employee_first_name, ' ', d.employee_part_name), '') AS director_name,
            toString(d.`_actual_date`) AS _actual_date
        FROM {settings.TBL_DIRECTORS} AS d
        WHERE d.taxpayer_iin_bin = {{bin:String}}
          AND d.`_actual_date` = (SELECT max(`_actual_date`) FROM {settings.TBL_DIRECTORS})
        ORDER BY director_name
        """,
        {"bin": bin_value},
    )


async def get_beneficiaries(session: AsyncSession, bin_value: str) -> List[Dict[str, Any]]:
    """Список БС компании, рассчитанный из всех активных алгоритмов."""
    tables = await algorithm_service.active_result_tables(session)
    if not tables:
        logger.warning("Нет ни одной рассчитанной таблицы алгоритмов — реестр пуст")
        return []

    # Число строк на одного клиента ограничивается настройкой и режется
    # в самом SQL, а не на стороне интерфейса
    sql = build_registry_sql(
        tables,
        company_filter="taxpayer_iin_bin = {bin:String}",
        category_source=_category_source,
        row_limit=int(runtime.get("MAX_ROWS_PER_CLIENT")),
        resolution_map=await algorithm_service.resolution_map_if_ready(),
    )
    rows = await clickhouse.fetch_all(sql, {"bin": bin_value})
    return sort_beneficiaries(rows)


async def get_company_card(session: AsyncSession, bin_value: str) -> Optional[Dict[str, Any]]:
    """Полная карточка компании."""
    company = await get_company_info(bin_value)
    if company is None:
        return None

    founders = await get_founders(bin_value)
    directors = await get_directors(bin_value)

    if company["is_state_owned"]:
        # Государственная собственность — бенефициарные собственники не отображаются
        beneficiaries: List[Dict[str, Any]] = []
        warning = (
            "Компания находится в государственной собственности. "
            "Бенефициарные собственники для таких организаций не определяются."
        )
    else:
        beneficiaries = await get_beneficiaries(session, bin_value)
        warning = None

    return {
        "company": company,
        "beneficiaries": beneficiaries,
        "founders": founders,
        "directors": directors,
        "director": directors[0] if directors else None,
        "warning": warning,
        "beneficiary_count": len(beneficiaries),
        "max_ball3": max((float(b.get("ball3") or 0) for b in beneficiaries), default=0.0),
    }


# ---------------------------------------------------------------------------
# Поиск
# ---------------------------------------------------------------------------
async def search_companies(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 50,
    status_filter: Optional[str] = None,
    algorithm_filter: Optional[str] = None,
    risk_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Поиск компаний по БИН или наименованию с показателями реестра."""
    query = (query or "").strip()
    if not query:
        return []

    # Лимит режется на сервере: значение из запроса к API может быть любым
    limit = clamp_rows(limit, 50)

    companies = await clickhouse.fetch_all(
        f"""
        SELECT
            toString(c.taxpayer_iin_bin) AS taxpayer_iin_bin,
            ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
            ifNull(toString(any(c.category)), '') AS category,
            ifNull(toString(any(c.code_nd)), '') AS code_nd,
            ifNull(toString(any(c.address)), '') AS address,
            ifNull(toString(any(c.reg_start_date)), '') AS reg_start_date
        FROM {settings.DICT_COMPANIES} AS c
        WHERE positionCaseInsensitive(c.taxpayer_iin_bin, {{q:String}}) > 0
           OR positionCaseInsensitive(toString(c.taxpayer_name), {{q:String}}) > 0
        GROUP BY c.taxpayer_iin_bin
        ORDER BY taxpayer_name
        LIMIT {{lim:UInt32}}
        """,
        {"q": query, "lim": limit},
    )
    if not companies:
        return []

    bins = [c["taxpayer_iin_bin"] for c in companies]

    ownership_rows = await clickhouse.fetch_all(
        f"""
        SELECT
            toString(o.taxpayer_iin_bin) AS taxpayer_iin_bin,
            ifNull(toString(argMax(o.ownership_type, o.`_actual_date`)), '') AS ownership_type
        FROM {settings.DICT_OWNERSHIP} AS o
        WHERE o.taxpayer_iin_bin IN {{bins:Array(String)}}
        GROUP BY o.taxpayer_iin_bin
        """,
        {"bins": bins},
    )
    ownership_map = {r["taxpayer_iin_bin"]: r.get("ownership_type", "") for r in ownership_rows}

    summary_map: Dict[str, Dict[str, Any]] = {}
    tables = await algorithm_service.active_result_tables(session)
    if tables:
        conditions = ["taxpayer_iin_bin IN {bins:Array(String)}"]
        if algorithm_filter:
            conditions.append("algorithm_code = {algo:String}")
        summary_sql = build_company_summary_sql(tables, " AND ".join(conditions))
        params: Dict[str, Any] = {"bins": bins}
        if algorithm_filter:
            params["algo"] = algorithm_filter
        try:
            for row in await clickhouse.fetch_all(summary_sql, params):
                summary_map[row["taxpayer_iin_bin"]] = row
        except ClickHouseError as exc:
            logger.error("Не удалось рассчитать сводку реестра для поиска: %s", exc)

    results: List[Dict[str, Any]] = []
    for company in companies:
        bin_value = company["taxpayer_iin_bin"]
        ownership_type = ownership_map.get(bin_value, "") or ""
        state_owned = is_state_owned(ownership_type)
        summary = summary_map.get(bin_value, {})

        # Для государственных компаний БС не показываются
        beneficiary_count = 0 if state_owned else int(summary.get("beneficiary_count") or 0)
        max_ball3 = 0.0 if state_owned else float(summary.get("max_ball3") or 0)

        results.append(
            {
                **company,
                "ownership_type": ownership_type,
                "is_state_owned": state_owned,
                "beneficiary_count": beneficiary_count,
                "max_ball3": round(max_ball3, 2),
                "region": company.get("code_nd") or "",
            }
        )

    results = _apply_filters(results, status_filter=status_filter, risk_filter=risk_filter)
    results.sort(key=lambda r: (-r["max_ball3"], r.get("taxpayer_name") or ""))
    return results


def _apply_filters(
    rows: List[Dict[str, Any]],
    *,
    status_filter: Optional[str],
    risk_filter: Optional[str],
) -> List[Dict[str, Any]]:
    filtered = rows

    if risk_filter:
        ranges = {"high": (70.0, 100.1), "medium": (40.0, 70.0), "low": (0.0, 40.0)}
        bounds = ranges.get(risk_filter)
        if bounds:
            low, high = bounds
            filtered = [r for r in filtered if low <= r["max_ball3"] < high]

    if status_filter == "state":
        filtered = [r for r in filtered if r["is_state_owned"]]
    elif status_filter == "with_bs":
        filtered = [r for r in filtered if r["beneficiary_count"] > 0]
    elif status_filter == "without_bs":
        filtered = [r for r in filtered if r["beneficiary_count"] == 0]

    return filtered


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------
async def get_stats(session: AsyncSession) -> Dict[str, Any]:
    """Общая статистика реестра."""
    tables = await algorithm_service.active_result_tables(session)
    if not tables:
        return {
            "total_rows": 0,
            "company_count": 0,
            "beneficiary_count": 0,
            "registration_count": 0,
            "assumed_count": 0,
            "nonresident_count": 0,
            "by_algorithm": [],
            "algorithms_total": 0,
            "algorithms_calculated": 0,
        }

    totals = await clickhouse.fetch_one(build_stats_sql(tables)) or {}
    by_algorithm = await clickhouse.fetch_all(build_stats_by_algorithm_sql(tables))

    algorithms = await algorithm_service.list_algorithms(session)
    hints = {a.code: a.name for a in algorithms}
    for row in by_algorithm:
        row["name"] = hints.get(row["algorithm_code"], "")

    return {
        **totals,
        "by_algorithm": by_algorithm,
        "algorithms_total": len(algorithms),
        "algorithms_calculated": len(tables),
    }
