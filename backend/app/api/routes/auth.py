"""Авторизация: вход, сведения о текущем пользователе, управление учётными записями."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models import BsUser
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Авторизация"])


@router.post("/login", response_model=TokenResponse, summary="Вход в систему")
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = (
        await session.execute(select(BsUser).where(BsUser.username == payload.username))
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        logger.warning("Неудачная попытка входа: %s", payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись заблокирована",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info("Вход в систему: %s (%s)", user.username, user.role)
    return TokenResponse(
        access_token=create_access_token(user.username, user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
async def me(user: CurrentUser) -> BsUser:
    return user


@router.get("/users", response_model=list[UserOut], summary="Список пользователей")
async def list_users(session: SessionDep, _: AdminUser) -> list[BsUser]:
    result = await session.execute(select(BsUser).order_by(BsUser.username))
    return list(result.scalars().all())


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя",
)
async def create_user(payload: UserCreate, session: SessionDep, _: AdminUser) -> BsUser:
    exists = (
        await session.execute(select(BsUser).where(BsUser.username == payload.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Пользователь {payload.username} уже существует",
        )

    user = BsUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Создан пользователь %s с ролью %s", user.username, user.role)
    return user
