"""Pydantic v2 schemas for drafts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TodoField(BaseModel):
    path: str
    context: str | None = None


class TodoSummary(BaseModel):
    count: int = 0
    fields: list[TodoField] = []


class DraftSummary(BaseModel):
    strat_code: int
    strat_name: str
    symbol: str | None = None
    active: bool = False
    tested: bool = False
    prod: bool = False
    todo_count: int = 0
    todo_fields: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)


class DraftDetail(BaseModel):
    strat_code: int
    strat_name: str
    active: bool = False
    tested: bool = False
    prod: bool = False
    todo_count: int = 0
    todo_fields: list[str] | None = None
    data: dict[str, Any] = {}
    todo_summary: TodoSummary = Field(default_factory=TodoSummary, alias="_todo_summary")
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FillTodoRequest(BaseModel):
    path: str
    value: Any


class DraftsListResponse(BaseModel):
    total: int
    drafts: list[DraftSummary]
