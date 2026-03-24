"""Async query logic for backtest jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from tools.db.models import BacktestJob, BacktestResult, Draft, Strategy


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_job(
    db: AsyncSession, body: Any
) -> BacktestJob:
    """Create a new backtest job after validating the draft is backtestable."""
    # 1. Validate draft exists
    result = await db.execute(
        select(Draft).where(Draft.strat_code == body.draft_strat_code)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )

    # 2. Validate strategy status = validated and todo_count = 0
    if draft.strategy_id is not None:
        strat_result = await db.execute(
            select(Strategy).where(Strategy.id == draft.strategy_id)
        )
        strategy = strat_result.scalar_one_or_none()
        strategy_status = strategy.status if strategy else None
    else:
        strategy_status = None

    if strategy_status != "validated" or draft.todo_count != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Draft is not backtestable: strategy must be validated and draft must have no pending TODOs",
        )

    # 3. Validate date range
    if body.start_date >= body.end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before end_date",
        )

    # 4. Insert job
    job = BacktestJob(
        draft_strat_code=body.draft_strat_code,
        symbol=body.symbol,
        timeframe=body.timeframe,
        start_date=body.start_date,
        end_date=body.end_date,
        status="pending",
        mode=getattr(body, "mode", "simple"),
        debug=getattr(body, "debug", False),
    )
    db.add(job)
    await db.flush()

    # Re-fetch with joinedload so the `result` relationship is populated
    # (avoids MissingGreenlet when FastAPI serializes the response).
    refreshed = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job.id)
    )
    return refreshed.scalar_one()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_job(db: AsyncSession, job_id: int) -> BacktestJob:
    """Get a single backtest job with its result (if any)."""
    result = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found",
        )
    return job


async def list_jobs(
    db: AsyncSession,
    draft_strat_code: int | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List backtest jobs with optional filters, ordered by created_at DESC."""
    query = select(BacktestJob).options(joinedload(BacktestJob.result))

    if draft_strat_code is not None:
        query = query.where(BacktestJob.draft_strat_code == draft_strat_code)

    if status_filter is not None:
        query = query.where(BacktestJob.status == status_filter)

    # Count
    count_q = select(func.count()).select_from(
        select(BacktestJob.id).where(
            *([BacktestJob.draft_strat_code == draft_strat_code] if draft_strat_code is not None else []),
            *([BacktestJob.status == status_filter] if status_filter is not None else []),
        ).subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    query = query.order_by(BacktestJob.created_at.desc())
    rows = (await db.execute(query)).unique().scalars().all()

    return {"total": total, "jobs": rows}


# ---------------------------------------------------------------------------
# Delete / Cancel
# ---------------------------------------------------------------------------

async def cancel_job(db: AsyncSession, job_id: int) -> None:
    """Delete a backtest job. Rejects deletion of running jobs (409)."""
    result = await db.execute(
        select(BacktestJob).where(BacktestJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found",
        )

    if job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a running backtest job",
        )

    await db.delete(job)
    await db.flush()


# ---------------------------------------------------------------------------
# Worker operations
# ---------------------------------------------------------------------------

async def claim_job(db: AsyncSession, job_id: int) -> BacktestJob:
    """Atomically claim a pending job by setting status to 'running'."""
    result = await db.execute(
        select(BacktestJob)
        .where(BacktestJob.id == job_id)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found",
        )

    if job.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not pending (current status: {job.status})",
        )

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.flush()

    refreshed = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job.id)
    )
    return refreshed.scalar_one()


async def complete_job(
    db: AsyncSession, job_id: int, metrics: dict[str, Any], trades: list[dict[str, Any]] | None = None
) -> BacktestJob:
    """Mark a job as completed and store its results."""
    result = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found",
        )

    if job.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not running (current status: {job.status})",
        )

    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)

    backtest_result = BacktestResult(
        job_id=job.id,
        metrics=metrics,
        trades=trades or [],
    )
    db.add(backtest_result)
    await db.flush()

    refreshed = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job.id)
    )
    return refreshed.scalar_one()


async def fail_job(
    db: AsyncSession, job_id: int, error_message: str
) -> BacktestJob:
    """Mark a job as failed with an error message."""
    result = await db.execute(
        select(BacktestJob).where(BacktestJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found",
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

    refreshed = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.id == job.id)
    )
    return refreshed.scalar_one()


async def get_pending_job(db: AsyncSession) -> BacktestJob | None:
    """Get the oldest pending job (for worker polling)."""
    result = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.status == "pending")
        .order_by(BacktestJob.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()
