"""Хранение SQL алгоритмов выявления БС и истории их изменений.

SQL живёт в PostgreSQL (bs_registry), а выполняется в ClickHouse.
Такое разделение позволяет администратору править алгоритм через интерфейс
без переустановки приложения, сохраняя предыдущую версию в истории.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class BsAlgorithm(Base):
    """Один алгоритм выявления бенефициарных собственников."""

    __tablename__ = "bs_algorithms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Код алгоритма из ТЗ, например «БС-1»
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    #: Название алгоритма
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Текстовое описание логики из бизнес-требований
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Полный SQL код алгоритма для выполнения в ClickHouse
    #: (может содержать несколько операторов, разделённых «;»)
    sql_script: Mapped[str] = mapped_column(Text, nullable=False)
    #: Название таблицы результата в ClickHouse, например «AFM_6_TEST.AFM_6_1_7»
    clickhouse_result_table: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    #: Источник данных: «МЮ_бс», «МФЦА», «ПО», «ДЦБ», «СФМ_ФМ1», «ЭСФ_связи», …
    source: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    #: Балл приоритетности (0 — балл не присваивается)
    priority_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Участвует ли алгоритм в расчёте реестра
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Номер версии, увеличивается при каждом изменении SQL
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # --- служебные поля, не влияющие на логику выявления БС ---
    #: Коды алгоритмов, которые должны быть рассчитаны раньше
    #: (БС-11 читает результаты БС-1 и БС-3, БС-13 и БС-17 — результаты других алгоритмов)
    depends_on: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    #: Порядок расчёта и отображения
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Итоги последнего запуска — показываются в интерфейсе управления алгоритмами
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[Optional[str]] = mapped_column(String(16))
    last_row_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    history: Mapped[List["BsAlgorithmHistory"]] = relationship(
        back_populates="algorithm",
        cascade="all, delete-orphan",
        order_by="BsAlgorithmHistory.changed_at.desc()",
    )

    @property
    def depends_on_list(self) -> List[str]:
        return [code.strip() for code in self.depends_on.split(",") if code.strip()]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BsAlgorithm {self.code} {self.name!r} v{self.version}>"


class BsAlgorithmHistory(Base):
    """Предыдущие версии SQL алгоритма."""

    __tablename__ = "bs_algorithm_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    algorithm_id: Mapped[int] = mapped_column(
        ForeignKey("bs_algorithms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Старый SQL код (тот, что действовал до изменения)
    sql_script: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Причина изменения
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    #: Служебное: номер версии и автор правки
    version: Mapped[Optional[int]] = mapped_column(Integer)
    changed_by: Mapped[Optional[str]] = mapped_column(String(64))

    algorithm: Mapped["BsAlgorithm"] = relationship(back_populates="history")
