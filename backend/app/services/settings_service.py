"""Настройки подключений и лимитов, редактируемые через интерфейс.

Три слоя и порядок приоритета
-----------------------------
1. Значения по умолчанию в коде — читаются из переменных окружения
   (то есть из docker-compose и .env).
2. Файл сохранённых настроек ``data/settings.json`` в томе контейнера.
3. При загрузке берутся умолчания, поверх накладывается файл.

ВНИМАНИЕ, ЧАСТАЯ ПРИЧИНА ПОТЕРИ ВРЕМЕНИ.
Сохранённое через интерфейс СИЛЬНЕЕ значений из docker-compose и .env.
Если адрес поменяли в docker-compose.yml, перезапустили контейнер, а приложение
продолжает ходить по старому адресу — виноват файл ``data/settings.json``.
Смотреть надо туда: либо поправить значение в интерфейсе, либо удалить файл
и перезапустить контейнер, тогда снова начнут действовать переменные окружения.
Текущий источник каждого значения виден в ответе ``GET /api/settings``
(поле ``source``: ``file`` или ``env``).

Безопасность
------------
* Изменять можно только ключи из белого списка EDITABLE_KEYS. Всё остальное,
  что придёт из API, отбрасывается — иначе произвольный ключ попал бы в конфиг.
* Все числовые лимиты зажимаются на сервере функцией clamp(). Ограничение
  в поле ввода обходится обычным запросом к API, поэтому проверка в интерфейсе
  ничего не гарантирует.
* Пароли никогда не попадают в журнал и не возвращаются наружу — только
  признак «задан / не задан».
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Белый список редактируемых ключей: имя -> тип значения
# ---------------------------------------------------------------------------
EDITABLE_KEYS: Dict[str, str] = {
    # --- ClickHouse ---
    "CLICKHOUSE_HOST": "str",
    "CLICKHOUSE_PORT": "int",
    "CLICKHOUSE_DATABASE": "str",
    "CLICKHOUSE_USER": "str",
    "CLICKHOUSE_PASSWORD": "str",
    # --- PostgreSQL ---
    "POSTGRES_HOST": "str",
    "POSTGRES_PORT": "int",
    "POSTGRES_DB": "str",
    "POSTGRES_USER": "str",
    "POSTGRES_PASSWORD": "str",
    # --- Модель (ИИ) ---
    "OLLAMA_BASE_URL": "str",
    "LLM_API_KIND": "str",
    "OLLAMA_MODEL": "str",
    # --- Лимиты ---
    "OLLAMA_NUM_CTX": "int",
    "LLM_MAX_TOKENS": "int",
    "LLM_CONCURRENCY": "int",
    "OLLAMA_TIMEOUT": "int",
    "OLLAMA_TEMPERATURE": "float",
    "LLM_KEEP_ALIVE": "str",
    "MAX_ROWS_PER_QUERY": "int",
    "MAX_ROWS_PER_CLIENT": "int",
    "CLICKHOUSE_MAX_EXECUTION_TIME": "int",
}

#: Значения этих ключей наружу не отдаются и в журнал не пишутся
SECRET_KEYS = frozenset({"CLICKHOUSE_PASSWORD", "POSTGRES_PASSWORD"})

#: Допустимые значения для ключей с фиксированным набором
ENUM_KEYS: Dict[str, Tuple[str, ...]] = {
    "LLM_API_KIND": ("ollama", "openai"),
}

#: Границы числовых значений: ключ -> (минимум, максимум)
#: Зажимаются на сервере при каждом сохранении и при каждом чтении.
LIMITS: Dict[str, Tuple[float, float]] = {
    "CLICKHOUSE_PORT": (1, 65535),
    "POSTGRES_PORT": (1, 65535),
    "OLLAMA_NUM_CTX": (512, 262144),
    "LLM_MAX_TOKENS": (64, 32768),
    "LLM_CONCURRENCY": (1, 32),
    "OLLAMA_TIMEOUT": (5, 3600),
    "OLLAMA_TEMPERATURE": (0.0, 2.0),
    "MAX_ROWS_PER_QUERY": (1, 20000),
    "MAX_ROWS_PER_CLIENT": (1, 200000),
    "CLICKHOUSE_MAX_EXECUTION_TIME": (10, 7200),
}

#: Служебные ключи файла — через API не редактируются
CACHE_MODELS_KEY = "_llm_models_cache"


def clamp(key: str, value: Any) -> Any:
    """Зажимает значение в допустимые границы.

    Вызывается и при сохранении, и при чтении: файл настроек могли поправить
    руками в обход интерфейса.
    """
    kind = EDITABLE_KEYS.get(key)
    if kind is None:
        return value

    if kind == "int":
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            number = int(_default_for(key) or 0)
        low, high = LIMITS.get(key, (None, None))
        if low is not None:
            number = max(int(low), min(int(high), number))
        return number

    if kind == "float":
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(_default_for(key) or 0.0)
        low, high = LIMITS.get(key, (None, None))
        if low is not None:
            number = max(float(low), min(float(high), number))
        return round(number, 3)

    text = "" if value is None else str(value).strip()
    allowed = ENUM_KEYS.get(key)
    if allowed and text not in allowed:
        return _default_for(key)
    return text


def _default_for(key: str) -> Any:
    return getattr(settings, key, None)


def clamp_rows(value: Any, default: Optional[int] = None) -> int:
    """Зажимает число строк выборки. Используется всеми запросами к данным."""
    maximum = int(runtime.get("MAX_ROWS_PER_QUERY"))
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default or maximum)
    return max(1, min(maximum, number))


class RuntimeSettings:
    """Действующие настройки приложения: умолчания плюс сохранённый файл."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._values: Dict[str, Any] = {}
        self._from_file: Dict[str, Any] = {}
        self._models_cache: List[str] = []
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._mtime: int = -1
        self.reload()

    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        directory = Path(settings.DATA_DIR)
        if not directory.is_absolute():
            directory = (Path(__file__).resolve().parent.parent.parent / settings.DATA_DIR).resolve()
        return directory / "settings.json"

    def _defaults(self) -> Dict[str, Any]:
        return {key: _default_for(key) for key in EDITABLE_KEYS}

    def _file_mtime(self) -> int:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return 0

    def _ensure_fresh(self) -> None:
        """Перечитывает файл, если он изменился на диске.

        Приложение работает в несколько воркеров uvicorn — это отдельные
        процессы, у каждого своя копия настроек в памяти. Сохранение проходит
        только в том процессе, который принял запрос, поэтому остальные обязаны
        замечать изменение файла. Без этой проверки настройки применялись бы
        через раз — в зависимости от того, какому воркеру достался запрос.
        """
        if self._file_mtime() != self._mtime:
            self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Слой 1 (умолчания) + слой 2 (файл) = действующие значения."""
        with self._lock:
            values = self._defaults()
            from_file: Dict[str, Any] = {}
            models_cache: List[str] = []

            path = self.path
            if path.is_file():
                try:
                    stored = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error(
                        "Файл настроек %s не прочитан (%s) — действуют переменные окружения",
                        path,
                        exc,
                    )
                    stored = {}

                models_cache = [str(m) for m in (stored.get(CACHE_MODELS_KEY) or [])]

                for key, value in stored.items():
                    # Через файл тоже принимаются только ключи из белого списка
                    if key in EDITABLE_KEYS:
                        from_file[key] = clamp(key, value)

                values.update(from_file)

            # Умолчания тоже прогоняются через зажим: в переменных окружения
            # может оказаться значение вне допустимых границ
            for key in EDITABLE_KEYS:
                values[key] = clamp(key, values.get(key))

            self._values = values
            self._from_file = from_file
            self._models_cache = models_cache
            self._mtime = self._file_mtime()

        logger.info(
            "Настройки загружены: %d из файла, %d из окружения (файл: %s)",
            len(self._from_file),
            len(EDITABLE_KEYS) - len(self._from_file),
            self.path if self.path.is_file() else "отсутствует",
        )

    # ------------------------------------------------------------------
    def get(self, key: str) -> Any:
        self._ensure_fresh()
        with self._lock:
            if key in self._values:
                return self._values[key]
        return _default_for(key)

    def all(self) -> Dict[str, Any]:
        self._ensure_fresh()
        with self._lock:
            return dict(self._values)

    def source_of(self, key: str) -> str:
        """Откуда взято значение: из файла настроек или из окружения."""
        with self._lock:
            return "file" if key in self._from_file else "env"

    def public(self) -> Dict[str, Any]:
        """Настройки для интерфейса: пароли заменены признаком «задан»."""
        self._ensure_fresh()
        with self._lock:
            data: Dict[str, Any] = {}
            for key in EDITABLE_KEYS:
                if key in SECRET_KEYS:
                    data[key] = ""
                    data[f"{key}_SET"] = bool(self._values.get(key))
                else:
                    data[key] = self._values.get(key)
            sources = {key: self.source_of(key) for key in EDITABLE_KEYS}
        return {"values": data, "source": sources, "limits": self.limits_meta()}

    @staticmethod
    def limits_meta() -> Dict[str, Dict[str, float]]:
        return {key: {"min": low, "max": high} for key, (low, high) in LIMITS.items()}

    # ------------------------------------------------------------------
    def update(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        """Сохраняет настройки, пропустив их через белый список и зажим.

        Пустое значение пароля НЕ затирает сохранённый ранее пароль —
        интерфейс отдаёт пустое поле, когда пользователь его не трогал.
        """
        applied: Dict[str, Any] = {}
        ignored: List[str] = []

        # Изменения соседнего воркера подхватываются до записи, иначе они
        # были бы затёрты содержимым памяти этого процесса
        self._ensure_fresh()

        with self._lock:
            for key, value in (incoming or {}).items():
                if key not in EDITABLE_KEYS:
                    ignored.append(key)
                    continue
                if key in SECRET_KEYS and (value is None or str(value) == ""):
                    continue
                applied[key] = clamp(key, value)

            if applied:
                self._from_file.update(applied)
                self._values.update(applied)
                self._write_file()

        if ignored:
            logger.warning("Отброшены ключи вне белого списка: %s", ", ".join(sorted(ignored)))
        if applied:
            logger.info("Сохранены настройки: %s", ", ".join(sorted(_safe_keys(applied))))
            self._notify(applied)

        return {"applied": sorted(_safe_keys(applied)), "ignored": sorted(ignored)}

    def remember_models(self, models: List[str]) -> None:
        """Запоминает перечень моделей, чтобы список работал при недоступном сервере ИИ."""
        with self._lock:
            self._models_cache = [str(m) for m in models if m]
            self._write_file()

    def cached_models(self) -> List[str]:
        self._ensure_fresh()
        with self._lock:
            cached = list(self._models_cache)
        current = self.get("OLLAMA_MODEL")
        if current and current not in cached:
            cached.insert(0, current)
        return cached

    def _write_file(self) -> None:
        path = self.path
        payload = dict(self._from_file)
        if self._models_cache:
            payload[CACHE_MODELS_KEY] = self._models_cache
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, path)
            # Запомнить своё же изменение, чтобы не перечитывать файл впустую
            self._mtime = self._file_mtime()
        except OSError as exc:
            logger.error("Не удалось сохранить файл настроек %s: %s", path, exc)
            raise

    # ------------------------------------------------------------------
    def on_change(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        """Подписка на изменение настроек — клиенты пересоздают соединения."""
        self._listeners.append(listener)

    def _notify(self, changed: Dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(changed)
            except Exception as exc:  # noqa: BLE001 — сбой одного не ломает остальных
                logger.error("Обработчик изменения настроек завершился ошибкой: %s", exc)


def _safe_keys(data: Dict[str, Any]) -> List[str]:
    """Имена ключей для журнала: значения паролей не раскрываются."""
    return [f"{k} (скрыт)" if k in SECRET_KEYS else k for k in data]


runtime = RuntimeSettings()
