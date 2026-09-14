"""Разбор отбора по меткам риска прямо на рабочем сервере.

Контур закрытый, база разработчику недоступна, и причину отказа иначе
видно только в логах. Этот маршрут повторяет весь путь отбора по каждому
реестру и возвращает то, что обычно теряется: нашлась ли таблица, какая
в ней колонка с ИИН, сколько строк и какая именно ошибка пришла из
ClickHouse — дословно, без обобщений вроде «не удалось получить список».
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from app.algorithms import direct_sql
from app.algorithms.portrait_sql import RISK_FILTERS, build_risk_iins_sql
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse
from app.services import algorithm_service, portrait_service

logger = get_logger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["Служебное"])


async def _probe(key: str) -> Dict[str, Any]:
    """Полная проверка одного реестра: от поиска таблицы до отбора."""
    label, table, column = RISK_FILTERS[key]
    report: Dict[str, Any] = {
        "ключ": key,
        "метка": label,
        "таблица_по_описанию": table,
        "колонка_по_описанию": column,
    }

    database, name = table.split(".", 1)

    # 1. Видна ли таблица этой учётной записи
    try:
        report["таблица_видна"] = await clickhouse.table_exists(database, name)
    except ClickHouseError as exc:
        report["таблица_видна"] = False
        report["ошибка_поиска_таблицы"] = str(exc)
        return report

    # 2. Какие колонки в ней видны
    try:
        columns = await clickhouse.table_columns(database, name)
        report["колонки"] = sorted(columns)
    except ClickHouseError as exc:
        report["ошибка_чтения_колонок"] = str(exc)
        return report

    # 3. Что из этого выбрал отбор
    usable = await portrait_service.available_risk_keys([key])
    report["метка_годна"] = key in usable
    sources = portrait_service.risk_sources(usable)
    if key in sources:
        report["таблица_найдена"] = sources[key][0]
        report["колонка_найдена"] = sources[key][1]

    # 4. Читается ли сам реестр
    try:
        report["строк_в_реестре"] = await clickhouse.table_row_count(database, name)
    except ClickHouseError as exc:
        report["ошибка_чтения_реестра"] = str(exc)

    if not report.get("метка_годна"):
        return report

    # 5. Отрабатывает ли подзапрос отбора сам по себе
    inner = build_risk_iins_sql([key], sources)
    try:
        rows = await clickhouse.fetch_all(
            "SELECT count() AS cnt FROM (" + inner + ") AS s", {}
        )
        report["иин_в_подзапросе"] = int(rows[0].get("cnt") or 0) if rows else 0
    except ClickHouseError as exc:
        report["ошибка_подзапроса"] = str(exc)

    # 6. И, наконец, оба списка целиком — ровно те запросы, что шлёт интерфейс
    source = await algorithm_service.merged_source()
    if not source:
        report["сводная_таблица"] = "не найдена"
        return report

    merged, columns_list = source
    report["сводная_таблица"] = merged

    try:
        sql = direct_sql.build_companies_list_sql(
            merged,
            columns_list,
            conditions=[
                "1",
                direct_sql.risk_condition_by_beneficiary([key], "d.taxpayer_key", sources),
            ],
            sort="priority",
            order="asc",
            limit=1,
            offset=0,
        )
        await clickhouse.fetch_all(sql, {})
        report["список_юл"] = "работает"
    except ClickHouseError as exc:
        report["список_юл"] = "ОШИБКА"
        report["ошибка_списка_юл"] = str(exc)

    try:
        sql = direct_sql.build_beneficiaries_list_sql(
            merged,
            columns_list,
            conditions=["1", direct_sql.risk_condition([key], "r.benefeciary_iin_bin", sources)],
            sort="priority",
            order="asc",
            limit=1,
            offset=0,
        )
        await clickhouse.fetch_all(sql, {})
        report["список_бс"] = "работает"
    except ClickHouseError as exc:
        report["список_бс"] = "ОШИБКА"
        report["ошибка_списка_бс"] = str(exc)

    return report


@router.get("/risk", summary="Почему не работает отбор по меткам риска")
async def risk_diagnostics() -> Dict[str, Any]:
    """Проверяет все одиннадцать реестров и возвращает дословные ошибки."""
    registries: List[Dict[str, Any]] = []
    for key in RISK_FILTERS:
        try:
            registries.append(await _probe(key))
        except Exception as exc:  # noqa: BLE001 — диагностика не должна падать сама
            registries.append({"ключ": key, "непредвиденная_ошибка": repr(exc)})

    # Учётная запись может видеть одну базу и не видеть другую — здесь
    # видно сразу, что именно ей доступно
    try:
        rows = await clickhouse.fetch_all(
            "SELECT name FROM system.databases ORDER BY name", {}
        )
        databases = [r["name"] for r in rows]
    except ClickHouseError as exc:
        databases = [f"не прочитаны: {exc}"]

    return {
        "версия_системы": settings.APP_VERSION,
        "база_по_умолчанию": settings.CLICKHOUSE_DATABASE,
        "видимые_базы": databases,
        "реестры": registries,
    }
