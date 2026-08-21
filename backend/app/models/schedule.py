"""Расписание ночного пересчёта реестра и история запусков.

Приложение работает в несколько воркеров uvicorn — это отдельные процессы,
и планировщик крутится в каждом. Чтобы пересчёт не запустился четырежды,
момент запуска «занимается» одним UPDATE по строке расписания: кто перевёл
next_run_at вперёд, тот и считает.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

#: Единственная строка расписания
SCHEDULE_ID = 1


class BsSchedule(Base):
    """Настройка ночного пересчёта. В таблице всегда одна строка."""

    __tablename__ = "bs_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    #: Выполнять ли пересчёт по расписанию
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Время запуска в формате ЧЧ:ММ по часовому поясу приложения
    run_time: Mapped[str] = mapped_column(String(5), default="03:00", nullable=False)
    #: Часовой пояс, в котором трактуется run_time
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Almaty", nullable=False)

    #: Момент следующего запуска в UTC — по нему воркеры и договариваются
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class BsRun(Base):
    """Один пересчёт реестра — ночной либо запущенный вручную."""

    __tablename__ = "bs_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: schedule — по расписанию, manual — кнопкой из интерфейса
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    #: running, success, partial, failed
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Итог по каждому алгоритму в виде JSON-строки
    details: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
