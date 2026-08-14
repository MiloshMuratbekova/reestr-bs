"""Настройки подключений и лимитов.

Все методы доступны только администратору: здесь редактируются адреса баз
и пароли, а также лимиты, влияющие на нагрузку.

Проверки подключений намеренно не выбрасывают исключений наружу —
возвращается признак ok и понятная строка, по которой аналитик сам поймёт,
не тот адрес указан, не пускает по паролю или недоступна сеть.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminUser
from app.core.logging_config import get_logger
from app.db import clickhouse as ch_module
from app.db import postgres as pg_module
from app.schemas.settings import (
    ClickHouseTestRequest,
    ModelsResponse,
    PostgresTestRequest,
    SettingsResponse,
    SettingsUpdate,
    SettingsUpdateResult,
    TestResult,
)
from app.services import ai_service
from app.services.settings_service import runtime

logger = get_logger(__name__)
router = APIRouter(tags=["Настройки"])


@router.get("/settings", response_model=SettingsResponse, summary="Текущие настройки")
async def get_settings(_: AdminUser) -> dict:
    return runtime.public()


@router.post("/settings", response_model=SettingsUpdateResult, summary="Сохранить настройки")
async def save_settings(payload: SettingsUpdate, user: AdminUser) -> dict:
    """Сохраняет настройки и сразу применяет их без перезапуска контейнера."""
    result = runtime.update(payload.values)

    if result["applied"]:
        logger.info(
            "Настройки изменены пользователем %s: %s",
            user.username,
            ", ".join(result["applied"]),
        )
        # Соединения пересоздаются, чтобы новые адреса заработали немедленно
        await ch_module.clickhouse.reconfigure()
        await ai_service.ollama.reconfigure()
        await pg_module.reconfigure_engine()

    public = runtime.public()
    return {
        "applied": result["applied"],
        "ignored": result["ignored"],
        "values": public["values"],
        "source": public["source"],
    }


@router.post("/ch/test", response_model=TestResult, summary="Проверить подключение к ClickHouse")
async def test_clickhouse(payload: ClickHouseTestRequest, _: AdminUser) -> dict:
    # Пустые поля берутся из действующих настроек: чтобы проверить соединение,
    # не требуется повторно вводить пароль
    return await ch_module.test_connection(
        host=payload.host or str(runtime.get("CLICKHOUSE_HOST")),
        port=payload.port or runtime.get("CLICKHOUSE_PORT"),
        database=payload.database or str(runtime.get("CLICKHOUSE_DATABASE") or ""),
        user=payload.user or str(runtime.get("CLICKHOUSE_USER") or ""),
        password=payload.password or str(runtime.get("CLICKHOUSE_PASSWORD") or ""),
    )


@router.post("/db/test", response_model=TestResult, summary="Проверить подключение к PostgreSQL")
async def test_postgres(payload: PostgresTestRequest, _: AdminUser) -> dict:
    return await pg_module.test_connection(
        host=payload.host or str(runtime.get("POSTGRES_HOST")),
        port=payload.port or runtime.get("POSTGRES_PORT"),
        database=payload.database or str(runtime.get("POSTGRES_DB") or ""),
        user=payload.user or str(runtime.get("POSTGRES_USER") or ""),
        password=payload.password or str(runtime.get("POSTGRES_PASSWORD") or ""),
    )


@router.post("/llm/test", response_model=TestResult, summary="Проверить модель")
async def test_llm(_: AdminUser) -> dict:
    """Отправляет модели короткий запрос и показывает её ответ."""
    return await ai_service.test_model()


@router.get("/llm/models", response_model=ModelsResponse, summary="Список моделей сервера ИИ")
async def list_models(_: AdminUser) -> dict:
    """При недоступности сервера возвращает сохранённый перечень.

    Список в интерфейсе остаётся рабочим, и модель можно выбрать вслепую.
    """
    return await ai_service.list_models_safe()
