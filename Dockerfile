# =============================================================================
# Реестр БС — образ приложения
#
# Один контейнер отдаёт и API, и интерфейс на порту 8020.
# Собирается на машине с интернетом, на сервер переносится через docker save.
#
#   docker build -t reestr-bs:1.0.0 .
# =============================================================================

# ---------- Этап 1: сборка интерфейса ----------
FROM node:20-alpine AS frontend

WORKDIR /build

# Зависимости ставятся отдельным слоем: пока package-lock не менялся,
# при пересборке этот шаг берётся из кеша
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Этап 2: рабочий образ ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Almaty \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8020 \
    LOG_DIR=/app/logs \
    FRONTEND_DIST=/app/frontend/dist \
    DATA_DIR=/app/data

WORKDIR /app

# Шрифт с кириллицей — им печатаются отчёты PDF. Стандартные шрифты PDF
# русских букв не содержат, а шрифт, встроенный в reportlab (Bitstream Vera),
# кириллицы тоже не имеет: файл собирается, но текст выходит пустым.
# Ставится здесь, при сборке на машине с интернетом — в закрытом контуре
# скачать его будет неоткуда.
RUN apt-get update \
    && apt-get install --no-install-recommends -y fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Зависимости — отдельным слоем, до копирования кода
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/sql ./sql
COPY --from=frontend /build/dist ./frontend/dist

# Приложение работает от непривилегированного пользователя.
# /app/data хранит settings.json — настройки, заданные через интерфейс,
# и монтируется томом, чтобы переживать пересоздание контейнера.
RUN useradd --create-home --uid 10001 reestr \
    && mkdir -p /app/logs /app/data \
    && chown -R reestr:reestr /app

USER reestr

EXPOSE 8020

# Проверяется отдача интерфейса: быстрый ответ, не зависящий от ClickHouse и Qwen.
# Обращаться к /api/health здесь нельзя — он ждёт таймауты смежных систем.
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8020/', timeout=8).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020", "--workers", "4", "--timeout-keep-alive", "120"]
