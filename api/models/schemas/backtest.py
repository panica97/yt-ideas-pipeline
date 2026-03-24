"""Pydantic v2 schemas for backtesting."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

BacktestMode = Literal["simple", "complete"]


class BacktestCreateRequest(BaseModel):
    draft_strat_code: int
    symbol: str
    timeframe: str = "1h"
    start_date: str
    end_date: str
    mode: BacktestMode = "simple"
    debug: bool = False


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
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestListResponse(BaseModel):
    total: int
    jobs: list[BacktestJobSummary]


class BacktestCompleteRequest(BaseModel):
    metrics: dict[str, Any]
    trades: list[dict[str, Any]] = []


class BacktestFailRequest(BaseModel):
    error_message: str
