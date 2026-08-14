"""Настройка логирования.

Пишем и в консоль, и в файлы (закрытый контур — внешних агрегаторов нет).
Отдельный лог для выполнения алгоритмов, т.к. он самый объёмный.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-32s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    app_file = logging.handlers.RotatingFileHandler(
        os.path.join(settings.LOG_DIR, "app.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    app_file.setFormatter(formatter)
    root.addHandler(app_file)

    # Отдельный файл под выполнение алгоритмов
    algo_logger = logging.getLogger("app.algorithms")
    algo_file = logging.handlers.RotatingFileHandler(
        os.path.join(settings.LOG_DIR, "algorithms.log"),
        maxBytes=100 * 1024 * 1024,
        backupCount=20,
        encoding="utf-8",
    )
    algo_file.setFormatter(formatter)
    algo_logger.addHandler(algo_file)

    # Приглушаем шумные библиотеки
    for noisy in ("httpx", "httpcore", "asyncio", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
