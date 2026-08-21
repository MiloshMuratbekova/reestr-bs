"""Ночной пересчёт реестра: расписание, запуск и история.

Пересчёт — это последовательный прогон всех активных алгоритмов
(:func:`app.services.algorithm_service.recalculate_all`). Здесь только
управление моментом запуска и запись результата; сама логика выявления БС
не затрагивается.

Про несколько воркеров
----------------------
uvicorn поднимает приложение в нескольких процессах, и цикл планировщика
работает в каждом. Право на запуск разыгрывается одним UPDATE: строка
расписания переводится на следующий срок, и только тот процесс, чей UPDATE
изменил строку, начинает считать. Остальные видят rowcount = 0 и ждут дальше.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError
from app.db.postgres import SessionLocal
from app.models import SCHEDULE_ID, BsRun, BsSchedule
from app.services import algorithm_service, listing_service

logger = get_logger(__name__)

#: Как часто воркер проверяет, не наступил ли срок запуска
POLL_INTERVAL_SECONDS = 60

#: Запуск, висящий дольше этого срока, считается оборванным (упал процесс)
STALE_RUN_HOURS = 12


def _zone(name: str):
    """Часовой пояс по имени. При неизвестном имени — UTC, с записью в журнал."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001 — база часовых поясов может отсутствовать
        logger.warning("Часовой пояс «%s» недоступен (%s), расписание считается в UTC", name, exc)
        return timezone.utc


def parse_run_time(value: str) -> tuple[int, int]:
    """Разбирает «ЧЧ:ММ». Некорректное значение отбрасывается на сервере."""
    try:
        hour_text, minute_text = str(value).split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, ValueError):
        raise ValueError("Время запуска указывается в формате ЧЧ:ММ, например 03:00") from None

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Время запуска должно быть в диапазоне от 00:00 до 23:59")
    return hour, minute


def compute_next_run(
    run_time: str, zone_name: str, *, after: Optional[datetime] = None
) -> datetime:
    """Ближайший момент запуска в UTC, строго позже ``after``."""
    hour, minute = parse_run_time(run_time)
    zone = _zone(zone_name)

    moment = (after or datetime.now(timezone.utc)).astimezone(zone)
    candidate = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= moment:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Расписание
# ---------------------------------------------------------------------------
async def ensure_schedule(session: AsyncSession) -> BsSchedule:
    """Возвращает строку расписания, создавая её при первом обращении."""
    schedule = (
        await session.execute(select(BsSchedule).where(BsSchedule.id == SCHEDULE_ID))
    ).scalar_one_or_none()
    if schedule is not None:
        return schedule

    schedule = BsSchedule(
        id=SCHEDULE_ID,
        enabled=False,
        run_time="03:00",
        timezone=settings.TIMEZONE,
        next_run_at=None,
    )
    session.add(schedule)
    try:
        await session.commit()
    except IntegrityError:
        # Строку создал соседний воркер — читаем её
        await session.rollback()
        schedule = (
            await session.execute(select(BsSchedule).where(BsSchedule.id == SCHEDULE_ID))
        ).scalar_one()
    return schedule


def schedule_to_dict(schedule: BsSchedule) -> Dict[str, Any]:
    return {
        "enabled": bool(schedule.enabled),
        "run_time": schedule.run_time,
        "timezone": schedule.timezone,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else "",
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else "",
        "updated_by": schedule.updated_by or "",
    }


async def get_schedule(session: AsyncSession) -> Dict[str, Any]:
    return schedule_to_dict(await ensure_schedule(session))


async def update_schedule(
    session: AsyncSession,
    *,
    enabled: bool,
    run_time: str,
    zone_name: Optional[str] = None,
    updated_by: str = "",
) -> Dict[str, Any]:
    """Сохраняет расписание и пересчитывает момент следующего запуска."""
    parse_run_time(run_time)  # проверка формата до записи

    schedule = await ensure_schedule(session)
    schedule.enabled = bool(enabled)
    schedule.run_time = run_time
    schedule.timezone = zone_name or schedule.timezone or settings.TIMEZONE
    schedule.updated_by = updated_by
    schedule.next_run_at = (
        compute_next_run(schedule.run_time, schedule.timezone) if schedule.enabled else None
    )
    await session.commit()
    await session.refresh(schedule)

    logger.info(
        "Расписание пересчёта: %s, время %s (%s), следующий запуск %s",
        "включено" if schedule.enabled else "выключено",
        schedule.run_time,
        schedule.timezone,
        schedule.next_run_at or "—",
    )
    return schedule_to_dict(schedule)


