"""Пользователи системы.

В системе две роли:
  administrator — полный доступ, включая управление алгоритмами и пересчёт;
  user          — просмотр данных и работа с чатом Qwen.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class UserRole(str, enum.Enum):
    ADMINISTRATOR = "administrator"
    USER = "user"


class BsUser(Base):
    __tablename__ = "bs_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    #: administrator | user
    role: Mapped[str] = mapped_column(String(16), default=UserRole.USER.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- служебные поля ---
    full_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def is_administrator(self) -> bool:
        return self.role == UserRole.ADMINISTRATOR.value

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BsUser {self.username} ({self.role})>"
