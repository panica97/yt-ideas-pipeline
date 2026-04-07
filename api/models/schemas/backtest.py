"""Pydantic v2 schemas for backtesting."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

BacktestMode = Literal["simple", "complete", "montecarlo", "monkey", "stress"]
BacktestTimeframe = Literal[
    "1m", "5m", "15m", "30m",
    "1H", "2H", "3H", "4H", "8H",
    "1D", "1W",
    # Legacy lowercase variants accepted by engine
    "1h", "2h", "3h", "4h", "8h", "1d", "1w",
]
BacktestStatus = Literal["pending", "running", "completed", "failed"]


class BacktestCreateRequest(BaseModel):
    draft_strat_code: int
    symbol: str
    timeframe: BacktestTimeframe = "1h"
    start_date: str
    end_date: str
    mode: BacktestMode = "simple"
    n_paths: Optional[int] = None
    fit_years: Optional[int] = None
    n_simulations: Optional[int] = None    # for monkey mode
    monkey_mode: Optional[str] = None      # "A" or "B"
    stress_test_name: Optional[str] = None
    stress_param_overrides: Optional[dict] = None
    stress_single_overrides: Optional[dict] = None
    stress_max_parallel: Optional[int] = None
    pipeline_group: Optional[_uuid.UUID] = None
    pipeline_config: Optional[dict] = None
    debug: bool = False

    @field_validator("symbol")
    @classmethod
    def symbol_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol must not be empty")
        if len(v) > 20:
            raise ValueError("symbol must be at most 20 characters")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Ensure dates are valid YYYY-MM-DD strings."""
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid date format: '{v}'. Expected YYYY-MM-DD.")
        return v


class BacktestResultResponse(BaseModel):
    id: int
    metrics: dict[str, Any]
    trades: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BacktestJobResponse(BaseModel):
    id: int
    draft_strat_code: int
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    status: str
    mode: str = "simple"
    n_paths: int | None = None
    fit_years: int | None = None
    n_simulations: int | None = None
    monkey_mode: str | None = None
    stress_test_name: str | None = None
    stress_param_overrides: dict | None = None
    stress_single_overrides: dict | None = None
    stress_max_parallel: int | None = None
    pipeline_group: _uuid.UUID | None = None
    pipeline_config: dict | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: BacktestResultResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestJobSummary(BaseModel):
    id: int
    draft_strat_code: int
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    status: str
    mode: str = "simple"
    n_paths: int | None = None
    fit_years: int | None = None
    n_simulations: int | None = None
    monkey_mode: str | None = None
    stress_test_name: str | None = None
    stress_param_overrides: dict | None = None
    stress_single_overrides: dict | None = None
    stress_max_parallel: int | None = None
    pipeline_group: _uuid.UUID | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestListResponse(BaseModel):
    total: int
    jobs: list[BacktestJobSummary]


PipelineStatus = Literal["pending", "running", "completed", "failed"]


class PipelineStatusResponse(BaseModel):
    pipeline_group: _uuid.UUID
    status: PipelineStatus
    jobs: list[BacktestJobSummary]

    model_config = ConfigDict(from_attributes=True)


class BacktestCompleteRequest(BaseModel):
    metrics: dict[str, Any]
    trades: list[dict[str, Any]] = []


class BacktestFailRequest(BaseModel):
    error_message: str
