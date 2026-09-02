"""Разбор «грязных» строк ФИО моделью, с запоминанием разобранного.

Что происходит
--------------
Реестр показывает имя бенефициара по простым правилам: справочник физлиц,
затем наименование из кавычек, затем строка до первой запятой. Там, где
источник записал всё подряд без кавычек, правила бессильны — и в карточку
попадает фраза целиком.

Такие строки отбираются здесь и уходят одним запросом к модели. Она
возвращает разобранное: наименование, доля, ИИН, признак нерезидента.
Результат ложится в PostgreSQL приложения и дальше берётся оттуда.

Чего этот модуль НЕ делает
--------------------------
Не меняет логику выявления бенефициаров. Разбор касается только того, как
запись показывается: ключ сведения, баллы и состав реестра остаются теми же,
их считает SQL. Если модель недоступна или ответила неразборчиво, показывается
имя по правилам — страница из-за этого не ломается и не ждёт.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.name_cleanup import BsNameCleanup, fingerprint
from app.services.ai_service import AiError, ollama

logger = get_logger(__name__)

#: Признаки того, что в поле лежит не имя, а фраза с лишними сведениями
NOISE_MARKS = (
    "тип участия",
    "статус заявки",
    "доля",
    "гражданство",
    "резидент",
    "участник",
    "учредител",
    "акционер",
)

#: Организационные формы: сами по себе именем не являются
LEGAL_FORMS = (
    "тоо",
    "ао",
    "оао",
    "зао",
    "пао",
    "ип",
    "ксп",
    "ооо",
    "публичная компания",
    "товарищество",
    "акционерное общество",
    "с ограниченной ответственностью",
)

_SYSTEM = (
    "Ты разбираешь записи о владельцах компаний из государственного реестра "
    "Казахстана. Отвечаешь только JSON, без пояснений и без разметки."
)


def looks_dirty(name: str) -> bool:
    """Похоже ли, что в поле имени осталась лишняя информация.

    Признаки: служебные слова источника, двоеточие, несколько запятых или
    просто слишком длинная строка. Имя человека и краткое наименование
    организации под эти признаки не подпадают, и модель их не трогает.
    """
    text = (name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(mark in lowered for mark in NOISE_MARKS):
        return True
    if ":" in text or text.count(",") >= 2:
        return True
    return len(text) > 80


def _parse_reply(text: str, count: int) -> List[Dict[str, Any]]:
    """Разбирает ответ модели. Мусор и недостачу гасит пустыми записями."""
    cleaned = text.strip()
    # Модель нередко оборачивает JSON в ```json … ```
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end <= start:
        raise AiError("Модель ответила не JSON-массивом")

    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, list):
        raise AiError("Модель вернула не массив")

    result: List[Dict[str, Any]] = []
    for index in range(count):
        item = data[index] if index < len(data) and isinstance(data[index], dict) else {}
        iin = re.sub(r"\D", "", str(item.get("iin") or ""))
        result.append(
            {
                "name": str(item.get("name") or "").strip()[:300],
                "iin": iin if len(iin) == 12 else "",
                "share": str(item.get("share") or "").strip()[:32],
                "is_nonresident": bool(item.get("is_nonresident")),
            }
        )
    return result


def build_prompt(values: Sequence[str]) -> str:
    """Задание модели: разобрать пронумерованные строки."""
    lines = "\n".join(f"{i}. {v}" for i, v in enumerate(values, start=1))
    forms = ", ".join(LEGAL_FORMS[:8]).upper()
    return f"""Ниже пронумерованы записи о владельцах компаний. В каждой перемешаны
наименование организации или ФИО человека и служебные сведения: тип участия,
статус заявки, доля, гражданство.

Для каждой записи верни объект с полями:
  "name"           — только наименование организации или ФИО человека.
                     Организационную форму ({forms} и подобные) в name НЕ включай.
                     Кавычки убери. Если наименования нет, оставь пустую строку.
  "iin"            — ИИН или БИН из 12 цифр, если он есть в записи, иначе "".
  "share"          — доля участия так, как записана («30%», «1/3»), иначе "".
  "is_nonresident" — true, если из записи следует, что лицо иностранное
                     или нерезидент, иначе false.

Ничего не придумывай: чего в записи нет, того быть не должно в ответе.
Верни JSON-массив ровно из {len(values)} объектов, по одному на каждую запись,
в том же порядке. Никакого текста кроме массива.

