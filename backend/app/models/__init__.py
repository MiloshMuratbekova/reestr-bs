"""Модели PostgreSQL (БД bs_registry на сервере 10.10.31.35)."""

from app.models.algorithm import BsAlgorithm, BsAlgorithmHistory
from app.models.name_cleanup import BsNameCleanup, fingerprint
from app.models.report import BsReport
from app.models.schedule import SCHEDULE_ID, BsRun, BsSchedule
from app.models.user import BsUser, UserRole

__all__ = [
    "BsAlgorithm",
    "BsAlgorithmHistory",
    "BsNameCleanup",
    "BsReport",
    "BsRun",
    "BsSchedule",
    "BsUser",
    "SCHEDULE_ID",
    "UserRole",
    "fingerprint",
]
