"""Управление алгоритмами выявления БС. Доступ только у администратора."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, SessionDep
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError
from app.schemas.algorithm import (
    AiUpdateRequest,
    AiUpdateResponse,
    AlgorithmCreate,
    AlgorithmHistoryOut,
    AlgorithmOut,
    AlgorithmRunResult,
    AlgorithmUpdate,
    RecalculateResponse,
)
from app.services import ai_service, algorithm_service, schedule_service

logger = get_logger(__name__)
router = APIRouter(tags=["Алгоритмы"])


@router.get("/algorithms", response_model=list[AlgorithmOut], summary="Список алгоритмов")
async def list_algorithms(session: SessionDep, _: AdminUser):
    return await algorithm_service.list_algorithms(session)


@router.post(
    "/algorithms",
    response_model=AlgorithmOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать алгоритм",
)
async def create_algorithm(payload: AlgorithmCreate, session: SessionDep, user: AdminUser):
    try:
        await algorithm_service.get_algorithm(session, payload.code)
    except algorithm_service.AlgorithmNotFound:
        pass
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Алгоритм {payload.code} уже существует"
        )

    logger.info("Создание алгоритма %s пользователем %s", payload.code, user.username)
    return await algorithm_service.create_algorithm(session, payload.model_dump())


@router.get("/algorithms/{code}", response_model=AlgorithmOut, summary="Алгоритм по коду")
async def get_algorithm(code: str, session: SessionDep, _: AdminUser):
    try:
        return await algorithm_service.get_algorithm(session, code)
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.put("/algorithms/{code}", summary="Обновить SQL алгоритма и выполнить его")
async def update_algorithm(
    code: str, payload: AlgorithmUpdate, session: SessionDep, user: AdminUser
):
    try:
        result = await algorithm_service.update_algorithm(
            session,
            code,
            payload.model_dump(exclude_unset=True),
            changed_by=user.username,
            execute=payload.execute,
        )
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return {
        "algorithm": AlgorithmOut.model_validate(result["algorithm"]),
        "run": result["run"],
        "run_error": result["run_error"],
    }


@router.get(
    "/algorithms/{code}/history",
    response_model=list[AlgorithmHistoryOut],
    summary="История изменений SQL",
)
async def algorithm_history(code: str, session: SessionDep, _: AdminUser):
    try:
        return await algorithm_service.get_history(session, code)
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "/algorithms/{code}/rollback/{history_id}",
    response_model=AlgorithmOut,
    summary="Откатить SQL на версию из истории",
)
async def rollback_algorithm(
    code: str, history_id: int, session: SessionDep, user: AdminUser
):
    try:
        return await algorithm_service.rollback_algorithm(
            session, code, history_id, changed_by=user.username
        )
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "/algorithms/{code}/run",
    response_model=AlgorithmRunResult,
    summary="Запустить алгоритм в ClickHouse",
)
async def run_algorithm(code: str, session: SessionDep, user: AdminUser):
    try:
        result = await algorithm_service.run_algorithm(session, code, triggered_by=user.username)
    except algorithm_service.ReadOnlyMode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ClickHouseError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Ошибка выполнения алгоритма {code} в ClickHouse: {exc}",
        ) from exc
    return AlgorithmRunResult(**result)


@router.post(
    "/algorithms/{code}/ai-update",
    response_model=AiUpdateResponse,
    summary="Предложение нового SQL от Qwen по бизнес-требованию",
)
async def ai_update(
    code: str, payload: AiUpdateRequest, session: SessionDep, user: AdminUser
):
    try:
        algorithm = await algorithm_service.get_algorithm(session, code)
    except algorithm_service.AlgorithmNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    logger.info("Запрос ИИ-обновления SQL %s пользователем %s", code, user.username)

    try:
        result = await ai_service.suggest_sql_update(
            code, algorithm.sql_script, payload.requirement
        )
    except ai_service.AiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return AiUpdateResponse(**result)


@router.post(
    "/recalculate",
    response_model=RecalculateResponse,
    summary="Пересчитать все алгоритмы последовательно",
)
async def recalculate(session: SessionDep, user: AdminUser):
    """Пересчёт идёт через schedule_service — тогда он попадает в историю
    запусков наравне с ночным и сбрасывает кеш сводных разрезов.
    """
    running = await schedule_service.active_run(session)
    if running is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Пересчёт уже выполняется с {running.started_at:%d.%m.%Y %H:%M} "
            f"(инициатор: {running.triggered_by or 'система'}). Дождитесь завершения.",
        )

    logger.info("Пересчёт реестра запущен пользователем %s", user.username)
    try:
        result = await schedule_service.run_recalculation(
            trigger="manual", triggered_by=user.username, session=session
        )
    except algorithm_service.ReadOnlyMode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RecalculateResponse(**result)
