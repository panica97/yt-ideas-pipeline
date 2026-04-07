"""Async query logic for backtest jobs."""

from __future__ import annotations

import uuid as _uuid
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
        n_paths=getattr(body, "n_paths", None),
        fit_years=getattr(body, "fit_years", None),
        n_simulations=getattr(body, "n_simulations", None),
        monkey_mode=getattr(body, "monkey_mode", None),
        stress_test_name=getattr(body, "stress_test_name", None),
        stress_param_overrides=getattr(body, "stress_param_overrides", None),
        stress_single_overrides=getattr(body, "stress_single_overrides", None),
        stress_max_parallel=getattr(body, "stress_max_parallel", None),
        pipeline_group=getattr(body, "pipeline_group", None),
        pipeline_config=getattr(body, "pipeline_config", None),
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
        # Gracefully accept if already in a terminal state (race with pipeline
        # cancellation: worker finishes while _cancel_pipeline_siblings already
        # marked it as failed/completed).
        if job.status in ("completed", "failed"):
            refreshed = await db.execute(
                select(BacktestJob)
                .options(joinedload(BacktestJob.result))
                .where(BacktestJob.id == job.id)
            )
            return refreshed.scalar_one()
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

    # --- Pipeline orchestration ---
    if job.pipeline_group and job.pipeline_config:
        await _create_pipeline_children(db, job)

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
        # Gracefully accept if already in a terminal state (race with pipeline
        # cancellation: worker finishes while _cancel_pipeline_siblings already
        # marked it as failed/completed).
        if job.status in ("completed", "failed"):
            refreshed = await db.execute(
                select(BacktestJob)
                .options(joinedload(BacktestJob.result))
                .where(BacktestJob.id == job.id)
            )
            return refreshed.scalar_one()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not running (current status: {job.status})",
        )

    job.status = "failed"
    job.error_message = error_message
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()

    # --- Pipeline failure propagation ---
    if job.pipeline_group:
        await _cancel_pipeline_siblings(db, job)

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


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

async def get_pipeline(
    db: AsyncSession, group_id: _uuid.UUID
) -> dict[str, Any]:
    """Get all jobs for a pipeline group with derived overall status."""
    result = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.pipeline_group == group_id)
        .order_by(BacktestJob.created_at.asc())
    )
    jobs = result.unique().scalars().all()

    # Derive status
    statuses = [j.status for j in jobs]
    if not statuses:
        overall = "pending"
    elif any(s == "failed" for s in statuses):
        overall = "failed"
    elif all(s == "completed" for s in statuses):
        overall = "completed"
    elif all(s == "pending" for s in statuses):
        overall = "pending"
    else:
        overall = "running"

    return {
        "pipeline_group": group_id,
        "status": overall,
        "jobs": jobs,
    }


async def _create_pipeline_children(
    db: AsyncSession, parent: BacktestJob
) -> list[BacktestJob]:
    """Create MC, Monkey, and Stress child jobs from a completed pipeline parent."""
    config = parent.pipeline_config  # dict with keys: montecarlo, monkey, stress
    children = []

    # Map of mode -> config key -> mode-specific field mappings
    mode_configs = {
        "montecarlo": {
            "config_key": "montecarlo",
            "fields": lambda c: {
                "n_paths": c.get("n_paths", 1000),
                "fit_years": c.get("fit_years", 10),
            },
        },
        "monkey": {
            "config_key": "monkey",
            "fields": lambda c: {
                "n_simulations": c.get("n_simulations", 1000),
                "monkey_mode": c.get("monkey_mode", "A"),
            },
        },
        "stress": {
            "config_key": "stress",
            "fields": lambda c: {
                "stress_test_name": c.get("stress_test_name"),
                "stress_param_overrides": c.get("stress_param_overrides"),
                "stress_single_overrides": c.get("stress_single_overrides"),
                "stress_max_parallel": c.get("stress_max_parallel", 4),
            },
        },
    }

    for mode, cfg in mode_configs.items():
        mode_params = config.get(cfg["config_key"], {})
        extra_fields = cfg["fields"](mode_params)

        child = BacktestJob(
            draft_strat_code=parent.draft_strat_code,
            symbol=parent.symbol,
            timeframe=parent.timeframe,
            start_date=parent.start_date,
            end_date=parent.end_date,
            status="pending",
            mode=mode,
            pipeline_group=parent.pipeline_group,
            pipeline_config=None,  # only parent stores config
            **extra_fields,
        )
        db.add(child)
        children.append(child)

    await db.flush()
    return children


async def _cancel_pipeline_siblings(
    db: AsyncSession, failed_job: BacktestJob
) -> None:
    """Cancel all pending/running siblings in the same pipeline."""
    siblings = await db.execute(
        select(BacktestJob)
        .where(
            BacktestJob.pipeline_group == failed_job.pipeline_group,
            BacktestJob.id != failed_job.id,
            BacktestJob.status.in_(["pending", "running"]),
        )
    )
    for sibling in siblings.scalars().all():
        sibling.status = "failed"
        sibling.error_message = f"Pipeline cancelled: {failed_job.mode} failed"
        sibling.completed_at = datetime.now(timezone.utc)

    await db.flush()
