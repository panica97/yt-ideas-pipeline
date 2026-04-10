"""Pydantic v2 schemas for generic job tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

JobStatus = Literal["pending", "running", "completed", "failed"]


class JobCreateRequest(BaseModel):
    job_type: str
    draft_id: str
    config: Optional[dict[str, Any]] = None


class JobUpdateRequest(BaseModel):
    status: JobStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    id: int
    job_id: str
    job_type: str
    status: str
    draft_id: str
    config: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    total: int
    jobs: list[JobResponse]
