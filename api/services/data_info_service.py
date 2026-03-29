"""Async service logic for data-info scan jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Instrument, ScanJob

from api.models.schemas.data_info import ScanResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_scan_job(db: AsyncSession) -> ScanJob:
    """Create a new scan job. Reject if a pending/running job already exists."""
    result = await db.execute(
        select(ScanJob).where(ScanJob.status.in_(["pending", "running"]))
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scan job is already pending or running",
        )

    job = ScanJob(status="pending")
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_scan_job(db: AsyncSession, job_id: int) -> ScanJob:
    """Fetch a scan job by ID, or raise 404."""
    result = await db.execute(
        select(ScanJob).where(ScanJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )
    return job


async def get_pending_scan_job(db: AsyncSession) -> ScanJob | None:
    """Return the oldest pending scan job, or None."""
    result = await db.execute(
        select(ScanJob)
        .where(ScanJob.status == "pending")
        .order_by(ScanJob.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Worker operations
# ---------------------------------------------------------------------------

async def claim_scan_job(db: AsyncSession, job_id: int) -> ScanJob:
    """Claim a pending scan job by transitioning to running."""
    result = await db.execute(
        select(ScanJob)
        .where(ScanJob.id == job_id)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )

    if job.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not in pending state",
        )

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)
    return job


async def complete_scan_job(
    db: AsyncSession, job_id: int, results: list[ScanResult]
) -> ScanJob:
    """Complete a scan job: store results and update matching instruments."""
    result = await db.execute(
        select(ScanJob).where(ScanJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )

    if job.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not running (current status: {job.status})",
        )

    # Update matching instruments
    for scan_result in results:
        instr_result = await db.execute(
            select(Instrument).where(Instrument.symbol == scan_result.symbol)
        )
        instrument = instr_result.scalar_one_or_none()
        if instrument:
            instrument.data_from = scan_result.data_from
            instrument.data_to = scan_result.data_to
        else:
            logger.warning(
                "Scan result symbol '%s' does not match any instrument, skipping",
                scan_result.symbol,
            )

    # Store results and complete
    job.results = [r.model_dump(mode="json") for r in results]
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)
    return job


async def fail_scan_job(
    db: AsyncSession, job_id: int, error_message: str
) -> ScanJob:
    """Mark a scan job as failed with an error message."""
    result = await db.execute(
        select(ScanJob).where(ScanJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )

    if job.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not running (current status: {job.status})",
        )

    job.status = "failed"
    job.error_message = error_message
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)
    return job
