"""Поиск компаний, карточка компании, чат с Qwen и общая статистика."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, current_url
from app.schemas.registry import (
    ChatRequest,
    ChatResponse,
    CompanySearchItem,
    ExplainRequest,
    ExplainResponse,
    StatsResponse,
)
from app.services import ai_service, listing_service, registry_service

logger = get_logger(__name__)
router = APIRouter(tags=["Реестр БС"])


def clickhouse_detail(exc: ClickHouseError) -> str:
    """Сообщение аналитику по ошибке хранилища.

    Раньше здесь была одна строка на все случаи — «нет связи, проверьте
    доступность сервера». Из-за этого отклонённый сервером запрос (нет базы,
    нет прав, неизвестная настройка) выглядел как обрыв сети: в настройках
    проверка подключения проходила, а поиск сообщал, что связи нет, и человек
    шёл искать несуществующую сетевую проблему.

    Теперь два случая разведены: адрес показывается действующий (с учётом
    сохранённых настроек, а не только переменных окружения), а если сервер
    ответил — отдаём его формулировку.
    """
    if exc.is_unreachable:
        return (
            f"Нет связи с хранилищем данных ClickHouse ({current_url()}). "
            "Проверьте доступность сервера и повторите запрос."
        )
    return (
        f"ClickHouse отклонил запрос (код {exc.status_code}). "
        f"Ответ сервера: {str(exc)[:500]}"
    )


@router.get(
    "/search",
    response_model=list[CompanySearchItem],
    summary="Поиск компаний по БИН или наименованию",
)
async def search(
    session: SessionDep,
    _: CurrentUser,
    query: str = Query(..., min_length=2, description="БИН или часть наименования"),
    # Верхняя граница не задаётся здесь намеренно: значение режется на сервере
    # функцией clamp_rows по настройке «максимум строк в выборке»
    limit: int = Query(50, ge=1),
    status_filter: Optional[str] = Query(None, alias="status"),
    algorithm: Optional[str] = Query(None, description="Код алгоритма, например БС-1"),
    risk: Optional[str] = Query(None, description="high | medium | low"),
) -> list[dict]:
    try:
        return await registry_service.search_companies(
            session,
            query,
            limit=limit,
            status_filter=status_filter,
            algorithm_filter=algorithm,
            risk_filter=risk,
        )
    except ClickHouseError as exc:
        logger.error("Поиск не выполнен: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc


@router.get("/company/{bin_value}", summary="Карточка компании")
async def company_card(bin_value: str, session: SessionDep, _: CurrentUser) -> dict:
    try:
        card = await registry_service.get_company_card(session, bin_value)
    except ClickHouseError as exc:
        logger.error("Карточка %s не построена: %s", bin_value, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc

    if card is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Компания с БИН {bin_value} не найдена в справочнике юридических лиц",
        )
    return card


@router.post(
    "/company/{bin_value}/explain",
    response_model=ExplainResponse,
    summary="Объяснение от ИИ, почему выявлены бенефициарные собственники",
)
async def explain(
    bin_value: str,
    payload: ExplainRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ExplainResponse:
    try:
        card = await registry_service.get_company_card(session, bin_value)
    except ClickHouseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc

    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Компания с БИН {bin_value} не найдена")

    logger.info("Запрос ИИ-объяснения по %s от %s", bin_value, user.username)

    try:
        if payload.benefeciary_iin_bin:
            beneficiary = next(
                (
                    b
                    for b in card["beneficiaries"]
                    # Сверка по служебному ключу: в поле ИИН у нерезидента
                    # стоит слово «нерезидент», одинаковое у многих
                    if b.get("benefeciary_key") == payload.benefeciary_iin_bin
                ),
                None,
            )
            if beneficiary is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    "Указанный бенефициар не найден в реестре по этой компании",
                )
            result = await ai_service.explain_beneficiary(card["company"], beneficiary)
        else:
            result = await ai_service.explain_company(card)
    except ai_service.AiError as exc:
        logger.error("Ошибка ИИ при объяснении %s: %s", bin_value, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return ExplainResponse(explanation=result["explanation"], duration_ms=result["duration_ms"])


@router.post("/chat", response_model=ChatResponse, summary="Вопрос аналитика по компании")
async def chat(payload: ChatRequest, session: SessionDep, user: CurrentUser) -> ChatResponse:
    try:
        card = await registry_service.get_company_card(session, payload.bin)
    except ClickHouseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc

    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Компания с БИН {payload.bin} не найдена")

    logger.info("Вопрос в чат по %s от %s", payload.bin, user.username)

    try:
        result = await ai_service.chat_about_company(card, payload.message)
    except ai_service.AiError as exc:
        logger.error("Ошибка ИИ в чате по %s: %s", payload.bin, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return ChatResponse(answer=result["answer"], duration_ms=result["duration_ms"])


@router.get("/stats", response_model=StatsResponse, summary="Общая статистика реестра")
async def stats(session: SessionDep, _: CurrentUser) -> dict:
    """Показатели дашборда.

    Помимо общей статистики реестра возвращает разрезы, нужные только
    дашборду: всего ЮЛ в справочнике, распределение по уровню риска и
    два списка топ-10. Они считаются по всему реестру, поэтому держатся
    в памяти процесса несколько минут — см. listing_service.
    """
    try:
        return await listing_service.dashboard(session)
    except ClickHouseError as exc:
        logger.error("Статистика не рассчитана: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, clickhouse_detail(exc)) from exc
