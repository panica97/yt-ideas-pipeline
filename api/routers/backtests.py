"""Backtest job endpoints."""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas.backtest import (
    BacktestCompleteRequest,
    BacktestCreateRequest,
    BacktestFailRequest,
    BacktestJobResponse,
    BacktestListResponse,
    BacktestStatus,
    PipelineStatusResponse,
)
from api.services import backtest_service

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


@router.post("", status_code=201, response_model=BacktestJobResponse)
async def create_backtest(
    body: BacktestCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.create_job(db, body)


@router.get("", response_model=BacktestListResponse)
async def list_backtests(
    draft_strat_code: int | None = Query(None),
    status: BacktestStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.list_jobs(db, draft_strat_code=draft_strat_code, status_filter=status)


@router.get("/pending")
async def get_pending_job(
    db: AsyncSession = Depends(get_db),
):
    job = await backtest_service.get_pending_job(db)
    if job is None:
        return Response(status_code=204)
    return BacktestJobResponse.model_validate(job, from_attributes=True)


@router.get("/pipeline/{group_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    group_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.get_pipeline(db, group_id)


@router.get("/{job_id}", response_model=BacktestJobResponse)
async def get_backtest(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.get_job(db, job_id)


@router.delete("/{job_id}", status_code=204)
async def cancel_backtest(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    await backtest_service.cancel_job(db, job_id)


# ---------------------------------------------------------------------------
# Worker-only endpoints (claim, results, fail)
#
# These endpoints are intended for the backtest worker process, not end users.
# They share the same API key auth as user-facing endpoints. This is an
# acceptable trade-off for IRT because it is a single-user, locally-deployed
# tool — adding separate worker auth (e.g. a dedicated worker API key or
# mTLS) would be overengineering at this stage. If IRT becomes multi-user or
# publicly exposed, revisit this (see audit_02 H-03).
# ---------------------------------------------------------------------------

@router.patch("/{job_id}/claim", response_model=BacktestJobResponse)
async def claim_backtest(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.claim_job(db, job_id)


@router.post("/{job_id}/results", response_model=BacktestJobResponse)
async def complete_backtest(
    job_id: int,
    body: BacktestCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.complete_job(db, job_id, body.metrics, body.trades)


@router.patch("/{job_id}/fail", response_model=BacktestJobResponse)
async def fail_backtest(
    job_id: int,
    body: BacktestFailRequest,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.fail_job(db, job_id, body.error_message)
