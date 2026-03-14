"""Pydantic v2 schemas for strategies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    source_channel: str | None = None
    source_videos: list[str] | None = None
    parameters: list[Any] | None = None
    entry_rules: list[Any] | None = None
    exit_rules: list[Any] | None = None
    risk_management: list[Any] | None = None
    notes: list[Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StrategiesListResponse(BaseModel):
    total: int
    strategies: list[StrategyResponse]
