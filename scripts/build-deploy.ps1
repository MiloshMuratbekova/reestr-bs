# =============================================================================
# Реестр БС — сборка комплекта поставки для изолированного сервера 10.10.31.35
#
# Выполняется на рабочей машине С ИНТЕРНЕТОМ и с установленным Docker.
# Результат — один файл reestr-bs-deploy.tar.
#
#   .\scripts\build-deploy.ps1
#   .\scripts\build-deploy.ps1 -Version 1.1
# =============================================================================

param(
    [string]$Version = "1.0"
)

$ErrorActionPreference = "Stop"

$AppImage = "reestr-bs:$Version"
$PgImage  = "postgres:16"
$Bundle   = "reestr-bs-deploy.tar"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Stage = Join-Path $Root "dist-release\bundle"

# Запись без метки порядка байт (BOM).
# В Windows PowerShell 5.1 «Set-Content -Encoding utf8» ставит в начало файла
# EF BB BF. Для .env это означает, что первая строка достаётся парсеру вместе
# с меткой, а для docker-compose.yml — что YAML начинается с невидимых байт.
# На сервере с Linux это ломает разбор, хотя в редакторе файл выглядит целым.
function Write-PlainUtf8([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# Чтение тоже должно быть явным. «Get-Content -Raw» без -Encoding в
# PowerShell 5.1 принимает UTF-8-файл без метки за однобайтовую кодировку,
# и русские комментарии превращаются в мусор ещё до записи.
function Read-PlainUtf8([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, (New-Object System.Text.UTF8Encoding($false)))
}

# --- Проверка готовности Docker -------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker не найден. Установите Docker Desktop и повторите."
}
docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker установлен, но демон не запущен. Запустите Docker Desktop."
}

# --- 1. Образ приложения ---------------------------------------------------
# --provenance/--sbom обязательны: без них buildx добавляет к образу манифест
# вложений, и docker load на сервере его не принимает.
# --load кладёт результат в локальное хранилище образов, откуда его берёт docker save.
Write-Host "==> Сборка образа $AppImage (linux/amd64)" -ForegroundColor Cyan
docker build --platform linux/amd64 --provenance=false --sbom=false --load -t $AppImage .
if ($LASTEXITCODE -ne 0) { throw "Сборка образа завершилась ошибкой" }

Write-Host "==> Загрузка образа $PgImage" -ForegroundColor Cyan
docker pull --platform linux/amd64 $PgImage
if ($LASTEXITCODE -ne 0) { throw "Не удалось загрузить $PgImage" }

# --- 2. Проверка содержимого ОБРАЗА, а не рабочей папки --------------------
# Локальная сборка и то, что реально попало в образ, расходятся чаще, чем кажется.
Write-Host "==> Проверка содержимого образа" -ForegroundColor Cyan
$checks = @(
    @{ Name = "Python";           Cmd = "python --version" },
    @{ Name = "uvicorn";          Cmd = "python -c 'import uvicorn; print(uvicorn.__version__)'" },
    @{ Name = "интерфейс собран"; Cmd = "ls -1 /app/frontend/dist/index.html" },
    @{ Name = "Swagger локально"; Cmd = "ls -1 /app/app/static/swagger/swagger-ui-bundle.js" },
    @{ Name = "SQL алгоритмов";   Cmd = "ls -1 /app/app/algorithms/sql/ | wc -l" },
    @{ Name = "каталог настроек"; Cmd = "ls -d /app/data" },
    @{ Name = "пользователь";     Cmd = "id -un" }
)
foreach ($check in $checks) {
    $out = (docker run --rm --entrypoint sh $AppImage -c $check.Cmd 2>&1 | Out-String).Trim()
    "{0,-22} {1}" -f $check.Name, $out
}

