from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    role: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    full_name: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=256)
    role: str = Field(default="user", pattern="^(administrator|user)$")
    full_name: str = ""


class UserUpdate(BaseModel):
    """Изменение учётной записи администратором.

    Передаются только те поля, которые действительно меняются.
    Пустой пароль не трогает существующий.
    """

    password: Optional[str] = Field(default=None, min_length=6, max_length=256)
    role: Optional[str] = Field(default=None, pattern="^(administrator|user)$")
    full_name: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    """Смена собственного пароля.

    Текущий пароль запрашивается намеренно: иначе оставленная без присмотра
    открытая сессия позволяла бы захватить учётную запись.
    """

    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=6, max_length=256)
