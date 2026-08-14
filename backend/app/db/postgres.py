"""Подключение к PostgreSQL (метаданные алгоритмов, пользователи, аудит).

БД разворачивается локально на бэкенд-сервере 10.10.31.35.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict

from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.settings_service import runtime

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Базовый класс моделей."""


def current_dsn() -> str:
    """Строка подключения из действующих настроек.

    DATABASE_URL (режим локального запуска на SQLite) имеет приоритет:
    в этом режиме параметры PostgreSQL из интерфейса не применяются.
    """
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return (
        f"postgresql+asyncpg://{runtime.get('POSTGRES_USER')}:{runtime.get('POSTGRES_PASSWORD')}"
        f"@{runtime.get('POSTGRES_HOST')}:{runtime.get('POSTGRES_PORT')}/{runtime.get('POSTGRES_DB')}"
    )


def _create_engine() -> AsyncEngine:
    dsn = current_dsn()

    # SQLite не поддерживает параметры пула соединений — они применимы
    # только к PostgreSQL. SQLite используется исключительно для локального
    # запуска без развёрнутой PostgreSQL.
    if settings.is_sqlite:
        logger.warning(
            "Метаданные хранятся в SQLite (%s) — режим локального запуска. "
            "В продуктивном контуре должна использоваться PostgreSQL.",
            dsn,
        )
        return create_async_engine(dsn, echo=settings.DEBUG)

    return create_async_engine(
        dsn,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine: AsyncEngine = _create_engine()
#: Строка подключения, на которой создан текущий пул — для сверки при изменении настроек
_active_dsn: str = current_dsn()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: сессия на запрос."""
    # Параметры подключения мог изменить другой воркер uvicorn —
    # сверяем строку подключения перед выдачей сессии
    if current_dsn() != _active_dsn:
        await reconfigure_engine()

    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def reconfigure_engine() -> None:
    """Пересоздаёт пул соединений после изменения параметров PostgreSQL.

    Запросы, начатые до вызова, доработают на прежнем пуле — он закрывается
    после их завершения.
    """
    global engine, SessionLocal, _active_dsn

    new_dsn = current_dsn()
    if new_dsn == _active_dsn:
        return

    old_engine = engine
    engine = _create_engine()
    _active_dsn = new_dsn
    SessionLocal.configure(bind=engine)

    try:
        await old_engine.dispose()
    except Exception as exc:  # noqa: BLE001 — закрытие старого пула не должно ронять запрос
        logger.warning("Прежний пул соединений закрыт с ошибкой: %s", exc)

    logger.info("Пул соединений PostgreSQL пересоздан по новым настройкам")


async def test_connection(
    host: str,
    port: Any,
    database: str,
    user: str,
    password: str,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Проверяет подключение к PostgreSQL указанными параметрами.

    Исключения наружу не выбрасываются: возвращается либо
    ``{"ok": True, "version": ...}``, либо ``{"ok": False, "error": "Тип: текст"}``.
    Соединение открывается только для чтения.
    """
    import asyncpg  # локальный импорт: нужен лишь для проверки

    connection = None
    try:
        connection = await asyncio.wait_for(
            asyncpg.connect(
                host=str(host),
                port=int(port),
                user=str(user),
                password=str(password),
                database=str(database),
                server_settings={"default_transaction_read_only": "on"},
            ),
            timeout=timeout,
        )
        version = await connection.fetchval("SELECT version()")
        return {
            "ok": True,
            "version": str(version or "").split(" on ")[0],
            "message": f"Подключение установлено: {str(version or '').split(' on ')[0]}",
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"Таймаут подключения: {host}:{port} не ответил за {timeout:.0f} с"}
    except Exception as exc:  # noqa: BLE001 — наружу отдаём строку, а не исключение
        name = type(exc).__name__
        text = str(exc).strip() or name
        # Пароль в текст ошибки не попадает: asyncpg его не подставляет
        if "password authentication failed" in text.lower():
            return {"ok": False, "error": f"Доступ запрещён: неверный пользователь или пароль ({name})"}
        if "does not exist" in text.lower():
            return {"ok": False, "error": f"База или роль не найдены: {text[:200]}"}
        if isinstance(exc, OSError):
            return {"ok": False, "error": f"Сеть недоступна: {host}:{port} — {text[:200]}"}
        return {"ok": False, "error": f"{name}: {text[:300]}"}
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # noqa: BLE001
                pass


async def init_db() -> None:
    """Создаёт таблицы метаданных при первом старте.

    Приложение запускается несколькими воркерами uvicorn, и на пустой базе
    они выполняют создание схемы одновременно: каждый проверяет наличие таблиц
    и не находит их. Проигравший гонку получает ошибку «таблица уже существует»,
    и это штатная ситуация, а не сбой.
    """
    from app import models  # noqa: F401  — регистрация моделей в метаданных

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except (ProgrammingError, IntegrityError) as exc:
        logger.info("Схема создана другим процессом приложения (%s)", type(exc).__name__)
        return

    logger.info("Схема PostgreSQL проверена/создана")


async def close_db() -> None:
    await engine.dispose()
