# =============================================================================
# Сборка комплекта поставки «Реестр БС» на Windows.
#
# Выполняется на машине С ИНТЕРНЕТОМ и с установленным Docker Desktop.
#
#   .\scripts\build-release.ps1
#   .\scripts\build-release.ps1 -Version 1.1.0
# =============================================================================

param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$AppImage = "reestr-bs:$Version"
$PgImage  = "postgres:16-alpine"
$Bundle   = "reestr-bs-$Version"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Out = Join-Path $Root "dist-release\$Bundle"

# --- Проверка готовности Docker -------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker не найден. Установите Docker Desktop и повторите."
}
docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker установлен, но демон не запущен. Запустите Docker Desktop и дождитесь статуса Running."
}

# Сервер 10.10.31.35 — linux/amd64. Архитектура указывается явно, чтобы образ
# не собрался под архитектуру машины сборки.
# --provenance/--sbom отключены намеренно: иначе buildx добавляет к образу
# манифест вложений, и docker load на сервере со старой версией Docker
# может его не принять. Нужен простой манифест под одну платформу.
Write-Host "==> Сборка образа $AppImage (linux/amd64)" -ForegroundColor Cyan
docker build --platform linux/amd64 --provenance=false --sbom=false -t $AppImage .
if ($LASTEXITCODE -ne 0) { throw "Сборка образа завершилась ошибкой" }

Write-Host "==> Загрузка образа PostgreSQL $PgImage" -ForegroundColor Cyan
docker pull --platform linux/amd64 $PgImage
if ($LASTEXITCODE -ne 0) { throw "Не удалось загрузить $PgImage" }

Write-Host "==> Подготовка комплекта" -ForegroundColor Cyan
if (Test-Path "$Root\dist-release") { Remove-Item "$Root\dist-release" -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "==> Экспорт образов в images.tar (несколько минут)" -ForegroundColor Cyan
docker save $AppImage $PgImage -o "$Out\images.tar"
if ($LASTEXITCODE -ne 0) { throw "Экспорт образов завершился ошибкой" }

Copy-Item "$Root\docker-compose.yml" $Out
Copy-Item "$Root\.env.example" $Out
# Имя латиницей: кириллица в tar на Windows записывается в кодировке,
# которую Linux разбирает как мусор
Copy-Item "$Root\docs\deploy-docker.md" "$Out\INSTALL.md"

# Версия образа фиксируется в комплекте
$envPath = Join-Path $Out ".env.example"
(Get-Content $envPath -Raw) -replace '(?m)^VERSION=.*', "VERSION=$Version" |
    Set-Content $envPath -Encoding utf8

# Архив без сжатия и без вложенного каталога: слои образов уже сжаты,
# gzip экономит около 2 МБ из 188, а распаковка становится на шаг короче.
# Файлы ложатся прямо в текущий каталог — сразу можно делать docker load.
Write-Host "==> Упаковка архива" -ForegroundColor Cyan
tar cf "$Root\$Bundle.tar" -C "$Root\dist-release\$Bundle" .
if ($LASTEXITCODE -ne 0) { throw "Упаковка архива завершилась ошибкой" }

$archive = Get-Item "$Root\$Bundle.tar"
$size = "{0:N0} МБ" -f ($archive.Length / 1MB)
$hash = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash.ToLower()

Write-Host @"

=============================================================
 Комплект готов: $Bundle.tar  ($size)
 SHA256: $hash

 Перенести на сервер и выполнить:
   mkdir -p ~/reestr-bs && cd ~/reestr-bs
   tar xf ~/$Bundle.tar
   docker load -i images.tar
   cp .env.example .env && nano .env
   docker compose up -d
=============================================================
"@ -ForegroundColor Green