# --- 3. Каталог комплекта --------------------------------------------------
Write-Host "==> Подготовка комплекта" -ForegroundColor Cyan
if (Test-Path "$Root\dist-release") { Remove-Item "$Root\dist-release" -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

# --- 4. Образы одним архивом ------------------------------------------------
Write-Host "==> Экспорт образов (несколько минут)" -ForegroundColor Cyan
$imagesTar = Join-Path $Stage "images.tar"
docker save $AppImage $PgImage -o $imagesTar
if ($LASTEXITCODE -ne 0) { throw "Экспорт образов завершился ошибкой" }

Write-Host "==> Сжатие images.tar.gz" -ForegroundColor Cyan
$imagesGz = Join-Path $Stage "images.tar.gz"
$in  = [System.IO.File]::OpenRead($imagesTar)
$out = [System.IO.File]::Create($imagesGz)
$gz  = New-Object System.IO.Compression.GZipStream($out, [System.IO.Compression.CompressionLevel]::Optimal)
try { $in.CopyTo($gz) } finally { $gz.Dispose(); $out.Dispose(); $in.Dispose() }
Remove-Item $imagesTar -Force

# --- 5. Конфигурация с сгенерированными секретами --------------------------
Write-Host "==> Копирование .env" -ForegroundColor Cyan
# Пароли постоянные и лежат в .env.example. Генерация убрана намеренно:
# новый пароль на каждой сборке ломал уже развёрнутую базу — PostgreSQL
# задаёт его только при создании тома и дальше держит старый.
Copy-Item "$Root\.env.example" (Join-Path $Stage ".env")

Copy-Item "$Root\docker-compose.yml"    $Stage
Copy-Item "$Root\docker-compose.v2.yml" $Stage
Copy-Item "$Root\docs\README-DEPLOY.md" $Stage

# Тег образа в compose должен совпадать с тем, что реально собран. Иначе на
# сервере compose не найдёт образ локально и полезет за ним в интернет,
# которого там нет. Раньше версия подставлялась только в docker build,
# а в compose оставалась прежней — и бандл выходил нерабочим.
Write-Host "==> Простановка версии $Version в compose" -ForegroundColor Cyan
foreach ($file in @("docker-compose.yml", "docker-compose.v2.yml")) {
    $path = Join-Path $Stage $file
    $text = Read-PlainUtf8 $path
    $text = $text -replace 'image:\s*reestr-bs:[^\s]+', "image: $AppImage"
    Write-PlainUtf8 $path $text
}
# Проверка: собранный тег обязан присутствовать в обоих файлах
foreach ($file in @("docker-compose.yml", "docker-compose.v2.yml")) {
    if (-not (Select-String -Path (Join-Path $Stage $file) -Pattern ([regex]::Escape("image: $AppImage")) -Quiet)) {
        throw "В $file не проставился образ $AppImage"
    }
}

# README попадает на сервер как единственная инструкция, и версия в нём
# указана явно. Без подстановки шаг «docker load» обещает не тот тег, что
# реально в образе, — расхождение всплывает уже в закрытом контуре.
$readmePath = Join-Path $Stage "README-DEPLOY.md"
$readmeText = Read-PlainUtf8 $readmePath
$readmeText = $readmeText -replace 'reestr-bs:[0-9][0-9.]*', $AppImage
Write-PlainUtf8 $readmePath $readmeText
if (-not (Select-String -Path $readmePath -Pattern ([regex]::Escape($AppImage)) -Quiet)) {
    throw "В README-DEPLOY.md не проставился образ $AppImage"
}

# --- 6. Бандл ---------------------------------------------------------------
Write-Host "==> Упаковка $Bundle" -ForegroundColor Cyan
tar -cf "$Root\$Bundle" -C $Stage .
if ($LASTEXITCODE -ne 0) { throw "Упаковка бандла завершилась ошибкой" }

$archive = Get-Item "$Root\$Bundle"
$size = "{0:N0} МБ" -f ($archive.Length / 1MB)
$hash = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash.ToLower()

Write-Host @"

=============================================================
 Комплект готов: $Bundle  ($size)
 SHA256: $hash

 Образы в архиве: $AppImage, $PgImage

 Вход в интерфейс отключён (AUTH_ENABLED=false в .env).
 Если включить AUTH_ENABLED=true — вход admin / admin, дальше пароль
 меняется в интерфейсе: кнопка «Сменить пароль» или раздел «Пользователи».

 На сервере (там установлен docker-compose 1.x):
   scp $Bundle user@10.10.31.35:/tmp/
   ssh user@10.10.31.35
   cd ~/reestr-bs && tar -xf /tmp/$Bundle
   docker load -i images.tar.gz
   docker-compose -p reestr-bs up -d
   docker-compose -p reestr-bs ps
=============================================================
"@ -ForegroundColor Green
