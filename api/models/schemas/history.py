"""Pydantic v2 schemas for research history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HistoryItem(BaseModel):
    video_id: str
    url: str
    channel: str | None = None
    topic: str | None = None
    researched_at: datetime | None = None
    strategies_found: int = 0
    classification: str | None = None
    title: str | None = None

    model_config = ConfigDict(from_attributes=True)


class HistoryListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[HistoryItem]


class LastResearch(BaseModel):
    topic: str | None = None
    date: datetime | None = None
    videos: int = 0
    strategies: int = 0


class HistoryStatsResponse(BaseModel):
    total_videos: int = 0
    total_strategies_found: int = 0
    by_topic: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    last_research: LastResearch | None = None
