"""Проверка доступности смежных систем."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings
from app.db.clickhouse import ClickHouseError, clickhouse, current_url
from app.services.ai_service import ollama
from app.services.settings_service import runtime

router = APIRouter(tags=["Служебное"])


@router.get("/health", summary="Состояние системы")
async def health(session: SessionDep) -> dict:
    clickhouse_ok = await clickhouse.ping()
    clickhouse_version = ""
    if clickhouse_ok:
        try:
            info = await clickhouse.server_info()
            clickhouse_version = info.get("version", "")
        except ClickHouseError:
            clickhouse_ok = False

    try:
        await session.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:  # noqa: BLE001 — состояние показываем, а не пробрасываем
        postgres_ok = False

    ollama_ok = await ollama.ping()

    # Адреса берутся из действующих настроек, а не из переменных окружения:
    # сохранённые через интерфейс значения сильнее
    return {
        "status": "ok" if (clickhouse_ok and postgres_ok) else "degraded",
        # Интерфейс по этому признаку прячет запуск алгоритмов и пересчёт:
        # в режиме чтения они всё равно будут отклонены сервером
        "readonly": settings.CLICKHOUSE_READONLY,
        "clickhouse": {
            "available": clickhouse_ok,
            "url": current_url(),
            "version": clickhouse_version,
        },
        "postgres": {
            "available": postgres_ok,
            "database": settings.DATABASE_URL or runtime.get("POSTGRES_DB"),
        },
        "ai": {
            "available": ollama_ok,
            "url": runtime.get("OLLAMA_BASE_URL"),
            "model": runtime.get("OLLAMA_MODEL"),
            "api_kind": runtime.get("LLM_API_KIND"),
        },
    }
