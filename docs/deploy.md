# Развёртывание на 10.10.31.35, порт 8020

Сервер: Linux amd64, интернета нет. Всё необходимое переносится готовым.

nginx **не нужен**: приложение само раздаёт интерфейс и API на одном порту 8020.

---

## Важно: версия Python

Пакеты собраны под **Python 3.11** (`cp311`, `manylinux2014_x86_64`).
Проверьте версию на сервере:

```bash
python3 --version
```

Если она отличается — комплект нужно пересобрать на машине с интернетом
одной командой (подставьте нужную версию):

```bash
pip download -r backend/requirements.txt -d backend/wheels \
    --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:
pip download "uvloop>=0.19.0" -d backend/wheels \
    --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: --no-deps
```

`uvloop` качается отдельно: при сборке комплекта на Windows он отбрасывается
маркером окружения, а на Linux `uvicorn[standard]` его требует.

---

## 1. Что перенести на сервер

Каталог проекта целиком, включая два подготовленных заранее артефакта:

| Что | Зачем | Объём |
|---|---|---|
| `backend/` | приложение | — |
| `backend/wheels/` | 39 пакетов Python под Linux amd64 | 24 МБ |
| `backend/app/static/swagger/` | локальная копия Swagger UI | 1,6 МБ |
| `frontend/dist/` | **собранный** интерфейс | 270 КБ |
| `docs/` | документация | — |

`frontend/node_modules` переносить **не нужно** — интерфейс уже собран,
`dist/` это обычная статика, не зависящая от ОС. Node.js на сервере не требуется.

Обратите внимание: `backend/wheels/` и `frontend/dist/` перечислены
в `.gitignore` как артефакты сборки. При переносе архивом это неважно,
но если переносите через git — добавьте их принудительно (`git add -f`).

```bash
tar czf reestr_bs.tar.gz --exclude=node_modules --exclude=.venv --exclude=__pycache__ reestr_bs/
```

---

## 2. PostgreSQL

```bash
sudo -u postgres psql -f backend/sql/01_create_database.sql
```

Перед выполнением замените `CHANGE_ME` на реальный пароль.

Схему таблиц приложение создаёт само при первом старте. Развернуть заранее
или сверить вручную:

```bash
psql -U bs_registry -d bs_registry -f backend/sql/02_create_tables.sql
```

---

## 3. Приложение

```bash
cd /opt/reestr_bs/backend

python3 -m venv .venv
source .venv/bin/activate
pip install --no-index --find-links=./wheels -r requirements.txt

cp .env.example .env
```

Заполнить в `.env`:

| Параметр | Значение |
|---|---|
| `SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | пароль роли `bs_registry` |
| `FIRST_SUPERUSER_PASSWORD` | пароль первичного администратора |
| `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` | учётные данные ClickHouse |

Уже проставлены и менять не нужно: `PORT=8020`,
`OLLAMA_MODEL=qwen3.5-122b`, `FRONTEND_DIST=../frontend/dist`.

Оставьте `DATABASE_URL` пустым — иначе вместо PostgreSQL будет использован SQLite.

Проверочный запуск:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8020
```

В журнале при старте должны быть строки:

```
Интерфейс раздаётся из /opt/reestr_bs/frontend/dist
ИИ Qwen:    http://192.168.97.8:11434 (qwen3.5-122b)
ClickHouse доступен, версия ...
Поле category берётся из ...
```

---

## 4. systemd

`/etc/systemd/system/reestr-bs.service`:

```ini
[Unit]
Description=Реестр БС — система выявления бенефициарных собственников
After=network.target postgresql.service

[Service]
Type=simple
User=reestr
WorkingDirectory=/opt/reestr_bs/backend
Environment="PATH=/opt/reestr_bs/backend/.venv/bin"
ExecStart=/opt/reestr_bs/backend/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8020 --workers 4 --timeout-keep-alive 120
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reestr-bs
sudo journalctl -u reestr-bs -f
```

Открыть порт, если включён firewall:

