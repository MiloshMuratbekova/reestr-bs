"""Зависимости FastAPI: сессия БД, текущий пользователь, проверка роли."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.postgres import get_session
from app.models import BsUser, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


#: Кем представляются запросы, когда вход отключён (AUTH_ENABLED=false).
#: Объект не сохраняется в базу — он нужен лишь для того, чтобы маршруты,
#: ожидающие пользователя, продолжали работать без переписывания.
def _service_user() -> BsUser:
    return BsUser(
        username="служебный доступ",
        password_hash="",
        role=UserRole.ADMINISTRATOR.value,
        full_name="Вход отключён (AUTH_ENABLED=false)",
        is_active=True,
    )


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)] = None,
) -> BsUser:
    # Вход отключён — пропускаем всех. Проверка стоит здесь, в единственной
    # точке, через которую проходят все защищённые маршруты, поэтому саму
    # авторизацию из них вырезать не потребовалось.
    if not settings.AUTH_ENABLED:
        return _service_user()

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Срок действия сессии истёк. Войдите заново.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        await session.execute(select(BsUser).where(BsUser.username == payload["sub"]))
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или заблокирован",
        )
    return user


CurrentUser = Annotated[BsUser, Depends(get_current_user)]


async def require_administrator(user: CurrentUser) -> BsUser:
    if user.role != UserRole.ADMINISTRATOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Действие доступно только администратору.",
        )
    return user


AdminUser = Annotated[BsUser, Depends(require_administrator)]
