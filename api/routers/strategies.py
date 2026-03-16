"""Strategy and draft read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.draft import DraftsListResponse
from api.models.schemas.strategy import StrategiesListResponse, StrategyResponse
from api.services import strategy_service

router = APIRouter(prefix="/api/strategies", tags=["strategies"], dependencies=[Depends(verify_api_key)])


# NOTE: The /drafts routes MUST come before /{strategy_name} to avoid
# "drafts" being captured as a strategy_name path parameter.

@router.get("/drafts", response_model=DraftsListResponse)
async def list_drafts(
    has_todos: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    total, drafts = await strategy_service.list_drafts(db, has_todos=has_todos)
    return {"total": total, "drafts": drafts}


@router.get("/drafts/{strat_code}")
async def get_draft(strat_code: int, db: AsyncSession = Depends(get_db)):
    return await strategy_service.get_draft_by_code(db, strat_code)


@router.get("", response_model=StrategiesListResponse)
async def list_strategies(
    channel: str | None = Query(None),
    search: str | None = Query(None),
    session_id: int | None = Query(None),
    has_draft: bool | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    total, strategies = await strategy_service.list_strategies(
        db, channel=channel, search=search, session_id=session_id,
        has_draft=has_draft, status=status,
    )
    return {"total": total, "strategies": strategies}


# NOTE: PATCH validate/unvalidate routes MUST come before /{strategy_name}
# to avoid "validate"/"unvalidate" being captured as a strategy_name.

@router.patch("/{strategy_name}/validate", response_model=StrategyResponse)
async def validate_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.validate_strategy(db, strategy_name)


@router.patch("/{strategy_name}/unvalidate", response_model=StrategyResponse)
async def unvalidate_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.unvalidate_strategy(db, strategy_name)


@router.get("/{strategy_name}", response_model=StrategyResponse)
async def get_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.get_strategy_by_name(db, strategy_name)