```bash
sudo firewall-cmd --add-port=8020/tcp --permanent && sudo firewall-cmd --reload
# либо
sudo ufw allow 8020/tcp
```

Логи приложения дополнительно пишутся в `backend/logs/`:
`app.log` — общий, `algorithms.log` — выполнение алгоритмов.

---

## 5. Проверка

| Адрес | Что должно быть |
|---|---|
| `http://10.10.31.35:8020` | страница входа |
| `http://10.10.31.35:8020/api/docs` | документация API (Swagger работает без интернета) |
| `http://10.10.31.35:8020/api/health` | `status: ok`, все три системы доступны |

Проверить имя модели на сервере ИИ:

```bash
curl http://192.168.97.8:11434/api/tags
```

Значение `OLLAMA_MODEL` в `.env` должно совпадать с именем из этого ответа
буква в букву — `qwen3.5-122b`.

---

## 6. Первый запуск

1. Войти администратором (логин и пароль из `FIRST_SUPERUSER*`).
2. Раздел **Алгоритмы** — таблица заполнена 14 алгоритмами из ТЗ.
3. Запускать по одному, начиная с независимых: БС-1, БС-2, БС-3, БС-4, БС-22.
   Так сразу видно, какой именно алгоритм упал и на чём.
4. Затем зависимые: БС-11, БС-13, БС-17 — они читают результаты предыдущих.
5. Остальные: БС-6, БС-7, БС-8, БС-9, БС-10, БС-16.
6. После проверки — «Пересчитать всё» для полного прогона в правильном порядке.

**По времени:** БС-13 читает ЭСФ (~485 млн строк) и выполняется часами.
Остальные — от секунд до десятков минут. Модель на 122 млрд параметров
отвечает небыстро, поэтому `OLLAMA_TIMEOUT` выставлен в 600 секунд.

---

## 7. Настройка ClickHouse

Тяжёлым алгоритмам нужна выгрузка промежуточных данных на диск. Клиент передаёт
эти настройки в каждом запросе, но их стоит закрепить и в профиле пользователя
на сервере ClickHouse:

```xml
<max_execution_time>1800</max_execution_time>
<max_memory_usage>32000000000</max_memory_usage>
<max_bytes_before_external_group_by>8000000000</max_bytes_before_external_group_by>
<max_bytes_before_external_sort>8000000000</max_bytes_before_external_sort>
<join_algorithm>partial_merge,hash</join_algorithm>
```

Учётной записи нужны права `CREATE TABLE`, `CREATE VIEW`, `DROP` в базе
`AFM_6_TEST` и чтение остальных баз.

---

## 8. Обновление алгоритма без перезапуска

SQL хранится в PostgreSQL, поэтому правка применяется сразу:

1. **Алгоритмы** → «Изменить» → отредактировать SQL → «Сохранить и выполнить».
   Прежняя версия уходит в `bs_algorithm_history`, номер версии растёт.
2. Либо «ИИ» → описать новое требование → проверить diff → «Одобрить и выполнить».
3. Откат: `POST /api/algorithms/{code}/rollback/{id}`.

Файлы в `backend/app/algorithms/sql/` — только начальное заполнение при первом
старте и эталон для сверки; на работающую систему они не влияют.

---

## 9. Обновление интерфейса

Интерфейс собирается на машине с Node.js и переносится готовым:

```bash
cd frontend
npm run build          # результат в dist/
```

Затем заменить `frontend/dist` на сервере и перезапустить службу
(перезапуск нужен только чтобы сбросить кеш отдачи файлов).

---

## 10. Режим разработки

Если понадобится дорабатывать интерфейс с горячей перезагрузкой, на машине
разработчика поднимаются два процесса:

```bash
# бэкенд
cd backend && uvicorn app.main:app --port 8020

# интерфейс
cd frontend
VITE_BACKEND_URL=http://127.0.0.1:8020 npm run dev
```

Интерфейс будет на `http://localhost:5173`, запросы `/api` проксируются
на 8020. Адрес `localhost:5173` уже указан в `CORS_ORIGINS`.
