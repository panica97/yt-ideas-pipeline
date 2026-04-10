"""Generic job tracking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas.job import (
    JobCreateRequest,
    JobListResponse,
    JobResponse,
    JobStatus,
    JobUpdateRequest,
)
from api.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=201, response_model=JobResponse)
async def create_job(
    body: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await job_service.create_job(db, body.job_type, body.draft_id, body.config)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await job_service.list_jobs(db, status_filter=status)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await job_service.get_job(db, job_id)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    body: JobUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await job_service.update_job_status(
        db, job_id, body.status, result=body.result, error=body.error
    )