# ---------------------------------------------------------------------------
# История запусков
# ---------------------------------------------------------------------------
def run_to_dict(run: BsRun) -> Dict[str, Any]:
    try:
        details = json.loads(run.details or "[]")
    except json.JSONDecodeError:
        details = []
    return {
        "id": run.id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "duration_ms": run.duration_ms,
        "total": run.total,
        "succeeded": run.succeeded,
        "failed": run.failed,
        "total_rows": run.total_rows,
        "error": run.error or "",
        "triggered_by": run.triggered_by or "",
        "details": details,
    }


async def list_runs(session: AsyncSession, *, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            select(BsRun).order_by(BsRun.started_at.desc()).limit(max(1, min(200, int(limit))))
        )
    ).scalars().all()
    return [run_to_dict(run) for run in rows]


async def active_run(session: AsyncSession) -> Optional[BsRun]:
    """Незавершённый пересчёт, если он есть.

    Запись, висящая в состоянии «выполняется» дольше STALE_RUN_HOURS,
    во внимание не принимается: процесс, который её начал, уже не жив,
    иначе пересчёт нельзя было бы запустить никогда.
    """
    threshold = datetime.now(timezone.utc) - timedelta(hours=STALE_RUN_HOURS)
    return (
        await session.execute(
            select(BsRun)
            .where(BsRun.status == "running", BsRun.started_at >= threshold)
            .order_by(BsRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Пересчёт
# ---------------------------------------------------------------------------
async def run_recalculation(
    *, trigger: str = "manual", triggered_by: str = "", session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Выполняет пересчёт всех алгоритмов и записывает результат в историю."""
    own_session = session is None
    session = session or SessionLocal()

    try:
        run = BsRun(trigger=trigger, status="running", triggered_by=triggered_by)
        session.add(run)
        await session.commit()
        await session.refresh(run)

        started = time.perf_counter()
        try:
            result = await algorithm_service.recalculate_all(session, triggered_by=triggered_by)
        except (ClickHouseError, SQLAlchemyError) as exc:
            run.status = "failed"
            run.error = str(exc)[:4000]
            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            await session.commit()
            logger.error("Пересчёт завершился ошибкой: %s", exc)
            raise

        run.status = "success" if result["failed"] == 0 else "partial"
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = result["duration_ms"]
        run.total = result["total"]
        run.succeeded = result["succeeded"]
        run.failed = result["failed"]
        run.total_rows = result["total_rows"]
        run.details = json.dumps(result["results"], ensure_ascii=False)[:1_000_000]
        await session.commit()

        # Сводные разрезы посчитаны по прежним данным — их надо забыть
        listing_service.drop_cache()

        return {**result, "run_id": run.id, "status": run.status}
    finally:
        if own_session:
            await session.close()


# ---------------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------------
async def _claim_due_run() -> bool:
    """Пытается занять наступивший срок запуска. True — этот процесс считает."""
    async with SessionLocal() as session:
        schedule = await ensure_schedule(session)
        if not schedule.enabled:
            return False

        now = datetime.now(timezone.utc)
        if schedule.next_run_at is None:
            # Расписание включено, а срок не проставлен — выставляем и ждём
            schedule.next_run_at = compute_next_run(schedule.run_time, schedule.timezone)
            await session.commit()
            return False

        next_at = schedule.next_run_at
        if next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=timezone.utc)
        if next_at > now:
            return False

        following = compute_next_run(schedule.run_time, schedule.timezone, after=now)
        result = await session.execute(
            update(BsSchedule)
            .where(
                BsSchedule.id == SCHEDULE_ID,
                BsSchedule.enabled.is_(True),
                BsSchedule.next_run_at == schedule.next_run_at,
            )
            .values(next_run_at=following, last_run_at=now)
        )
        await session.commit()
        return result.rowcount == 1


async def scheduler_loop() -> None:
    """Фоновая задача: раз в минуту проверяет, не наступил ли срок пересчёта."""
    logger.info("Планировщик ночного пересчёта запущен, опрос раз в %d с", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            if not await _claim_due_run():
                continue

            logger.info("Наступил срок ночного пересчёта — запуск")
            await run_recalculation(trigger="schedule", triggered_by="расписание")
        except asyncio.CancelledError:
            logger.info("Планировщик остановлен")
            raise
        except Exception as exc:  # noqa: BLE001 — цикл не должен умирать от разовой ошибки
            logger.error("Ошибка в цикле планировщика: %s", exc)
