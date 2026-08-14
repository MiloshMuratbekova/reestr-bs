from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlgorithmOut(BaseModel):
    id: int
    code: str
    name: str
    description: str
    sql_script: str
    clickhouse_result_table: str
    source: str
    priority_score: int
    is_active: bool
    version: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    depends_on: str = ""
    order_index: int = 0
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_row_count: Optional[int] = None
    last_error: Optional[str] = None

    model_config = {"from_attributes": True}


class AlgorithmCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    sql_script: str = Field(..., min_length=1)
    clickhouse_result_table: str = ""
    source: str = ""
    priority_score: int = 0
    is_active: bool = True
    depends_on: List[str] = Field(default_factory=list)
    order_index: int = 100


class AlgorithmUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sql_script: Optional[str] = None
    clickhouse_result_table: Optional[str] = None
    source: Optional[str] = None
    priority_score: Optional[int] = None
    is_active: Optional[bool] = None
    depends_on: Optional[List[str]] = None
    order_index: Optional[int] = None
    reason: str = ""
    #: Выполнить новый SQL в ClickHouse сразу после сохранения
    execute: bool = True


class AlgorithmHistoryOut(BaseModel):
    id: int
    algorithm_id: int
    sql_script: str
    changed_at: datetime
    reason: str
    version: Optional[int] = None
    changed_by: Optional[str] = None

    model_config = {"from_attributes": True}


class AlgorithmRunResult(BaseModel):
    code: str
    status: str
    row_count: Optional[int] = None
    duration_ms: Optional[int] = None
    result_table: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class AiUpdateRequest(BaseModel):
    requirement: str = Field(..., min_length=5, description="Текст нового бизнес-требования")


class AiUpdateResponse(BaseModel):
    algorithm_code: str
    old_sql: str
    new_sql: str
    tables: List[str] = Field(default_factory=list)
    duration_ms: int = 0


class RecalculateResponse(BaseModel):
    duration_ms: int
    total: int
    succeeded: int
    failed: int
    total_rows: int
    results: List[Dict[str, Any]]
