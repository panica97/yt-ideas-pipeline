"""Pydantic v2 schemas for dashboard statistics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LastResearchStat(BaseModel):
    topic: str | None = None
    date: datetime | None = None
    strategies_found: int = 0


class StatsResponse(BaseModel):
    total_topics: int = 0
    total_channels: int = 0
    total_videos_researched: int = 0
    total_strategies: int = 0
    total_drafts: int = 0
    drafts_with_todos: int = 0
    last_research: LastResearchStat | None = None
