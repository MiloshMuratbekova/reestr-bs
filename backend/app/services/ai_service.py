"""Интеграция с моделью Qwen через Ollama REST API (192.168.97.9:11434).

Три сценария из ТЗ:
  * объяснение, почему человек признан бенефициарным собственником;
  * ответ на вопрос аналитика в чате по контексту компании;
  * подготовка нового SQL алгоритма по новому бизнес-требованию.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.algorithms.definitions import ALGORITHM_HINTS
from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.clickhouse import ClickHouseError, clickhouse
from app.services.settings_service import runtime

logger = get_logger(__name__)

DASH = "—"


class AiError(RuntimeError):
    """Ошибка обращения к модели Qwen."""


# ---------------------------------------------------------------------------
# Транспорт
# ---------------------------------------------------------------------------
class OllamaClient:
    """Клиент сервера ИИ.

    Поддерживаются два типа API, выбор — в настройках (LLM_API_KIND):
      * ``ollama`` — нативный Ollama: /api/generate, /api/tags;
      * ``openai`` — OpenAI-совместимый: /v1/chat/completions, /v1/models.

    Все параметры (адрес, модель, лимиты) читаются из настроек времени
    выполнения, поэтому изменения из интерфейса применяются без перезапуска.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""
        self._semaphore = asyncio.Semaphore(max(1, int(settings.LLM_CONCURRENCY)))
        self._concurrency = max(1, int(settings.LLM_CONCURRENCY))

    # ------------------------------------------------------------------
    @staticmethod
    def base_url() -> str:
        return str(runtime.get("OLLAMA_BASE_URL") or "").rstrip("/")

    @staticmethod
    def api_kind() -> str:
        return str(runtime.get("LLM_API_KIND") or "ollama")

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._base_url = self.base_url()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(float(runtime.get("OLLAMA_TIMEOUT")), connect=15.0),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        logger.info(
            "Клиент ИИ инициализирован: %s (API: %s)", self._base_url, self.api_kind()
        )

    async def reconfigure(self) -> None:
        """Применяет изменённые настройки: адрес, таймаут, параллельность."""
        concurrency = max(1, int(runtime.get("LLM_CONCURRENCY")))
        if concurrency != self._concurrency:
            self._semaphore = asyncio.Semaphore(concurrency)
            self._concurrency = concurrency

        if self.base_url() != self._base_url or self._client is None:
            await self.close()
            await self.connect()
        elif self._client is not None:
            self._client.timeout = httpx.Timeout(
                float(runtime.get("OLLAMA_TIMEOUT")), connect=15.0
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise AiError("Клиент сервера ИИ не инициализирован")
        return self._client

    # ------------------------------------------------------------------
    def _build_payload(
        self, prompt: str, system: Optional[str], temperature: Optional[float]
    ) -> Tuple[str, Dict[str, Any]]:
        temp = float(runtime.get("OLLAMA_TEMPERATURE")) if temperature is None else temperature
        num_ctx = int(runtime.get("OLLAMA_NUM_CTX"))
        max_tokens = int(runtime.get("LLM_MAX_TOKENS"))
        model = str(runtime.get("OLLAMA_MODEL"))

        if self.api_kind() == "openai":
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            return "/v1/chat/completions", {
                "model": model,
                "messages": messages,
                "temperature": temp,
                "max_tokens": max_tokens,
                "stream": False,
            }

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            # num_ctx задаётся явно: по умолчанию Ollama берёт 4096 и молча
            # обрезает всё, что длиннее, — без ошибки и без предупреждения.
            # Карточка компании с десятком бенефициаров в 4096 не помещается.
            "options": {
                "temperature": temp,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
            # Модель остаётся в памяти между запросами: иначе Ollama выгружает
            # её через 5 минут, и первый запрос после паузы ждёт повторной
            # загрузки 122B-модели — со стороны это выглядит как зависание.
            "keep_alive": str(runtime.get("LLM_KEEP_ALIVE")),
        }
        if system:
            payload["system"] = system
        return "/api/generate", payload

    @staticmethod
    def _extract_text(data: Dict[str, Any], kind: str) -> str:
        if kind == "openai":
            choices = data.get("choices") or []
            if choices:
                return (choices[0].get("message", {}).get("content") or "").strip()
            return ""
        return (data.get("response") or "").strip()

    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        await self.reconfigure()
        path, payload = self._build_payload(prompt, system, temperature)
        timeout = float(runtime.get("OLLAMA_TIMEOUT"))
        kind = self.api_kind()

        started = time.perf_counter()
        # Число одновременных обращений к модели ограничено настройкой:
        # 122B-модель на нескольких параллельных запросах уходит в своп
        async with self._semaphore:
            try:
                response = await self.client.post(path, json=payload, timeout=timeout)
            except httpx.TimeoutException as exc:
                raise AiError(
                    f"Модель не ответила за {timeout:.0f} секунд. "
                    "Увеличьте таймаут в настройках либо сократите объём данных."
                ) from exc
            except httpx.HTTPError as exc:
                raise AiError(
                    f"Не удалось подключиться к серверу ИИ ({self.base_url()}). "
                    "Проверьте адрес в настройках и доступность сервиса."
                ) from exc

        if response.status_code != 200:
            raise AiError(f"Сервер ИИ вернул ошибку {response.status_code}: {response.text[:500]}")

        data = response.json()
        return {
            "text": self._extract_text(data, kind),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "model": data.get("model", runtime.get("OLLAMA_MODEL")),
            "eval_count": data.get("eval_count"),
        }

    # ------------------------------------------------------------------
    async def ping(self) -> bool:
        try:
            await self.reconfigure()
            path = "/v1/models" if self.api_kind() == "openai" else "/api/tags"
            response = await self.client.get(path, timeout=10.0)
            return response.status_code == 200
        except (httpx.HTTPError, AiError):
            return False

    async def available_models(self) -> List[str]:
        """Список моделей с сервера ИИ. Бросает AiError при недоступности."""
        await self.reconfigure()
        kind = self.api_kind()
        path = "/v1/models" if kind == "openai" else "/api/tags"
        try:
            response = await self.client.get(path, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AiError(f"{type(exc).__name__}: не удалось получить список моделей") from exc

        data = response.json()
        if kind == "openai":
            return [str(m.get("id", "")) for m in data.get("data", []) if m.get("id")]
        return [str(m.get("name", "")) for m in data.get("models", []) if m.get("name")]


ollama = OllamaClient()


# ---------------------------------------------------------------------------
# Вспомогательное форматирование
# ---------------------------------------------------------------------------
def _value(raw: Any) -> str:
    """Пустые значения показываются прочерком."""
    if raw is None:
        return DASH
    text = str(raw).strip()
    return text if text else DASH


def _algorithms_block(codes: List[str]) -> str:
    if not codes:
        return DASH
    lines = []
    for code in codes:
        hint = ALGORITHM_HINTS.get(code)
        lines.append(f"    - {code}: {hint}" if hint else f"    - {code}")
    return "\n" + "\n".join(lines)


def _beneficiary_lines(beneficiaries: List[Dict[str, Any]], limit: int = 40) -> str:
    if not beneficiaries:
        return "  Бенефициарные собственники не выявлены."
    lines = []
    for item in beneficiaries[:limit]:
        codes = item.get("algorithm_codes") or []
        if isinstance(codes, str):
            codes = [codes]
        lines.append(
            f"  - {_value(item.get('benefeciary_name'))} "
            f"(ИИН {_value(item.get('benefeciary_iin_bin'))}), "
            f"статус: {_value(item.get('status'))}, "
            f"алгоритмы: {', '.join(codes) if codes else DASH}, "
            f"доля: {_value(item.get('share_percentage'))}, "
            f"вероятность: {_value(item.get('ball3'))}%"
        )
    if len(beneficiaries) > limit:
        lines.append(f"  … и ещё {len(beneficiaries) - limit} записей")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Сценарий 1: объяснение, почему человек является БС
# ---------------------------------------------------------------------------
EXPLAIN_SYSTEM = (
    "Вы — аналитик Агентства по финансовому мониторингу Республики Казахстан. "
    "Вы объясняете результаты работы системы «Реестр БС» простыми словами, "
    "без технических терминов, названий таблиц и кода. "
    "Отвечайте только на русском языке."
)


def build_explain_prompt(company: Dict[str, Any], beneficiary: Dict[str, Any]) -> str:
    codes = beneficiary.get("algorithm_codes") or []
    if isinstance(codes, str):
        codes = [codes]

    return f"""Проанализируйте одного бенефициарного собственника юридического лица.

КОМПАНИЯ
  Наименование: {_value(company.get('taxpayer_name'))}
  БИН: {_value(company.get('taxpayer_iin_bin'))}
  Организационно-правовая форма: {_value(company.get('category'))}
  Тип собственности: {_value(company.get('ownership_type'))}

БЕНЕФИЦИАРНЫЙ СОБСТВЕННИК
  Имя: {_value(beneficiary.get('benefeciary_name'))}
  ИИН: {_value(beneficiary.get('benefeciary_iin_bin'))}
  Статус: {_value(beneficiary.get('status'))}
  Доля владения: {_value(beneficiary.get('share_percentage'))}
  Вероятность: {_value(beneficiary.get('ball3'))}%
  Дополнительная информация: {_value(beneficiary.get('dop_info'))}
  Выявлен алгоритмами: {_algorithms_block(list(codes))}

Дайте развёрнутый ответ по четырём пунктам:
1. Почему этот человек является бенефициарным собственником компании.
2. На основании каких данных это определено.
3. Какие риски это несёт.
4. Что рекомендуется дополнительно проверить.

Пишите простыми словами, как для сотрудника, который не работает с базами данных."""


async def explain_beneficiary(
    company: Dict[str, Any], beneficiary: Dict[str, Any]
) -> Dict[str, Any]:
    prompt = build_explain_prompt(company, beneficiary)
    result = await ollama.generate(prompt, system=EXPLAIN_SYSTEM)
    return {"explanation": result["text"], "duration_ms": result["duration_ms"], "prompt": prompt}


async def explain_company(card: Dict[str, Any]) -> Dict[str, Any]:
    """Объяснение по всей карточке компании — по всем выявленным БС."""
    company = card.get("company", {})
    beneficiaries = card.get("beneficiaries", [])

    if company.get("is_state_owned"):
        return {
            "explanation": (
                "Компания находится в государственной собственности. "
                "Бенефициарные собственники для таких организаций не определяются."
            ),
            "duration_ms": 0,
        }

    prompt = f"""Проанализируйте бенефициарных собственников юридического лица.

КОМПАНИЯ
  Наименование: {_value(company.get('taxpayer_name'))}
  БИН: {_value(company.get('taxpayer_iin_bin'))}
  Организационно-правовая форма: {_value(company.get('category'))}
  Тип собственности: {_value(company.get('ownership_type'))}
  Дата регистрации: {_value(company.get('reg_start_date'))}
  Адрес: {_value(company.get('address'))}

ВЫЯВЛЕННЫЕ БЕНЕФИЦИАРНЫЕ СОБСТВЕННИКИ ({len(beneficiaries)})
{_beneficiary_lines(beneficiaries)}

РАСШИФРОВКА АЛГОРИТМОВ
{chr(10).join(f'  {code}: {hint}' for code, hint in ALGORITHM_HINTS.items())}

Дайте развёрнутый ответ по четырём пунктам:
1. Почему эти люди являются бенефициарными собственниками компании.
2. На основании каких данных это определено.
3. Какие риски это несёт.
4. Что рекомендуется дополнительно проверить.

Пишите простыми словами, как для сотрудника, который не работает с базами данных."""

    result = await ollama.generate(prompt, system=EXPLAIN_SYSTEM)
    return {"explanation": result["text"], "duration_ms": result["duration_ms"]}


# ---------------------------------------------------------------------------
# Сценарий 2: чат аналитика
# ---------------------------------------------------------------------------
CHAT_SYSTEM = (
    "Вы — помощник аналитика Агентства по финансовому мониторингу Республики Казахстан. "
    "Отвечайте конкретно и только на основании переданных данных о компании. "
    "Если данных для ответа недостаточно, прямо скажите об этом и укажите, "
    "какие сведения нужно запросить дополнительно. Отвечайте на русском языке."
)


def build_chat_prompt(card: Dict[str, Any], message: str) -> str:
    company = card.get("company", {})
    beneficiaries = card.get("beneficiaries", [])
    founders = card.get("founders", [])
    directors = card.get("directors", [])

    founders_block = (
        "\n".join(
            f"  - {_value(f.get('founder_name'))} "
            f"(ИИН/БИН {_value(f.get('founder_iin_bin'))}), доля: {_value(f.get('share_percentage'))}"
            for f in founders[:30]
        )
        or "  Учредители не указаны."
    )
    directors_block = (
        "\n".join(
            f"  - {_value(d.get('director_name'))} (ИИН {_value(d.get('director_iin_bin'))})"
            for d in directors[:10]
        )
        or "  Руководитель не указан."
    )

    return f"""КОНТЕКСТ — ДАННЫЕ О КОМПАНИИ

  Наименование: {_value(company.get('taxpayer_name'))}
  БИН: {_value(company.get('taxpayer_iin_bin'))}
  Организационно-правовая форма: {_value(company.get('category'))}
  Тип собственности: {_value(company.get('ownership_type'))}
  Дата регистрации: {_value(company.get('reg_start_date'))}
  Адрес: {_value(company.get('address'))}

БЕНЕФИЦИАРНЫЕ СОБСТВЕННИКИ ({len(beneficiaries)})
{_beneficiary_lines(beneficiaries)}

УЧРЕДИТЕЛИ
{founders_block}

РУКОВОДИТЕЛЬ
{directors_block}

РАСШИФРОВКА АЛГОРИТМОВ
{chr(10).join(f'  {code}: {hint}' for code, hint in ALGORITHM_HINTS.items())}

ВОПРОС АНАЛИТИКА
{message}

Ответьте конкретно, ссылаясь на переданные выше данные."""


async def chat_about_company(card: Dict[str, Any], message: str) -> Dict[str, Any]:
    prompt = build_chat_prompt(card, message)
    result = await ollama.generate(prompt, system=CHAT_SYSTEM)
    return {"answer": result["text"], "duration_ms": result["duration_ms"]}


# ---------------------------------------------------------------------------
# Сценарий 3: обновление SQL алгоритма
# ---------------------------------------------------------------------------
SQL_SYSTEM = (
    "Вы — эксперт по ClickHouse SQL. Вы пишете корректные запросы для ClickHouse "
    "версии 25. Отвечайте только SQL-кодом без пояснений."
)

CLICKHOUSE_RULES = """ОГРАНИЧЕНИЯ, КОТОРЫЕ ОБЯЗАТЕЛЬНО НУЖНО УЧЕСТЬ:
  - база данных ClickHouse версии 25, используется синтаксис ClickHouse;
  - суммы в полях типа Int128 нельзя напрямую приводить к Decimal;
  - даты в полях типа DateTime используются напрямую, без парсинга;
  - вместо UNION нужно писать UNION ALL;
  - коррелированные подзапросы в IN не поддерживаются — нужно использовать JOIN."""

_TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def extract_tables(sql: str) -> List[str]:
    """Находит таблицы вида «база.таблица», используемые в запросе."""
    found: List[str] = []
    for match in _TABLE_PATTERN.finditer(sql):
        table = match.group(1)
        if table not in found:
            found.append(table)
    return found


async def describe_tables(tables: List[str], limit: int = 25) -> str:
    """Структуры таблиц через DESCRIBE — передаются модели в промпте."""
    blocks: List[str] = []
    for table in tables[:limit]:
        try:
            columns = await clickhouse.fetch_all(f"DESCRIBE TABLE {table}")
        except ClickHouseError as exc:
            blocks.append(f"{table}: структура недоступна ({exc})")
            continue
        if not columns:
            continue
        column_list = ", ".join(
            f"{c.get('name')} {c.get('type')}" for c in columns if c.get("name")
        )
        blocks.append(f"{table}: {column_list}")
    return "\n".join(blocks) if blocks else "Структуры таблиц недоступны."


def build_sql_update_prompt(
    old_sql: str, requirement: str, tables_description: str, algorithm_code: str
) -> str:
    return f"""Нужно переписать SQL алгоритма {algorithm_code} системы «Реестр БС».

СТРУКТУРЫ ИСПОЛЬЗУЕМЫХ ТАБЛИЦ
{tables_description}

ДЕЙСТВУЮЩИЙ SQL АЛГОРИТМА
{old_sql}

НОВОЕ БИЗНЕС-ТРЕБОВАНИЕ
{requirement}

{CLICKHOUSE_RULES}

Набор выходных полей менять нельзя: taxpayer_iin_bin, founder_iin_bin,
share_percentage, director_iin_bin, benefeciary_iin_bin, status,
algorithm_code, priority, source, _actual_date, dop_info.

Верните только готовый SQL-код без пояснений и без markdown-разметки."""


def _strip_markdown_fence(text: str) -> str:
    """Убирает обрамление ```sql ... ```, если модель его добавила."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Проверки для страницы настроек
# ---------------------------------------------------------------------------
async def test_model() -> Dict[str, Any]:
    """Короткий запрос к модели. Исключения наружу не выбрасываются.

    Возвращает ``{"ok": True, "answer": ...}`` либо
    ``{"ok": False, "error": "Тип: текст"}`` — интерфейс показывает строку
    состояния, по которой видно, что именно не так.
    """
    started = time.perf_counter()
    try:
        result = await ollama.generate(
            "Ответь одним словом: работает",
            system="Отвечай предельно кратко, на русском языке.",
            temperature=0.0,
        )
    except AiError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — наружу отдаём строку, а не исключение
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}

    answer = (result.get("text") or "").strip()
    if not answer:
        return {
            "ok": False,
            "error": "Модель ответила пустой строкой — проверьте имя модели в настройках",
        }

    return {
        "ok": True,
        "model": str(runtime.get("OLLAMA_MODEL")),
        "answer": answer[:300],
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "message": f"Модель ответила за {int((time.perf_counter() - started) * 1000)} мс",
    }


async def list_models_safe() -> Dict[str, Any]:
    """Список моделей с сервера ИИ.

    При недоступности сервера возвращает сохранённый перечень, чтобы
    выпадающий список остался рабочим и модель можно было выбрать вслепую.
    """
    try:
        models = await ollama.available_models()
    except AiError as exc:
        return {"ok": False, "models": runtime.cached_models(), "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "models": runtime.cached_models(),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }

    if models:
        runtime.remember_models(models)
    return {"ok": True, "models": models}


async def suggest_sql_update(
    algorithm_code: str, old_sql: str, requirement: str
) -> Dict[str, Any]:
    tables = extract_tables(old_sql)
    tables_description = await describe_tables(tables)
    prompt = build_sql_update_prompt(old_sql, requirement, tables_description, algorithm_code)

    result = await ollama.generate(prompt, system=SQL_SYSTEM, temperature=0.1)
    new_sql = _strip_markdown_fence(result["text"])

    return {
        "algorithm_code": algorithm_code,
        "old_sql": old_sql,
        "new_sql": new_sql,
        "tables": tables,
        "duration_ms": result["duration_ms"],
    }
