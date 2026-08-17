"""Авторизация и управление пользователями.

Вход по логину и паролю, JWT в заголовке Authorization: Bearer.

Всё, что касается учётных записей, делается здесь и через интерфейс:
создание, смена пароля, роль, блокировка, удаление. Никаких обходных путей
через базу для этого не требуется — раньше пароль задавался только при первом
запуске и потом становился неизменяемым, что упиралось в правку SQL вручную.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models import BsUser, UserRole
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Авторизация"])


@router.get("/mode", summary="Требуется ли вход в систему")
async def mode() -> dict:
    """Открытый эндпоинт: интерфейс спрашивает до входа, нужен ли он вообще.

    Если вход отключён, страница логина не показывается — иначе она бы
    требовала пароль, которого сервер уже не спрашивает.
    """
    return {"auth_enabled": settings.AUTH_ENABLED}


async def _get_user(session: SessionDep, username: str) -> BsUser:
    user = (
        await session.execute(select(BsUser).where(BsUser.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Пользователь {username} не найден")
    return user


async def _count_active_admins(session: SessionDep) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(BsUser)
                .where(
                    BsUser.role == UserRole.ADMINISTRATOR.value,
                    BsUser.is_active.is_(True),
                )
            )
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Свой пароль — доступно любому вошедшему
# ---------------------------------------------------------------------------
@router.post("/change-password", summary="Сменить свой пароль")
async def change_password(
    payload: ChangePasswordRequest, session: SessionDep, user: CurrentUser
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль указан неверно")

    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый пароль совпадает с текущим")

    user.password_hash = hash_password(payload.new_password)
    await session.commit()

    logger.info("Пользователь %s сменил свой пароль", user.username)
    return {"detail": "Пароль изменён"}


# ---------------------------------------------------------------------------
# Управление пользователями — только администратор
# ---------------------------------------------------------------------------
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
async def create_user(payload: UserCreate, session: SessionDep, admin: AdminUser) -> BsUser:
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
    logger.info("%s создал пользователя %s (%s)", admin.username, user.username, user.role)
    return user


@router.patch(
    "/users/{username}",
    response_model=UserOut,
    summary="Изменить пользователя: пароль, роль, блокировка",
)
async def update_user(
    username: str, payload: UserUpdate, session: SessionDep, admin: AdminUser
) -> BsUser:
    user = await _get_user(session, username)

    # Нельзя понизить себя самого. Проверка «остался ли ещё администратор»
    # тут не спасает: пока другие администраторы есть, понижение проходит,
    # и человек мгновенно теряет доступ к разделу, из которого только что
    # нажал кнопку — вернуть роль он уже не может.
    if (
        user.username == admin.username
        and payload.role is not None
        and payload.role != UserRole.ADMINISTRATOR.value
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Нельзя понизить собственную роль — вы сразу потеряете доступ. "
            "Попросите другого администратора.",
        )

    # Нельзя лишить систему последнего действующего администратора:
    # иначе управлять пользователями станет некому и придётся лезть в базу
    losing_admin = (
        user.role == UserRole.ADMINISTRATOR.value
        and user.is_active
        and (
            (payload.role is not None and payload.role != UserRole.ADMINISTRATOR.value)
            or payload.is_active is False
        )
    )
    if losing_admin and await _count_active_admins(session) <= 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Это последний действующий администратор. Сначала назначьте другого.",
        )

    if user.username == admin.username and payload.is_active is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Нельзя заблокировать собственную учётную запись"
        )

    changed = []
    if payload.password:
        user.password_hash = hash_password(payload.password)
        changed.append("пароль")
    if payload.role is not None and payload.role != user.role:
        user.role = payload.role
        changed.append(f"роль на {payload.role}")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None and payload.is_active != user.is_active:
        user.is_active = payload.is_active
        changed.append("разблокирован" if payload.is_active else "заблокирован")

    await session.commit()
    await session.refresh(user)

    if changed:
        logger.info(
            "%s изменил учётную запись %s: %s", admin.username, username, ", ".join(changed)
        )
    return user


@router.delete(
    "/users/{username}",
    status_code=status.HTTP_200_OK,
    summary="Удалить пользователя",
)
async def delete_user(username: str, session: SessionDep, admin: AdminUser) -> dict:
    user = await _get_user(session, username)

    if user.username == admin.username:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Нельзя удалить собственную учётную запись"
        )

    if (
        user.role == UserRole.ADMINISTRATOR.value
        and user.is_active
        and await _count_active_admins(session) <= 1
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Это последний действующий администратор. Сначала назначьте другого.",
        )

    await session.delete(user)
    await session.commit()

    logger.info("%s удалил учётную запись %s", admin.username, username)
    return {"detail": f"Пользователь {username} удалён"}
