"""Страницы списков: юридические лица, бенефициары, структуры владения, источники.

Реестр не материализуется, поэтому каждая страница — это запрос по всем
таблицам алгоритмов. Такие запросы тяжёлые, а данные меняются раз в сутки
(ночной пересчёт), поэтому результаты сводных разрезов держатся в памяти
процесса заданное время. Постраничная выборка не кешируется — она и так
ограничена лимитом строк.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import sources as sources_catalog
from app.algorithms.listing_sql import (
    BENEFICIARY_SORT_COLUMNS,
    COMPANY_SORT_COLUMNS,
    build_beneficiaries_list_sql,
    build_companies_enrich_sql,
    build_companies_list_sql,
    build_companies_of_director_sql,
    build_companies_of_founder_sql,
    build_company_names_sql,
    build_dashboard_summary_sql,
    build_founders_of_sql,
    build_person_name_sql,
    build_top_companies_sql,
    build_total_companies_sql,
)
from app.algorithms.registry_sql import build_registry_sql
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse
from app.services import algorithm_service, name_service, registry_service
from app.services.settings_service import clamp_rows, runtime

logger = get_logger(__name__)

#: Сколько держать в памяти результат сводного разреза, секунд.
#: Реестр пересчитывается ночью, поэтому пять минут никак не влияют
#: на актуальность, но снимают повторные проходы по всем алгоритмам.
CACHE_TTL_SECONDS = 300

_cache: Dict[str, Tuple[float, Any]] = {}


async def cached(key: str, producer: Callable[[], Any]) -> Any:
    """Значение из памяти процесса либо пересчёт с запоминанием."""
    now = time.monotonic()
    entry = _cache.get(key)
    if entry and now - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]

    value = await producer()
    _cache[key] = (now, value)
    return value


def drop_cache() -> None:
    """Сбрасывает кеш — вызывается после пересчёта алгоритмов."""
    _cache.clear()


def _page_bounds(page: int, limit: int) -> Tuple[int, int]:
    limit = clamp_rows(limit, 50)
    page = max(1, int(page or 1))
    return limit, (page - 1) * limit


def _risk_condition(risk: Optional[str], column: str) -> Optional[str]:
    """Условие по уровню риска: тот же диапазон, что и в цветовой шкале."""
    if risk == "high":
        return f"{column} > 70"
    if risk == "medium":
        return f"{column} >= 40 AND {column} <= 70"
    if risk == "low":
        return f"{column} < 40"
    return None


# ---------------------------------------------------------------------------
# Список юридических лиц
# ---------------------------------------------------------------------------
async def list_companies(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
    region: Optional[str] = None,
    ownership: Optional[str] = None,
    risk: Optional[str] = None,
    scope: str = "registry",
    sort: str = "max_ball3",
    order: str = "desc",
) -> Dict[str, Any]:
    """Страница списка ЮЛ.

    ``scope='registry'`` — только компании, по которым выявлены БС. Такой
    разрез считается целиком, поэтому доступны сортировка и фильтры
    по количеству БС и вероятности.

    ``scope='all'`` — все ЮЛ из справочника. Здесь страница сначала берётся
    из справочника, и только для неё считаются показатели реестра: иначе
    пришлось бы считать реестр по всему справочнику юридических лиц.
    """
    limit, offset = _page_bounds(page, limit)
    tables = await algorithm_service.active_result_tables(session)

    if scope == "all":
        return await _list_companies_from_dictionary(
            tables, limit=limit, offset=offset, query=query, region=region, sort=sort, order=order
        )

    if not tables:
        return {"items": [], "total": 0, "page": page, "limit": limit, "scope": scope}

    conditions: List[str] = []
    params: Dict[str, Any] = {}

    if query:
        conditions.append(
            "(positionCaseInsensitive(d.taxpayer_iin_bin, {q:String}) > 0"
            " OR positionCaseInsensitive(d.taxpayer_name, {q:String}) > 0)"
        )
        params["q"] = query.strip()
    if region:
        conditions.append("d.code_nd = {region:String}")
        params["region"] = region
    if ownership == "state":
        conditions.append("d.is_state_owned")
    elif ownership == "private":
        conditions.append("NOT d.is_state_owned")

    risk_condition = _risk_condition(risk, "d.max_ball3")
    if risk_condition:
        conditions.append(risk_condition)

    if sort not in COMPANY_SORT_COLUMNS:
        sort = "max_ball3"

    sql = build_companies_list_sql(
        tables, conditions=conditions, sort=sort, order=order, limit=limit, offset=offset
    )
    rows = await clickhouse.fetch_all(sql, params)

    total = int(rows[0].get("total_count") or 0) if rows else 0
    for row in rows:
        row.pop("total_count", None)
        row["region"] = row.get("code_nd") or ""
        row["max_ball3"] = round(float(row.get("max_ball3") or 0), 2)
        row["is_state_owned"] = bool(row.get("is_state_owned"))

    return {"items": rows, "total": total, "page": page, "limit": limit, "scope": "registry"}


async def _list_companies_from_dictionary(
    tables: List[str],
    *,
    limit: int,
    offset: int,
    query: Optional[str],
    region: Optional[str],
    sort: str,
    order: str,
) -> Dict[str, Any]:
    """Режим «все ЮЛ»: страница из справочника, показатели — только для неё."""
    conditions = ["1"]
    params: Dict[str, Any] = {}
    if query:
        conditions.append(
            "(positionCaseInsensitive(c.taxpayer_iin_bin, {q:String}) > 0"
            " OR positionCaseInsensitive(toString(c.taxpayer_name), {q:String}) > 0)"
        )
        params["q"] = query.strip()
    if region:
        conditions.append("toString(c.code_nd) = {region:String}")
        params["region"] = region

    # Сортировка в этом режиме возможна только по полям справочника:
    # показатели реестра для непрочитанных страниц ещё не посчитаны
    sort_column = {
        "taxpayer_iin_bin": "taxpayer_iin_bin",
        "taxpayer_name": "taxpayer_name",
        "code_nd": "code_nd",
        "reg_start_date": "reg_start_date",
    }.get(sort, "taxpayer_iin_bin")
    direction = "ASC" if str(order).lower() == "asc" else "DESC"

    rows = await clickhouse.fetch_all(
        f"""
        SELECT
            c.taxpayer_iin_bin AS taxpayer_iin_bin,
            ifNull(toString(any(c.taxpayer_name)), '') AS taxpayer_name,
            ifNull(toString(any(c.category)), '') AS category,
            ifNull(toString(any(c.code_nd)), '') AS code_nd,
            ifNull(toString(any(c.address)), '') AS address,
            ifNull(toString(any(c.reg_start_date)), '') AS reg_start_date,
            count() OVER () AS total_count
        FROM {settings.DICT_COMPANIES} AS c
        WHERE {" AND ".join(conditions)}
        GROUP BY c.taxpayer_iin_bin
        ORDER BY {sort_column} {direction}
        LIMIT {int(limit)} OFFSET {int(offset)}
        """,
        params,
    )

    total = int(rows[0].get("total_count") or 0) if rows else 0
    for row in rows:
        row.pop("total_count", None)

    bins = [row["taxpayer_iin_bin"] for row in rows]
    summary: Dict[str, Dict[str, Any]] = {}
    ownership_map: Dict[str, str] = {}

    if bins:
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

        if tables:
            try:
                for row in await clickhouse.fetch_all(
                    build_companies_enrich_sql(tables), {"bins": bins}
                ):
                    summary[row["taxpayer_iin_bin"]] = row
            except ClickHouseError as exc:
                logger.error("Показатели реестра для страницы справочника не посчитаны: %s", exc)

    for row in rows:
        bin_value = row["taxpayer_iin_bin"]
        ownership_type = ownership_map.get(bin_value, "")
        state_owned = registry_service.is_state_owned(ownership_type)
        stats = summary.get(bin_value, {})
        row["ownership_type"] = ownership_type
        row["is_state_owned"] = state_owned
        row["region"] = row.get("code_nd") or ""
        row["beneficiary_count"] = 0 if state_owned else int(stats.get("beneficiary_count") or 0)
        row["max_ball3"] = 0.0 if state_owned else round(float(stats.get("max_ball3") or 0), 2)

    return {
        "items": rows,
        "total": total,
        "page": offset // limit + 1,
        "limit": limit,
        "scope": "all",
    }


# ---------------------------------------------------------------------------
# Список бенефициаров
# ---------------------------------------------------------------------------
async def list_beneficiaries(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
    status_filter: Optional[str] = None,
    algorithm: Optional[str] = None,
    risk: Optional[str] = None,
    nonresident: Optional[bool] = None,
    sort: str = "max_ball3",
    order: str = "desc",
) -> Dict[str, Any]:
    """Страница списка бенефициаров, свёрнутого по ИИН."""
    limit, offset = _page_bounds(page, limit)
    tables = await algorithm_service.active_result_tables(session)
    if not tables:
        return {"items": [], "total": 0, "page": page, "limit": limit}

    conditions: List[str] = []
    params: Dict[str, Any] = {}

    if query:
        conditions.append(
            "(positionCaseInsensitive(r.iin_clean, {q:String}) > 0"
            " OR positionCaseInsensitive(r.benefeciary_key, {q:String}) > 0"
            " OR positionCaseInsensitive(r.benefeciary_name, {q:String}) > 0)"
        )
        params["q"] = query.strip()
    if status_filter == "registration":
        conditions.append("r.status LIKE 'Регистрационный%'")
    elif status_filter == "assumed":
        conditions.append("r.status LIKE 'Предполагаемый%'")
    if algorithm:
        conditions.append("has(r.algorithm_codes, {algo:String})")
        params["algo"] = algorithm
    if nonresident is True:
        conditions.append("r.is_nonresident")
    elif nonresident is False:
        conditions.append("NOT r.is_nonresident")

    risk_condition = _risk_condition(risk, "r.max_ball3")
    if risk_condition:
        conditions.append(risk_condition)

    if sort not in BENEFICIARY_SORT_COLUMNS:
        sort = "max_ball3"

    sql = build_beneficiaries_list_sql(
        tables, conditions=conditions, sort=sort, order=order, limit=limit, offset=offset
    )
    rows = await clickhouse.fetch_all(sql, params)

    total = int(rows[0].get("total_count") or 0) if rows else 0
    # Дочистка имён моделью — та же, что в карточке компании, чтобы список
    # и карточка показывали одно и то же наименование
    await name_service.enrich_names(session, rows)
    for row in rows:
        row.pop("total_count", None)
        row.pop("dop_info", None)
        row["max_ball3"] = round(float(row.get("max_ball3") or 0), 2)
        row["is_nonresident"] = bool(int(row.get("is_nonresident") or 0))

    return {"items": rows, "total": total, "page": page, "limit": limit}


async def beneficiary_profile(session: AsyncSession, iin: str) -> Dict[str, Any]:
    """Профиль бенефициара и все компании, где он выявлен."""
    tables = await algorithm_service.active_result_tables(session)
    if not tables:
        return {
            "benefeciary_key": iin,
            "benefeciary_iin_bin": "",
            "benefeciary_name": "",
            "companies": [],
        }

    # Здесь отбор идёт по бенефициару, поэтому подстановка ЮЛ→ФЛ не
    # применяется: она меняет как раз то поле, по которому фильтруем, и
    # запрос пришлось бы разворачивать по всему реестру. Профиль строится
    # по тому идентификатору, который выдали алгоритмы.
    sql = build_registry_sql(
        tables,
        company_filter="benefeciary_key = {iin:String}",
        category_source=registry_service.category_source(),
        row_limit=int(runtime.get("MAX_ROWS_PER_CLIENT")),
    )
    rows = await clickhouse.fetch_all(sql, {"iin": iin})

    name = next((r.get("benefeciary_name") for r in rows if r.get("benefeciary_name")), "")
    companies = sorted(
        rows,
        key=lambda r: (-float(r.get("ball3") or 0), str(r.get("taxpayer_name") or "")),
    )
    return {
        "benefeciary_key": iin,
        # Показанный ИИН берётся из самих строк: там он уже приведён
        # к виду «номер, слово нерезидент или пусто»
        "benefeciary_iin_bin": next(
            (r.get("benefeciary_iin_bin") for r in rows
             if r.get("benefeciary_iin_bin")), ""
        ),
        "benefeciary_name": name,
        "company_count": len({r.get("taxpayer_iin_bin") for r in rows}),
        "max_ball3": round(max((float(r.get("ball3") or 0) for r in rows), default=0.0), 2),
        "companies": companies,
    }


# ---------------------------------------------------------------------------
# Структуры владения
# ---------------------------------------------------------------------------
async def _company_names(bins: List[str]) -> Dict[str, Dict[str, str]]:
    if not bins:
        return {}
    rows = await clickhouse.fetch_all(build_company_names_sql(), {"bins": bins})
    return {r["taxpayer_iin_bin"]: r for r in rows}


async def get_ownership_graph(session: AsyncSession, node_id: str) -> Dict[str, Any]:
    """Граф владения вокруг компании либо физического лица.

    Строится из тех же данных, что и карточка: учредители и руководители МЮ
    плюс бенефициары из реестра. Новых признаков владения здесь не выводится —
    граф лишь показывает уже посчитанные связи.
    """
    node_id = (node_id or "").strip()
    if not node_id:
        return {"root": None, "nodes": [], "edges": []}

    company = await registry_service.get_company_info(node_id)
    if company is not None:
        return await _company_graph(session, node_id, company)
    return await _person_graph(session, node_id)


def _node(
    nodes: Dict[str, Dict[str, Any]],
    node_id: str,
    *,
    kind: str,
    name: str,
    is_root: bool = False,
    **extra: Any,
) -> None:
    """Добавляет узел, не затирая уже известные о нём сведения."""
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = {
            "id": node_id,
            "kind": kind,
            "name": name or node_id,
            "is_root": is_root,
            **extra,
        }
        return
    if name and not existing.get("name"):
        existing["name"] = name
    if is_root:
        existing["is_root"] = True
    for key, value in extra.items():
        if value not in (None, "", 0) and not existing.get(key):
            existing[key] = value


async def _company_graph(
    session: AsyncSession, bin_value: str, company: Dict[str, Any]
) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    _node(
        nodes,
        bin_value,
        kind="company",
        name=company.get("taxpayer_name") or bin_value,
        is_root=True,
        is_state_owned=company.get("is_state_owned", False),
        ownership_type=company.get("ownership_type", ""),
    )

    founders = await clickhouse.fetch_all(build_founders_of_sql(), {"bins": [bin_value]})
    legal_founders: List[str] = []
    for row in founders:
        founder_id = row.get("founder_iin_bin") or row.get("founder_name") or ""
        if not founder_id:
            continue
        kind = "company" if row.get("founder_kind") == "company" else "person"
        _node(nodes, founder_id, kind=kind, name=row.get("founder_name") or founder_id)
        edges.append(
            {
                "source": founder_id,
                "target": bin_value,
                "kind": "founder",
                "label": "учредитель",
                "share": row.get("share_percentage") or "",
            }
        )
        if kind == "company" and row.get("founder_iin_bin"):
            legal_founders.append(row["founder_iin_bin"])

    # Второй уровень: учредители юридических лиц — учредителей корневой компании
    if legal_founders:
        upper = await clickhouse.fetch_all(
            build_founders_of_sql(), {"bins": legal_founders[:20]}
        )
        for row in upper:
            founder_id = row.get("founder_iin_bin") or row.get("founder_name") or ""
            if not founder_id:
                continue
            kind = "company" if row.get("founder_kind") == "company" else "person"
            _node(nodes, founder_id, kind=kind, name=row.get("founder_name") or founder_id)
            edges.append(
                {
                    "source": founder_id,
                    "target": row["taxpayer_iin_bin"],
                    "kind": "founder",
                    "label": "учредитель",
                    "share": row.get("share_percentage") or "",
                }
            )

    directors = await registry_service.get_directors(bin_value)
    for row in directors:
        director_id = row.get("director_iin_bin") or ""
        if not director_id:
            continue
        _node(nodes, director_id, kind="person", name=row.get("director_name") or director_id)
        edges.append(
            {
                "source": director_id,
                "target": bin_value,
                "kind": "director",
                "label": "руководитель",
                "share": "",
            }
        )

    if not company.get("is_state_owned"):
        beneficiaries = await registry_service.get_beneficiaries(session, bin_value)
        for row in beneficiaries:
            beneficiary_id = row.get("benefeciary_key") or row.get("benefeciary_name") or ""
            if not beneficiary_id:
                continue
            _node(
                nodes,
                beneficiary_id,
                kind="person",
                name=row.get("benefeciary_name") or beneficiary_id,
            )
            edges.append(
                {
                    "source": beneficiary_id,
                    "target": bin_value,
                    "kind": "beneficiary",
                    "label": row.get("status") or "БС",
                    "share": row.get("share_percentage") or "",
                    "ball3": round(float(row.get("ball3") or 0), 2),
                    "algorithms": row.get("algorithm_codes") or [],
                }
            )

    # Наименования для узлов-компаний, попавших из таблицы учредителей
    unknown = [
        node["id"]
        for node in nodes.values()
        if node["kind"] == "company" and node["id"] != bin_value
    ]
    for node_id, info in (await _company_names(unknown)).items():
        if info.get("taxpayer_name"):
            nodes[node_id]["name"] = info["taxpayer_name"]

    return {
        "root": {"id": bin_value, "kind": "company", "name": company.get("taxpayer_name") or bin_value},
        "nodes": list(nodes.values()),
        "edges": edges,
    }


async def _person_graph(session: AsyncSession, iin: str) -> Dict[str, Any]:
    """Граф вокруг физического лица: где учредитель, руководитель, бенефициар."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    limit = clamp_rows(100, 100)
    name_row = await clickhouse.fetch_one(build_person_name_sql(), {"iin": iin})
    person_name = (name_row or {}).get("taxpayer_name") or iin

    _node(nodes, iin, kind="person", name=person_name, is_root=True)

    founder_rows = await clickhouse.fetch_all(
        build_companies_of_founder_sql(), {"iin": iin, "lim": limit}
    )
    for row in founder_rows:
        target = row["taxpayer_iin_bin"]
        _node(nodes, target, kind="company", name=target)
        edges.append(
            {
                "source": iin,
                "target": target,
                "kind": "founder",
                "label": "учредитель",
                "share": row.get("share_percentage") or "",
            }
        )

    director_rows = await clickhouse.fetch_all(
        build_companies_of_director_sql(), {"iin": iin, "lim": limit}
    )
    for row in director_rows:
        target = row["taxpayer_iin_bin"]
        _node(nodes, target, kind="company", name=target)
        edges.append(
            {
                "source": iin,
                "target": target,
                "kind": "director",
                "label": "руководитель",
                "share": "",
            }
        )

    profile = await beneficiary_profile(session, iin)
    if profile.get("benefeciary_name"):
        nodes[iin]["name"] = profile["benefeciary_name"]
    for row in profile.get("companies", []):
        target = row.get("taxpayer_iin_bin") or ""
        if not target:
            continue
        _node(nodes, target, kind="company", name=row.get("taxpayer_name") or target)
        edges.append(
            {
                "source": iin,
                "target": target,
                "kind": "beneficiary",
                "label": row.get("status") or "БС",
                "share": row.get("share_percentage") or "",
                "ball3": round(float(row.get("ball3") or 0), 2),
                "algorithms": row.get("algorithm_codes") or [],
            }
        )

    # Ни справочника, ни связей — такого идентификатора в данных нет,
    # и рисовать одинокий узел бессмысленно: страница покажет «не найдено»
    if not edges and not name_row:
        return {"root": None, "nodes": [], "edges": []}

    unknown = [node["id"] for node in nodes.values() if node["kind"] == "company"]
    for node_id, info in (await _company_names(unknown)).items():
        if info.get("taxpayer_name"):
            nodes[node_id]["name"] = info["taxpayer_name"]

    return {
        "root": {"id": iin, "kind": "person", "name": nodes[iin]["name"]},
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Источники данных
# ---------------------------------------------------------------------------
async def list_sources(session: AsyncSession) -> List[Dict[str, Any]]:
    """Каталог источников с количеством записей и датой обновления.

    Размеры берутся из ``system.tables`` одним запросом: count() по каждой
    из таблиц ЭСФ и ФМ-1 занял бы минуты.
    """
    algorithms = {a.code: a for a in await algorithm_service.list_algorithms(session)}
    table_info: Dict[str, Dict[str, Any]] = {}

    wanted = sources_catalog.all_tables()
    if wanted:
        try:
            rows = await clickhouse.fetch_all(
                """
                SELECT
                    concat(t.database, '.', t.name) AS full_name,
                    toString(t.total_rows) AS total_rows,
                    toString(t.metadata_modification_time) AS modified_at,
                    t.engine AS engine
                FROM system.tables AS t
                WHERE concat(t.database, '.', t.name) IN {tables:Array(String)}
                """,
                {"tables": wanted},
            )
            table_info = {r["full_name"]: r for r in rows}
        except ClickHouseError as exc:
            logger.warning("Сведения о таблицах источников не получены: %s", exc)

    result: List[Dict[str, Any]] = []
    for source in sources_catalog.SOURCES:
        tables: List[Dict[str, Any]] = []
        total_rows = 0
        modified: List[str] = []

        for table in list(source.tables) + list(source.extra_tables):
            info = table_info.get(table)
            rows_value = int(info["total_rows"]) if info and info.get("total_rows") else None
            if rows_value:
                total_rows += rows_value
            if info and info.get("modified_at"):
                modified.append(info["modified_at"])
            tables.append(
                {
                    "name": table,
                    "exists": info is not None,
                    "row_count": rows_value,
                    "modified_at": (info or {}).get("modified_at", ""),
                    "engine": (info or {}).get("engine", ""),
                    "is_extra": table in source.extra_tables,
                }
            )

        used_by = []
        for code in source.algorithms:
            algorithm = algorithms.get(code)
            used_by.append(
                {
                    "code": code,
                    "name": algorithm.name if algorithm else "",
                    "is_active": bool(algorithm.is_active) if algorithm else False,
                    "last_run_at": algorithm.last_run_at.isoformat()
                    if algorithm and algorithm.last_run_at
                    else "",
                    "last_run_status": (algorithm.last_run_status if algorithm else "") or "",
                    "last_row_count": algorithm.last_row_count if algorithm else None,
                }
            )

        result.append(
            {
                "key": source.key,
                "name": source.name,
                "organization": source.organization,
                "note": source.note,
                "tables": tables,
                "algorithms": used_by,
                "row_count": total_rows or None,
                "updated_at": max(modified) if modified else "",
            }
        )

    return result


# ---------------------------------------------------------------------------
# Дашборд
# ---------------------------------------------------------------------------
async def dashboard(session: AsyncSession) -> Dict[str, Any]:
    """Показатели и таблицы дашборда.

    Собирается поверх общей статистики реестра, к которой добавляются
    разрезы, нужные только этой странице.
    """
    stats = await registry_service.get_stats(session)
    tables = await algorithm_service.active_result_tables(session)

    async def compute() -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "total_companies": 0,
            "companies_with_bs": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "top_by_beneficiaries": [],
            "top_by_risk": [],
        }

        try:
            value = await clickhouse.fetch_value(build_total_companies_sql(), default=0)
            payload["total_companies"] = int(value or 0)
        except ClickHouseError as exc:
            logger.warning("Общее число ЮЛ не получено: %s", exc)

        if not tables:
            return payload

        try:
            summary = await clickhouse.fetch_one(build_dashboard_summary_sql(tables)) or {}
            payload.update(
                {
                    "companies_with_bs": int(summary.get("companies_with_bs") or 0),
                    "high_risk_count": int(summary.get("high_risk_count") or 0),
                    "medium_risk_count": int(summary.get("medium_risk_count") or 0),
                    "low_risk_count": int(summary.get("low_risk_count") or 0),
                }
            )
        except ClickHouseError as exc:
            logger.error("Сводка дашборда не рассчитана: %s", exc)

        for key, by in (("top_by_beneficiaries", "count"), ("top_by_risk", "risk")):
            try:
                rows = await clickhouse.fetch_all(build_top_companies_sql(tables, by=by, limit=10))
                for row in rows:
                    row["max_ball3"] = round(float(row.get("max_ball3") or 0), 2)
                    row["region"] = row.get("code_nd") or ""
                payload[key] = rows
            except ClickHouseError as exc:
                logger.error("Топ компаний (%s) не рассчитан: %s", by, exc)

        return payload

    extra = await cached(f"dashboard:{','.join(sorted(tables))}", compute)
    return {**stats, **extra}
