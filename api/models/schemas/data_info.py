"""Pydantic v2 schemas for data-info scan jobs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScanResult(BaseModel):
    symbol: str
    data_from: datetime | None = None
    data_to: datetime | None = None


class ScanResultsRequest(BaseModel):
    results: list[ScanResult]


class ScanFailRequest(BaseModel):
    error_message: str


class ScanJobResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    results: list[ScanResult] | None = None

    model_config = ConfigDict(from_attributes=True)
