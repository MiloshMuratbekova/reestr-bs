"""Асинхронный клиент ClickHouse поверх HTTP-интерфейса (192.168.122.45:8123).

Используется HTTP, а не native-протокол — так требует ТЗ и так проще
в закрытом контуре (не нужен драйвер и открытие порта 9000).

Параметризация запросов выполняется штатным механизмом ClickHouse:
в SQL пишется ``{name:String}``, а значение передаётся как ``param_name``
в query-string. Это исключает SQL-инъекции — значения никогда не
склеиваются со строкой запроса.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.settings_service import runtime

logger = get_logger(__name__)


def current_url() -> str:
    """Адрес ClickHouse из действующих настроек (файл сильнее окружения)."""
    return f"http://{runtime.get('CLICKHOUSE_HOST')}:{runtime.get('CLICKHOUSE_PORT')}"


class ClickHouseError(RuntimeError):
    """Ошибка выполнения запроса в ClickHouse."""

    def __init__(self, message: str, query: str = "", status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.query = query
        self.status_code = status_code


# Запрещённые конструкции для произвольных (в т.ч. сгенерированных ИИ) запросов
_FORBIDDEN_STATEMENTS = re.compile(
    r"\b(INSERT|ALTER|DROP|TRUNCATE|DELETE|UPDATE|CREATE|RENAME|ATTACH|DETACH|"
    r"OPTIMIZE|GRANT|REVOKE|SET\s+|SYSTEM|KILL)\b",
    re.IGNORECASE,
)


def assert_read_only(sql: str) -> None:
    """Проверяет, что запрос не изменяет данные.

    Применяется ко всему, что приходит извне ядра: ad-hoc запросы аналитика
    и SQL, сгенерированный моделью Qwen.
    """
    stripped = _strip_sql_comments(sql).strip()
    if not stripped:
        raise ClickHouseError("Пустой SQL-запрос")

    if ";" in stripped.rstrip(";"):
        raise ClickHouseError("Разрешён только один SQL-оператор в запросе")

    if _FORBIDDEN_STATEMENTS.search(stripped):
        raise ClickHouseError(
            "Запрос отклонён: разрешены только читающие операции (SELECT / WITH / DESCRIBE / SHOW)"
        )

    if not re.match(r"^\s*(SELECT|WITH|DESCRIBE|DESC|SHOW|EXPLAIN)\b", stripped, re.IGNORECASE):
        raise ClickHouseError(
            "Запрос должен начинаться с SELECT, WITH, DESCRIBE, SHOW или EXPLAIN"
        )


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


class ClickHouseClient:
    """Пул-клиент ClickHouse. Один экземпляр на приложение."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""

    # ------------------------------------------------------------------
    async def connect(self) -> None:
        if self._client is not None:
            return
        self._base_url = current_url()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.CLICKHOUSE_TIMEOUT, connect=15.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            verify=settings.CLICKHOUSE_VERIFY_SSL,
        )
        logger.info("ClickHouse клиент инициализирован: %s", self._base_url)

    async def reconfigure(self) -> None:
        """Пересоздаёт соединение после изменения адреса в настройках.

        Вызывается при сохранении настроек, чтобы новый адрес заработал
        без перезапуска контейнера.
        """
        if current_url() == self._base_url and self._client is not None:
            return
        await self.close()
        await self.connect()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("ClickHouse клиент закрыт")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ClickHouseError("ClickHouse клиент не инициализирован")
        return self._client

    # ------------------------------------------------------------------
    def _base_params(self, extra_settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "database": runtime.get("CLICKHOUSE_DATABASE"),
            # Таймаут тяжёлого сканирования — редактируется через интерфейс
            "max_execution_time": runtime.get("CLICKHOUSE_MAX_EXECUTION_TIME"),
            "max_memory_usage": settings.CLICKHOUSE_MAX_MEMORY_USAGE,
            # Большие JOIN-ы алгоритмов (ЭСФ ~485 млн строк) должны переливаться на диск
            "join_algorithm": "partial_merge,hash",
            "max_bytes_before_external_group_by": 8_000_000_000,
            "max_bytes_before_external_sort": 8_000_000_000,
        }
        if extra_settings:
            params.update(extra_settings)
        return params

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        user = runtime.get("CLICKHOUSE_USER")
        password = runtime.get("CLICKHOUSE_PASSWORD")
        if user:
            headers["X-ClickHouse-User"] = str(user)
        if password:
            headers["X-ClickHouse-Key"] = str(password)
        return headers

    @staticmethod
    def _bind(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Переводит словарь значений в формат ``param_<name>`` ClickHouse."""
        if not params:
            return {}
        bound: Dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, (list, tuple, set)):
                # ClickHouse принимает массивы в формате ['a','b']
                items = ",".join("'" + str(v).replace("'", "\\'") + "'" for v in value)
                bound[f"param_{key}"] = f"[{items}]"
            elif isinstance(value, bool):
                bound[f"param_{key}"] = "1" if value else "0"
            elif value is None:
                bound[f"param_{key}"] = ""
            else:
                bound[f"param_{key}"] = str(value)
        return bound

    # ------------------------------------------------------------------
    async def _post(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        query_settings: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        # Настройки мог изменить другой воркер uvicorn — тогда адрес в файле
        # уже новый, а соединение в этом процессе осталось на старом
        if current_url() != self._base_url:
            await self.reconfigure()

        query_params = self._base_params(query_settings)
        query_params.update(self._bind(params))

        try:
            response = await self.client.post(
                "/",
                params=query_params,
                content=sql.encode("utf-8"),
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise ClickHouseError(
                f"Превышено время ожидания ответа ClickHouse ({settings.CLICKHOUSE_TIMEOUT} с)",
                query=sql,
            ) from exc
        except httpx.HTTPError as exc:
            raise ClickHouseError(f"Сетевая ошибка ClickHouse: {exc}", query=sql) from exc

        if response.status_code != 200:
            text = response.text.strip()
            logger.error("ClickHouse %s: %s", response.status_code, text[:2000])
            raise ClickHouseError(text[:4000], query=sql, status_code=response.status_code)

        return response

    # ------------------------------------------------------------------
    async def fetch_all(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        query_settings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Выполняет SELECT и возвращает список словарей."""
        query = f"{sql.rstrip().rstrip(';')}\nFORMAT JSONEachRow"
        response = await self._post(query, params, query_settings)
        rows: List[Dict[str, Any]] = []
        for line in response.text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    async def fetch_one(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        query_settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        rows = await self.fetch_all(sql, params, query_settings)
        return rows[0] if rows else None

    async def fetch_value(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        default: Any = None,
    ) -> Any:
        row = await self.fetch_one(sql, params)
        if not row:
            return default
        return next(iter(row.values()), default)

    async def fetch_with_meta(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        query_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Возвращает данные вместе с описанием колонок и статистикой.

        Используется для произвольных запросов в интерфейсе аналитика.
        """
        query = f"{sql.rstrip().rstrip(';')}\nFORMAT JSON"
        response = await self._post(query, params, query_settings)
        payload = response.json()
        return {
            "columns": [
                {"name": column["name"], "type": column["type"]}
                for column in payload.get("meta", [])
            ],
            "rows": payload.get("data", []),
            "row_count": payload.get("rows", 0),
            "statistics": payload.get("statistics", {}),
        }

    async def execute(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        query_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Выполняет DDL/DML (CREATE, INSERT, DROP). Возвращает тело ответа."""
        response = await self._post(sql, params, query_settings)
        return response.text

    async def execute_script(
        self,
        statements: Sequence[str],
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Последовательно выполняет несколько операторов."""
        for statement in statements:
            statement = statement.strip().rstrip(";")
            if statement:
                await self.execute(statement, params)

    # ------------------------------------------------------------------
    async def ping(self) -> bool:
        try:
            response = await self.client.get("/ping", timeout=10.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def server_info(self) -> Dict[str, Any]:
        row = await self.fetch_one(
            "SELECT version() AS version, uptime() AS uptime, currentDatabase() AS database"
        )
        return row or {}

    async def table_exists(self, database: str, table: str) -> bool:
        value = await self.fetch_value(
            "SELECT count() FROM system.tables "
            "WHERE database = {db:String} AND name = {tbl:String}",
            {"db": database, "tbl": table},
        )
        return bool(value and int(value) > 0)

    async def table_row_count(self, database: str, table: str) -> int:
        value = await self.fetch_value(
            f"SELECT count() AS cnt FROM {database}.{table}",
            default=0,
        )
        return int(value or 0)


clickhouse = ClickHouseClient()


async def get_clickhouse() -> ClickHouseClient:
    """FastAPI-зависимость."""
    return clickhouse


async def test_connection(
    host: str,
    port: Any,
    database: str = "",
    user: str = "",
    password: str = "",
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Проверяет подключение к ClickHouse указанными параметрами.

    Исключения наружу не выбрасываются: возвращается либо
    ``{"ok": True, "version": ...}``, либо ``{"ok": False, "error": "Тип: текст"}``,
    чтобы интерфейс показал аналитику понятную строку состояния, а не ошибку 500.

    Соединение открывается в режиме readonly=1: проверка не должна иметь
    возможности что-либо изменить в базе.
    """
    url = f"http://{host}:{port}"
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if user:
        headers["X-ClickHouse-User"] = str(user)
    if password:
        headers["X-ClickHouse-Key"] = str(password)

    # В readonly=1 нельзя передавать другие настройки в том же запросе,
    # поэтому список параметров минимальный.
    params: Dict[str, Any] = {"readonly": 1}
    if database:
        params["database"] = database

    try:
        async with httpx.AsyncClient(base_url=url, timeout=timeout) as client:
            response = await client.post(
                "/",
                params=params,
                content=b"SELECT version() AS version, currentDatabase() AS db FORMAT JSONEachRow",
                headers=headers,
            )
    except httpx.ConnectTimeout:
        return {"ok": False, "error": f"Таймаут подключения: {url} не ответил за {timeout:.0f} с"}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Сеть недоступна: не удалось установить соединение с {url}"}
    except httpx.TimeoutException:
        return {"ok": False, "error": f"Таймаут запроса: {url} не ответил за {timeout:.0f} с"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if response.status_code == 401 or response.status_code == 403:
        return {"ok": False, "error": "Доступ запрещён: неверный пользователь или пароль"}
    if response.status_code != 200:
        text = response.text.strip().splitlines()
        message = text[0][:300] if text else f"HTTP {response.status_code}"
        return {"ok": False, "error": f"HTTP {response.status_code}: {message}"}

    try:
        row = json.loads(response.text.splitlines()[0])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "error": "Некорректный ответ сервера ClickHouse"}

    return {
        "ok": True,
        "version": row.get("version", ""),
        "database": row.get("db", ""),
        "message": f"Подключение установлено, ClickHouse {row.get('version', '')}",
    }