{lines}"""


async def _load_known(
    session: AsyncSession, hashes: Sequence[str]
) -> Dict[str, BsNameCleanup]:
    if not hashes:
        return {}
    rows = await session.execute(
        select(BsNameCleanup).where(BsNameCleanup.raw_hash.in_(list(hashes)))
    )
    return {row.raw_hash: row for row in rows.scalars()}


async def _remember(session: AsyncSession, records: List[Dict[str, Any]]) -> None:
    """Складывает разобранное. Повторный разбор той же строки перезаписью."""
    if not records:
        return
    statement = pg_insert(BsNameCleanup).values(records)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[BsNameCleanup.raw_hash],
            set_={
                "name": statement.excluded.name,
                "iin": statement.excluded.iin,
                "share": statement.excluded.share,
                "is_nonresident": statement.excluded.is_nonresident,
                "source": statement.excluded.source,
            },
        )
    )
    await session.commit()


def _apply(row: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """Переносит разобранное в строку выдачи, ничего не затирая пустым."""
    if parsed.get("name"):
        row["benefeciary_name"] = parsed["name"]
    if parsed.get("share") and not str(row.get("share_percentage") or "").strip():
        row["share_percentage"] = parsed["share"]
    if parsed.get("is_nonresident"):
        row["is_nonresident"] = 1
    row["name_source"] = "ai"


async def enrich_names(
    session: AsyncSession,
    rows: List[Dict[str, Any]],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Дочищает имена в строках выдачи. Меняет их на месте и возвращает их же.

    Разбираются только те строки, где правила явно не справились. Уже
    разобранное берётся из PostgreSQL, новое уходит к модели одним запросом.
    Любая неудача — молчаливый откат к имени по правилам: пустая карточка
    из-за недоступной модели недопустима.
    """
    if not rows or not settings.AI_NAME_CLEANUP:
        return rows

    # Кандидаты: непустое исходное поле и подозрительное имя
    candidates: Dict[str, str] = {}
    for row in rows:
        raw = str(row.get("dop_info") or "").strip()
        if not raw or not looks_dirty(str(row.get("benefeciary_name") or "")):
            continue
        candidates.setdefault(fingerprint(raw), raw)
    if not candidates:
        return rows

    known = await _load_known(session, list(candidates))
    parsed: Dict[str, Dict[str, Any]] = {
        key: {
            "name": row.name,
            "iin": row.iin,
            "share": row.share,
            "is_nonresident": row.is_nonresident,
        }
        for key, row in known.items()
    }

    # За один заход к модели уходит ограниченное число строк: длинная выборка
    # не влезет в контекст, а ждать её на открытии страницы никто не станет
    cap = limit or settings.AI_NAME_CLEANUP_BATCH
    fresh = [(key, raw) for key, raw in candidates.items() if key not in parsed][:cap]
    if fresh:
        try:
            reply = await ollama.generate(
                build_prompt([raw for _, raw in fresh]), system=_SYSTEM, temperature=0.0
            )
            values = _parse_reply(reply["text"], len(fresh))
        except (AiError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Разбор имён моделью не удался: %s", exc)
            values = []

        if values:
            records = []
            for (key, raw), value in zip(fresh, values):
                parsed[key] = value
                records.append(
                    {
                        "raw_hash": key,
                        "raw_text": raw,
                        "name": value["name"],
                        "iin": value["iin"],
                        "share": value["share"],
                        "is_nonresident": value["is_nonresident"],
                        "source": "ai",
                    }
                )
            try:
                await _remember(session, records)
            except Exception as exc:  # noqa: BLE001 — показать важнее, чем запомнить
                await session.rollback()
                logger.warning("Не удалось сохранить разбор имён: %s", exc)

    for row in rows:
        raw = str(row.get("dop_info") or "").strip()
        value = parsed.get(fingerprint(raw)) if raw else None
        if value:
            _apply(row, value)
    return rows


async def forget_ai_names(session: AsyncSession) -> int:
    """Сбрасывает разбор, сделанный моделью. Возвращает число забытых строк."""
    rows = await session.execute(
        select(BsNameCleanup).where(BsNameCleanup.source == "ai")
    )
    items = list(rows.scalars())
    for item in items:
        await session.delete(item)
    await session.commit()
    return len(items)


def dirty_count(rows: Iterable[Dict[str, Any]]) -> int:
    """Сколько строк выдачи выглядят неразобранными — для показателей."""
    return sum(1 for row in rows if looks_dirty(str(row.get("benefeciary_name") or "")))
