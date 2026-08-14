from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Текущие настройки для формы.

    Пароли не возвращаются: вместо значения приходит признак
    ``<КЛЮЧ>_SET`` — задан пароль или нет.
    """

    values: Dict[str, Any]
    #: Откуда взято значение: «file» — из сохранённых настроек, «env» — из окружения
    source: Dict[str, str]
    #: Границы числовых параметров, применяемые на сервере
    limits: Dict[str, Dict[str, float]]


class SettingsUpdate(BaseModel):
    """Изменяемые настройки.

    Принимаются только ключи из белого списка, остальные отбрасываются.
    Пустое значение пароля не затирает сохранённый ранее.
    """

    values: Dict[str, Any] = Field(default_factory=dict)


class SettingsUpdateResult(BaseModel):
    applied: List[str] = Field(default_factory=list)
    ignored: List[str] = Field(default_factory=list)
    values: Dict[str, Any] = Field(default_factory=dict)
    source: Dict[str, str] = Field(default_factory=dict)


class TestResult(BaseModel):
    ok: bool
    message: str = ""
    error: str = ""
    version: str = ""
    database: str = ""
    model: str = ""
    answer: str = ""
    duration_ms: Optional[int] = None

    model_config = {"extra": "ignore", "protected_namespaces": ()}


class ClickHouseTestRequest(BaseModel):
    """Параметры проверки. Незаполненные берутся из действующих настроек."""

    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None


class PostgresTestRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None


class ModelsResponse(BaseModel):
    ok: bool
    models: List[str] = Field(default_factory=list)
    error: str = ""
