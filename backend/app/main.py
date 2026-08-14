"""Точка входа приложения «Реестр БС».

Агентство по финансовому мониторингу Республики Казахстан.
Система работает в закрытом контуре: бэкенд 10.10.31.35,
ClickHouse 192.168.122.45:8123, Qwen через Ollama 192.168.97.8:11434.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.routes import api_router
from app.core.config import settings
from app.core.logging_config import get_logger, setup_logging
from app.core.security import hash_password
from app.db.clickhouse import ClickHouseError, clickhouse, current_url
from app.db.postgres import SessionLocal, close_db, init_db
from app.models import BsUser, UserRole
from app.services import algorithm_service, registry_service
from app.services.ai_service import AiError, ollama

setup_logging()
logger = get_logger(__name__)


async def bootstrap() -> None:
    """Первичная подготовка: схема БД, администратор, каталог алгоритмов.

    Выполняется в каждом воркере uvicorn, поэтому все шаги идемпотентны
    и терпимы к тому, что параллельный процесс успел раньше.
    """
    await init_db()

    async with SessionLocal() as session:
        # Первичный администратор
        admin = (
            await session.execute(
                select(BsUser).where(BsUser.username == settings.FIRST_SUPERUSER)
            )
        ).scalar_one_or_none()

        if admin is None:
            session.add(
                BsUser(
                    username=settings.FIRST_SUPERUSER,
                    password_hash=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
                    role=UserRole.ADMINISTRATOR.value,
                    full_name="Администратор системы",
                )
            )
            try:
                await session.commit()
                logger.info("Создан администратор по умолчанию: %s", settings.FIRST_SUPERUSER)
            except IntegrityError:
                await session.rollback()
                logger.info("Администратор создан другим процессом приложения")

        # Каталог алгоритмов
        created = await algorithm_service.seed_algorithms(session)
        if created == 0:
            logger.info("Каталог алгоритмов уже заполнен")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 70)
    logger.info("Запуск системы «%s»", settings.APP_NAME)
    logger.info("ClickHouse: %s", current_url())
    logger.info("PostgreSQL: %s:%s/%s", settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB)
    logger.info("ИИ Qwen:    %s (%s)", settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    logger.info("=" * 70)

    await clickhouse.connect()
    await ollama.connect()

    try:
        await bootstrap()
    except Exception as exc:  # noqa: BLE001 — приложение должно подняться и показать ошибку
        logger.exception("Первичная подготовка не завершена: %s", exc)

    if await clickhouse.ping():
        try:
            info = await clickhouse.server_info()
            logger.info("ClickHouse доступен, версия %s", info.get("version", "неизвестна"))
            await registry_service.detect_category_source()
        except ClickHouseError as exc:
            logger.error("ClickHouse отвечает, но запрос не выполнен: %s", exc)
    else:
        logger.error("ClickHouse недоступен по адресу %s", current_url())

    try:
        if await ollama.ping():
            logger.info("Сервер ИИ доступен")
        else:
            logger.warning("Сервер ИИ недоступен по адресу %s", settings.OLLAMA_BASE_URL)
    except AiError as exc:
        logger.warning("Проверка сервера ИИ не выполнена: %s", exc)

    yield

    await clickhouse.close()
    await ollama.close()
    await close_db()
    logger.info("Система остановлена")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Интеллектуальная система выявления и анализа бенефициарных собственников "
        "юридических лиц. Агентство по финансовому мониторингу Республики Казахстан."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Штатные страницы документации отключены: они подгружают Swagger UI
    # с внешнего CDN, а контур закрытый. Ниже подключается локальная копия.
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.exception_handler(ClickHouseError)
async def clickhouse_error_handler(request: Request, exc: ClickHouseError) -> JSONResponse:
    """Ошибки хранилища показываются понятным сообщением, а не трассировкой."""
    logger.error("Ошибка ClickHouse на %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": (
                "Ошибка обращения к хранилищу данных ClickHouse. "
                "Проверьте доступность сервера и корректность запроса."
            ),
            "error": str(exc)[:1000],
        },
    )


@app.exception_handler(AiError)
async def ai_error_handler(request: Request, exc: AiError) -> JSONResponse:
    logger.error("Ошибка ИИ на %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


@app.get("/api/docs", include_in_schema=False)
async def swagger_ui() -> object:
    """Документация API на локальной копии Swagger UI, без обращений в интернет."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.APP_NAME} — документация API",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon.png",
    )


# ---------------------------------------------------------------------------
# Раздача собранного интерфейса.
# Приложение отдаёт фронтенд самостоятельно, чтобы в закрытом контуре
# не требовалось разворачивать отдельный веб-сервер.
# ---------------------------------------------------------------------------
_dist = Path(settings.FRONTEND_DIST)
if not _dist.is_absolute():
    _dist = (BASE_DIR.parent / settings.FRONTEND_DIST).resolve()

FRONTEND_READY = (_dist / "index.html").is_file()

if FRONTEND_READY:
    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")
    logger.info("Интерфейс раздаётся из %s", _dist)
else:
    logger.warning(
        "Каталог собранного интерфейса не найден: %s. "
        "Выполните «npm run build» и перенесите dist на сервер.",
        _dist,
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Отдаёт статику интерфейса, остальные пути — на index.html.

    Возврат index.html нужен маршрутизации SPA: адреса вида /company/123
    обрабатываются уже в браузере.
    """
    # Несуществующий метод API не должен получать в ответ HTML-страницу
    if full_path.startswith("api/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Метод API не найден")

    if not FRONTEND_READY:
        return JSONResponse(
            {
                "name": settings.APP_NAME,
                "version": "1.0.0",
                "docs": "/api/docs",
                "detail": "Интерфейс не собран: выполните «npm run build» в каталоге frontend",
            }
        )

    if full_path:
        candidate = (_dist / full_path).resolve()
        # Защита от выхода за пределы каталога dist
        if candidate.is_file() and _dist in candidate.parents:
            return FileResponse(candidate)

    return FileResponse(_dist / "index.html")
