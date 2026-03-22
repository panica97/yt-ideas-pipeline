"""Strategy and draft read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from pydantic import BaseModel
from api.models.schemas.draft import DraftsListResponse, FillTodoRequest
from api.models.schemas.strategy import StrategiesListResponse, StatusUpdate, StrategyResponse
from api.services import strategy_service

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class UpdateDraftDataRequest(BaseModel):
    data: dict


# NOTE: The /drafts routes MUST come before /{strategy_name} to avoid
# "drafts" being captured as a strategy_name path parameter.

@router.get("/drafts", response_model=DraftsListResponse)
async def list_drafts(
    has_todos: bool | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    total, drafts = await strategy_service.list_drafts(db, has_todos=has_todos, status=status)
    return {"total": total, "drafts": drafts}


@router.get("/drafts/{strat_code}")
async def get_draft(strat_code: int, db: AsyncSession = Depends(get_db)):
    return await strategy_service.get_draft_by_code(db, strat_code)


@router.patch("/drafts/{strat_code}/fill-todo")
async def fill_todo(
    strat_code: int,
    body: FillTodoRequest,
    db: AsyncSession = Depends(get_db),
):
    return await strategy_service.fill_todo(db, strat_code, body.path, body.value)


@router.put("/drafts/{strat_code}/data")
async def update_draft_data(
    strat_code: int,
    body: UpdateDraftDataRequest,
    db: AsyncSession = Depends(get_db),
):
    return await strategy_service.update_draft_data(db, strat_code, body.data)


@router.get("", response_model=StrategiesListResponse)
async def list_strategies(
    channel: str | None = Query(None),
    search: str | None = Query(None),
    session_id: int | None = Query(None),
    has_draft: bool | None = Query(None),
    has_todos: bool | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    total, strategies = await strategy_service.list_strategies(
        db, channel=channel, search=search, session_id=session_id,
        has_draft=has_draft, has_todos=has_todos, status=status,
    )
    return {"total": total, "strategies": strategies}


# NOTE: /status and /drafts routes MUST come before /{strategy_name}
# to avoid being captured as a strategy_name path parameter.

@router.get("/{strategy_name}/drafts")
async def get_drafts_by_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.get_drafts_by_strategy(db, strategy_name)


@router.patch("/{strategy_name}/status", response_model=StrategyResponse)
async def set_strategy_status(
    strategy_name: str,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await strategy_service.set_strategy_status(db, strategy_name, body.status)


@router.get("/{strategy_name}", response_model=StrategyResponse)
async def get_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.get_strategy_by_name(db, strategy_name)
