"""Async query logic for generic job tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Job


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_job(
    db: AsyncSession, job_type: str, draft_id: str, config: dict[str, Any] | None = None
) -> Job:
    """Create a new job with status 'pending'."""
    job = Job(
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        draft_id=draft_id,
        config=config,
        status="pending",
    )
    db.add(job)
    await db.flush()

    # Re-fetch to get server defaults populated
    refreshed = await db.execute(
        select(Job).where(Job.id == job.id)
    )
    return refreshed.scalar_one()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_job(db: AsyncSession, job_id: str) -> Job:
    """Get a single job by its UUID job_id."""
    result = await db.execute(
        select(Job).where(Job.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job


async def list_jobs(
    db: AsyncSession,
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List jobs with optional status filter, ordered by created_at DESC."""
    query = select(Job)

    if status_filter is not None:
        query = query.where(Job.status == status_filter)

    # Count
    count_q = select(func.count()).select_from(
        select(Job.id).where(
            *([Job.status == status_filter] if status_filter is not None else []),
        ).subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    query = query.order_by(Job.created_at.desc())
    rows = (await db.execute(query)).scalars().all()

    return {"total": total, "jobs": rows}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_job_status(
    db: AsyncSession,
    job_id: str,
    new_status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> Job:
    """Update job status, optionally setting result or error."""
    db_result = await db.execute(
        select(Job).where(Job.job_id == job_id)
    )
    job = db_result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.status = new_status

    if result is not None:
        job.result = result

    if error is not None:
        job.error = error

    if new_status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)

    await db.flush()

    refreshed = await db.execute(
        select(Job).where(Job.id == job.id)
    )
    return refreshed.scalar_one()
