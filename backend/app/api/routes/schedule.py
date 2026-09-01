"""Расписание ночного пересчёта реестра и история запусков. Только администратор."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, SessionDep
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError
from app.schemas.listing import RunOut, ScheduleOut, ScheduleUpdate
from app.services import algorithm_service, schedule_service

logger = get_logger(__name__)
router = APIRouter(tags=["Расписание"], prefix="/schedule")


@router.get("", response_model=ScheduleOut, summary="Текущее расписание пересчёта")
async def get_schedule(session: SessionDep, _: AdminUser):
    return await schedule_service.get_schedule(session)


@router.post("", response_model=ScheduleOut, summary="Сохранить расписание пересчёта")
async def save_schedule(payload: ScheduleUpdate, session: SessionDep, user: AdminUser):
    try:
        return await schedule_service.update_schedule(
            session,
            enabled=payload.enabled,
            run_time=payload.run_time,
            zone_name=payload.timezone,
            updated_by=user.username,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/runs", response_model=list[RunOut], summary="История пересчётов")
async def runs(session: SessionDep, _: AdminUser, limit: int = Query(20, ge=1, le=200)):
    return await schedule_service.list_runs(session, limit=limit)


@router.post("/run", response_model=RunOut, summary="Запустить пересчёт вручную")
async def run_now(session: SessionDep, user: AdminUser):
    """Пересчёт выполняется синхронно и занимает продолжительное время.

    Повторный запуск, пока предыдущий не закончился, отклоняется: алгоритмы
    пишут в одни и те же таблицы ClickHouse, и параллельный прогон испортил бы
    результат обоих.
    """
    running = await schedule_service.active_run(session)
    if running is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Пересчёт уже выполняется с {running.started_at:%d.%m.%Y %H:%M} "
            f"(инициатор: {running.triggered_by or 'система'}). Дождитесь завершения.",
        )

    logger.info("Ручной пересчёт реестра запущен пользователем %s", user.username)
    try:
        result = await schedule_service.run_recalculation(
            trigger="manual", triggered_by=user.username, session=session
        )
    except algorithm_service.ReadOnlyMode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ClickHouseError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Пересчёт не выполнен: {exc}"
        ) from exc

    runs_list = await schedule_service.list_runs(session, limit=1)
    if runs_list:
        return runs_list[0]
    return {
        "id": result.get("run_id", 0),
        "trigger": "manual",
        "status": result.get("status", "success"),
    }
