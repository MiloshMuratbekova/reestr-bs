from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CompanySearchItem(BaseModel):
    taxpayer_iin_bin: str
    taxpayer_name: str = ""
    category: str = ""
    code_nd: str = ""
    region: str = ""
    address: str = ""
    reg_start_date: str = ""
    ownership_type: str = ""
    is_state_owned: bool = False
    beneficiary_count: int = 0
    max_ball3: float = 0.0


class BeneficiaryOut(BaseModel):
    taxpayer_iin_bin: str
    taxpayer_name: str = ""
    benefeciary_iin_bin: str = ""
    benefeciary_name: str = ""
    status: str = ""
    algorithm_codes: List[str] = Field(default_factory=list)
    algorithms: str = ""
    priority: int = 0
    category: str = ""
    ownership_type: str = ""
    document_info: str = ""
    share_percentage: str = ""
    dop_info: str = ""
    ball1: int = 0
    ball2: int = 0
    ball3: float = 0.0

    model_config = {"extra": "ignore"}


class CompanyInfo(BaseModel):
    taxpayer_iin_bin: str
    taxpayer_name: str = ""
    category: str = ""
    reg_start_date: str = ""
    address: str = ""
    code_nd: str = ""
    ownership_type: str = ""
    is_state_owned: bool = False

    model_config = {"extra": "ignore"}


class FounderOut(BaseModel):
    founder_iin_bin: str = ""
    founder_name: str = ""
    share_percentage: str = ""

    model_config = {"extra": "ignore"}


class DirectorOut(BaseModel):
    director_iin_bin: str = ""
    director_name: str = ""

    model_config = {"extra": "ignore"}


class CompanyCard(BaseModel):
    company: CompanyInfo
    beneficiaries: List[BeneficiaryOut] = Field(default_factory=list)
    founders: List[FounderOut] = Field(default_factory=list)
    directors: List[DirectorOut] = Field(default_factory=list)
    director: Optional[DirectorOut] = None
    warning: Optional[str] = None
    beneficiary_count: int = 0
    max_ball3: float = 0.0


class ExplainRequest(BaseModel):
    #: ИИН конкретного бенефициара; если не указан — объясняется вся карточка
    benefeciary_iin_bin: Optional[str] = None


class ExplainResponse(BaseModel):
    explanation: str
    duration_ms: int = 0


class ChatRequest(BaseModel):
    bin: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    duration_ms: int = 0


class AlgorithmStat(BaseModel):
    algorithm_code: str
    name: str = ""
    priority: int = 0
    company_count: int = 0
    beneficiary_count: int = 0
    row_count: int = 0


class TopCompany(BaseModel):
    taxpayer_iin_bin: str
    taxpayer_name: str = ""
    code_nd: str = ""
    region: str = ""
    beneficiary_count: int = 0
    max_ball3: float = 0.0

    model_config = {"extra": "ignore"}


class StatsResponse(BaseModel):
    total_rows: int = 0
    company_count: int = 0
    beneficiary_count: int = 0
    registration_count: int = 0
    assumed_count: int = 0
    nonresident_count: int = 0
    algorithms_total: int = 0
    algorithms_calculated: int = 0
    by_algorithm: List[Dict[str, Any]] = Field(default_factory=list)

    # --- разрезы дашборда ---
    #: Всего юридических лиц в справочнике, а не только попавших в реестр
    total_companies: int = 0
    companies_with_bs: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    top_by_beneficiaries: List[TopCompany] = Field(default_factory=list)
    top_by_risk: List[TopCompany] = Field(default_factory=list)
