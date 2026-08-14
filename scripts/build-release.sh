#!/usr/bin/env bash
# =============================================================================
# Сборка комплекта поставки «Реестр БС».
#
# Выполняется на машине С ИНТЕРНЕТОМ и с установленным Docker.
# Результат — один архив, который переносится на сервер 10.10.31.35.
#
#   ./scripts/build-release.sh          # версия 1.0.0
#   ./scripts/build-release.sh 1.1.0    # своя версия
# =============================================================================

set -euo pipefail

VERSION="${1:-1.0.0}"
APP_IMAGE="reestr-bs:${VERSION}"
PG_IMAGE="postgres:16-alpine"
BUNDLE="reestr-bs-${VERSION}"

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT="${ROOT}/dist-release/${BUNDLE}"

# --- Проверка готовности Docker ---------------------------------------------
command -v docker >/dev/null 2>&1 || {
    echo "Docker не найден. Установите Docker и повторите." >&2
    exit 1
}
docker info >/dev/null 2>&1 || {
    echo "Docker установлен, но демон не запущен." >&2
    exit 1
}

# Сервер 10.10.31.35 — linux/amd64. Архитектура указывается явно, чтобы образ
# не собрался под архитектуру машины сборки (например, ARM-ноутбука).
# --provenance/--sbom отключены намеренно: иначе buildx добавляет к образу
# манифест вложений, и docker load на сервере со старой версией Docker
# может его не принять. Нужен простой манифест под одну платформу.
echo "==> Сборка образа ${APP_IMAGE} (linux/amd64)"
docker build --platform linux/amd64 --provenance=false --sbom=false -t "${APP_IMAGE}" .

echo "==> Загрузка образа PostgreSQL ${PG_IMAGE}"
docker pull --platform linux/amd64 "${PG_IMAGE}"

echo "==> Подготовка комплекта"
rm -rf "${ROOT}/dist-release"
mkdir -p "${OUT}"

echo "==> Экспорт образов в images.tar (это занимает несколько минут)"
docker save "${APP_IMAGE}" "${PG_IMAGE}" -o "${OUT}/images.tar"

cp "${ROOT}/docker-compose.yml" "${OUT}/"
cp "${ROOT}/.env.example" "${OUT}/"
# Имя латиницей — для единообразия со сборкой на Windows
cp "${ROOT}/docs/deploy-docker.md" "${OUT}/INSTALL.md"

# Версия образа фиксируется в комплекте, чтобы compose не искал другую
sed -i.bak "s/^VERSION=.*/VERSION=${VERSION}/" "${OUT}/.env.example" && rm -f "${OUT}/.env.example.bak"

# Архив без сжатия и без вложенного каталога: слои образов уже сжаты,
# gzip экономит около 2 МБ из 188, а распаковка становится на шаг короче.
# Файлы ложатся прямо в текущий каталог — сразу можно делать docker load.
echo "==> Упаковка архива"
tar cf "${ROOT}/${BUNDLE}.tar" -C "${ROOT}/dist-release/${BUNDLE}" .

SIZE=$(du -h "${ROOT}/${BUNDLE}.tar" | cut -f1)
HASH=$(sha256sum "${ROOT}/${BUNDLE}.tar" | cut -d' ' -f1)

cat <<INFO

=============================================================
 Комплект готов: ${BUNDLE}.tar  (${SIZE})
 SHA256: ${HASH}

 Внутри:
   images.tar          образы приложения и PostgreSQL
   docker-compose.yml  описание запуска
   .env.example        шаблон конфигурации
   INSTALL.md          инструкция

 Перенести на сервер и выполнить:
   mkdir -p ~/reestr-bs && cd ~/reestr-bs
   tar xf ~/${BUNDLE}.tar
   docker load -i images.tar
   cp .env.example .env && nano .env
   docker compose up -d
=============================================================
INFO
