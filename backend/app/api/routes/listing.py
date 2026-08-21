"""Страницы списков: юридические лица, бенефициары, структуры владения, источники."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.registry import clickhouse_detail
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError
from app.schemas.listing import (
    BeneficiaryListResponse,
    CompanyListResponse,
    OwnershipResponse,
)
from app.services import listing_service

logger = get_logger(__name__)
router = APIRouter(tags=["Списки"])


@router.get(
    "/companies",
    response_model=CompanyListResponse,
    summary="Список юридических лиц с показателями реестра",
)
async def companies(
    session: SessionDep,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    # Верхняя граница не задаётся здесь: значение режется на сервере
    # по настройке «максимум строк в выборке»
    limit: int = Query(50, ge=1),
    query: Optional[str] = Query(None, description="БИН или часть наименования"),
    region: Optional[str] = Query(None, description="Код региона (code_nd)"),
    ownership: Optional[str] = Query(None, description="state — государственные, private — прочие"),
    risk: Optional[str] = Query(None, description="high | medium | low"),
    scope: str = Query(
        "registry",
        description=(
            "registry — только компании с выявленными БС (доступны все сортировки); "
            "all — весь справочник ЮЛ (сортировка только по его полям)"
        ),
    ),
    sort: str = Query("max_ball3"),
    order: str = Query("desc"),
):
    try:
        return await listing_service.list_companies(
            session,
            page=page,
            limit=limit,
            query=query,
            region=region,
            ownership=ownership,
            risk=risk,
            scope=scope,
            sort=sort,
            order=order,
        )
    except ClickHouseError as exc:
        logger.error("Список ЮЛ не построен: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc


@router.get(
    "/beneficiaries",
    response_model=BeneficiaryListResponse,
    summary="Список бенефициарных собственников",
)
async def beneficiaries(
    session: SessionDep,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1),
    query: Optional[str] = Query(None, description="ИИН или часть ФИО"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="registration | assumed"
    ),
    algorithm: Optional[str] = Query(None, description="Код алгоритма, например БС-1"),
    risk: Optional[str] = Query(None, description="high | medium | low"),
    nonresident: Optional[bool] = Query(None, description="Только нерезиденты либо только резиденты"),
    sort: str = Query("max_ball3"),
    order: str = Query("desc"),
):
    try:
        return await listing_service.list_beneficiaries(
            session,
            page=page,
            limit=limit,
            query=query,
            status_filter=status_filter,
            algorithm=algorithm,
            risk=risk,
            nonresident=nonresident,
            sort=sort,
            order=order,
        )
    except ClickHouseError as exc:
        logger.error("Список бенефициаров не построен: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc


@router.get(
    "/beneficiaries/{iin}",
    summary="Профиль бенефициара и все компании, где он выявлен",
)
async def beneficiary(iin: str, session: SessionDep, _: CurrentUser) -> dict:
    try:
        return await listing_service.beneficiary_profile(session, iin)
    except ClickHouseError as exc:
        logger.error("Профиль бенефициара %s не построен: %s", iin, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc


@router.get(
    "/ownership/{node_id}",
    response_model=OwnershipResponse,
    summary="Структура владения вокруг компании либо физического лица",
)
async def ownership(node_id: str, session: SessionDep, _: CurrentUser):
    try:
        graph = await listing_service.get_ownership_graph(session, node_id)
    except ClickHouseError as exc:
        logger.error("Структура владения %s не построена: %s", node_id, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc

    if graph.get("root") is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{node_id} не найден ни среди юридических, ни среди физических лиц",
        )
    return graph


@router.get("/sources", summary="Источники данных реестра")
async def sources(session: SessionDep, _: CurrentUser) -> list[dict]:
    try:
        return await listing_service.list_sources(session)
    except ClickHouseError as exc:
        logger.error("Каталог источников не построен: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc
