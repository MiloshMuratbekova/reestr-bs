"""Разобранные моделью строки ФИО.

Зачем хранить
-------------
В поле ФИО у части алгоритмов лежит не имя, а целая фраза: организационная
форма, наименование в кавычках, тип участия, статус заявки, доля, гражданство.
Простые правила (см. :mod:`app.algorithms.cleaning`) вытаскивают наименование
из кавычек, но всё, что записано без них или необычно, им не по силам.

Такие строки разбирает модель. Спрашивать её при каждом открытии страницы
нельзя: ответ идёт секунды и на один и тот же текст может отличаться. Поэтому
разобранное складывается сюда, в PostgreSQL приложения, и дальше берётся
готовым. В ведомственную базу ClickHouse мы не пишем — прав нет.

Ключ — отпечаток исходной строки, а не её текст: строки бывают длинными,
а в индексе нужна предсказуемая длина.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def fingerprint(raw: str) -> str:
    """Отпечаток исходной строки — им и адресуется разобранное."""
    return hashlib.sha256((raw or "").strip().encode("utf-8")).hexdigest()


class BsNameCleanup(Base):
    """Одна разобранная строка ФИО."""

    __tablename__ = "bs_name_cleanup"

    raw_hash: Mapped[str] = mapped_column(String(64), primary_key=True)

    #: Исходная строка целиком — чтобы разбор можно было перепроверить глазами
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    #: Наименование организации либо ФИО человека, без всего лишнего
    name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: ИИН или БИН, если он был указан прямо в строке
    iin: Mapped[str] = mapped_column(String(12), default="", nullable=False)
    #: Доля участия так, как она записана в источнике («30%», «1/3»)
    share: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    #: Признак иностранного лица, если он следует из текста
    is_nonresident: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    #: Кто разобрал: ``ai`` — модель, ``rules`` — простые правила.
    #: Разделение нужно, чтобы разбор модели можно было выборочно сбросить,
    #: не трогая остальное.
    source: Mapped[str] = mapped_column(String(16), default="ai", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
