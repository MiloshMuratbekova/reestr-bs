"""Сформированные отчёты. Метаданные в PostgreSQL, файлы — в томе DATA_DIR."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class BsReport(Base):
    """Один сформированный отчёт."""

    __tablename__ = "bs_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Код шаблона: registry, high_risk, nonresidents, algorithms
    template: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    #: Название шаблона на момент формирования
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    #: Формат файла: xlsx либо pdf
    file_format: Mapped[str] = mapped_column(String(8), default="xlsx", nullable=False)
    #: Имя файла внутри каталога отчётов (без пути)
    file_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    #: Размер файла, байт
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Количество строк данных в отчёте
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Параметры формирования в виде JSON-строки
    parameters: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    created_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
