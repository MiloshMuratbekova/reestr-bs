"""Схемы страниц списков, источников, отчётов и расписания."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Списки
# ---------------------------------------------------------------------------
class CompanyListItem(BaseModel):
    taxpayer_iin_bin: str = Field(description="БИН юридического лица")
    taxpayer_name: str = ""
    category: str = ""
    code_nd: str = ""
    region: str = ""
    address: str = ""
    reg_start_date: str = ""
    ownership_type: str = ""
    is_state_owned: bool = False
    beneficiary_count: int = 0
    max_ball3: float = 0


class CompanyListResponse(BaseModel):
    items: List[CompanyListItem]
    total: int
    page: int
    limit: int
    scope: str = "registry"


class BeneficiaryListItem(BaseModel):
    benefeciary_iin_bin: str = ""
    benefeciary_name: str = ""
    status: str = ""
    algorithm_codes: List[str] = Field(default_factory=list)
    algorithms: str = ""
    company_count: int = 0
    max_ball3: float = 0
    is_nonresident: bool = False
    priority: int = 0


class BeneficiaryListResponse(BaseModel):
    items: List[BeneficiaryListItem]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# Структуры владения
# ---------------------------------------------------------------------------
class GraphNode(BaseModel):
    id: str
    kind: str = Field(description="company — юридическое лицо, person — физическое")
    name: str = ""
    is_root: bool = False
    is_state_owned: bool = False
    ownership_type: str = ""


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str = Field(description="founder, director либо beneficiary")
    label: str = ""
    share: str = ""
    ball3: Optional[float] = None
    algorithms: List[str] = Field(default_factory=list)


class OwnershipResponse(BaseModel):
    root: Optional[Dict[str, Any]] = None
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Отчёты
# ---------------------------------------------------------------------------
class ReportGenerateRequest(BaseModel):
    template: str = Field(description="Код шаблона: registry, high_risk, nonresidents, algorithms")
    file_format: str = Field(default="xlsx", description="xlsx либо pdf")
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ReportOut(BaseModel):
    id: int
    template: str
    title: str = ""
    file_format: str = "xlsx"
    file_name: str = ""
    file_size: int = 0
    row_count: int = 0
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: str = "success"
    error: str = ""
    created_by: str = ""
    created_at: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Расписание
# ---------------------------------------------------------------------------
class ScheduleUpdate(BaseModel):
    enabled: bool = False
    run_time: str = Field(default="03:00", description="Время запуска в формате ЧЧ:ММ")
    timezone: Optional[str] = None


class ScheduleOut(BaseModel):
    enabled: bool = False
    run_time: str = "03:00"
    timezone: str = ""
    next_run_at: str = ""
    last_run_at: str = ""
    updated_by: str = ""


class RunOut(BaseModel):
    id: int
    trigger: str = "manual"
    status: str = "running"
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    total_rows: int = 0
    error: str = ""
    triggered_by: str = ""
    details: List[Dict[str, Any]] = Field(default_factory=list)
