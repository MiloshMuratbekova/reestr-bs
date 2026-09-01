"""Конфигурация приложения «Реестр БС».

Все параметры читаются из переменных окружения / файла .env.
Система работает в закрытом контуре — внешних вызовов нет.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------- Приложение ----------------
    APP_NAME: str = "Реестр БС"
    APP_ENV: str = "production"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    HOST: str = "0.0.0.0"
    PORT: int = 8020
    WORKERS: int = 4

    #: Каталог собранного фронтенда. Если он есть, приложение раздаёт интерфейс
    #: само — в закрытом контуре это избавляет от установки nginx.
    FRONTEND_DIST: str = "../frontend/dist"

    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # ---------------- ClickHouse ----------------
    CLICKHOUSE_HOST: str = "192.168.122.45"
    CLICKHOUSE_PORT: int = 8123
    #: Учётная запись ClickHouse. Только чтение: система не создаёт и не
    #: изменяет таблицы в ведомственной базе, она их читает.
    CLICKHOUSE_USER: str = "ai_doa"
    #: Пароль в репозиторий не кладётся. Задаётся на сервере — в .env либо
    #: через Настройки в интерфейсе (хранится в томе, вне git).
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "AFM_6_TEST"
    CLICKHOUSE_TIMEOUT: int = 1800
    CLICKHOUSE_MAX_EXECUTION_TIME: int = 1800
    CLICKHOUSE_MAX_MEMORY_USAGE: int = 32_000_000_000
    CLICKHOUSE_VERIFY_SSL: bool = False

    #: Работать только на чтение. Таблицы результатов алгоритмов ведёт
    #: сама организация, система их не создаёт и не перезаписывает —
    #: она читает готовые и собирает из них реестр.
    #:
    #: Пока включено, недоступны запуск алгоритмов, полный пересчёт
    #: и ночное расписание: все три выполняли CREATE TABLE.
    #: Логика алгоритмов при этом никуда не делась — их SQL остаётся
    #: в интерфейсе как описание критериев отбора.
    CLICKHOUSE_READONLY: bool = True

    # ---------------- PostgreSQL ----------------
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "bs_registry"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "bs_registry"

    #: Прямое указание строки подключения. Задаётся только для локального
    #: запуска без PostgreSQL, например sqlite+aiosqlite:///./local.db
    #: В продуктивном контуре оставлять пустым — используется PostgreSQL.
    DATABASE_URL: str = ""

    # ---------------- Ollama / Qwen ----------------
    OLLAMA_BASE_URL: str = "http://192.168.97.9:11434"
    #: Имя модели ровно как оно зарегистрировано в Ollama — через дефис
    OLLAMA_MODEL: str = "doai-vision2:latest"
    #: Тип API сервера ИИ: «ollama» (нативный) либо «openai» (OpenAI-совместимый)
    LLM_API_KIND: str = "ollama"
    OLLAMA_TIMEOUT: int = 600
    OLLAMA_TEMPERATURE: float = 0.2
    OLLAMA_NUM_CTX: int = 16384
    #: Предельная длина ответа модели в токенах
    LLM_MAX_TOKENS: int = 2048
    #: Сколько запросов к модели выполнять одновременно
    LLM_CONCURRENCY: int = 2
    #: Сколько держать модель загруженной в память после запроса.
    #: По умолчанию Ollama выгружает её через 5 минут, и первый запрос
    #: после паузы платит за повторную загрузку — со стороны выглядит
    #: как таймаут. Для модели на 122 млрд параметров это минуты.
    LLM_KEEP_ALIVE: str = "30m"

    # ---------------- Лимиты выборок ----------------
    #: Максимум строк, возвращаемых одним запросом к ClickHouse
    MAX_ROWS_PER_QUERY: int = 1000
    #: Максимум строк данных, отдаваемых одному клиенту за запрос
    MAX_ROWS_PER_CLIENT: int = 50000

    # ---------------- Хранилище настроек ----------------
    #: Каталог для settings.json. В контейнере смонтирован том.
    DATA_DIR: str = "./data"

    # ---------------- Безопасность ----------------
    #: Требовать вход по логину и паролю.
    #: false — система открыта всем, кто дотянулся до её порта: вход не
    #: запрашивается, все запросы выполняются от имени служебного
    #: администратора. Допустимо только в закрытом контуре без доступа извне.
    #: Код авторизации при этом никуда не делся — чтобы вернуть её,
    #: достаточно поставить AUTH_ENABLED=true в .env и перезапустить.
    AUTH_ENABLED: bool = False

    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "admin"

    #: Аварийный сброс пароля администратора при запуске.
    #: Нужен, когда войти нечем: FIRST_SUPERUSER_PASSWORD применяется только
    #: при создании записи, а том с базой переживает обновление образа.
    #: Порядок: включить, запустить, войти, ВЫКЛЮЧИТЬ и перезапустить.
    #: Пока включён, пароль возвращается к FIRST_SUPERUSER_PASSWORD при
    #: каждом старте — оставлять его включённым нельзя.
    ADMIN_PASSWORD_RESET: bool = False

    # ---------------- Реестр ----------------
    #: База ClickHouse, в которой алгоритмы создают свои таблицы результатов
    REGISTRY_DATABASE: str = "AFM_6_TEST"
    #: Справочники, используемые при сборке итоговой таблицы
    DICT_COMPANIES: str = "AFM_2_1_TEST.AFM_2_1_9"
    DICT_PERSONS: str = "AFM_2_1_TEST.AFM_2_1_10"
    DICT_OWNERSHIP: str = "AFM_2_1.AFM_2_1_8"
    DICT_DOCUMENTS: str = "AFM_2_1.AFM_2_1_59"
    DICT_SHARES: str = "AFM_6_TEST.AFM_6_1_5_1"
    TBL_FOUNDERS: str = "AFM_2_1_TEST.AFM_2_1_5_1"
    TBL_DIRECTORS: str = "AFM_2_1_TEST.AFM_2_1_6_1"

    TIMEZONE: str = "Asia/Almaty"

    # ---------------- Логи ----------------
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"

    # ------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, value: Any) -> Any:
        """Принимает как JSON-список, так и строку через запятую."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ------------------------------------------------------------------
    @property
    def clickhouse_url(self) -> str:
        return f"http://{self.CLICKHOUSE_HOST}:{self.CLICKHOUSE_PORT}"

    @property
    def postgres_dsn(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.postgres_dsn.startswith("sqlite")

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def ollama_generate_url(self) -> str:
        return f"{self.OLLAMA_BASE_URL.rstrip('/')}/api/generate"

    @property
    def ollama_chat_url(self) -> str:
        return f"{self.OLLAMA_BASE_URL.rstrip('/')}/api/chat"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
