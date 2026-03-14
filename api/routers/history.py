"""Research history endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.history import HistoryListResponse, HistoryStatsResponse
from api.services import history_service

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=HistoryListResponse)
async def list_history(
    topic: str | None = Query(None),
    channel: str | None = Query(None),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    sort: str = Query("researched_at"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    total, items = await history_service.list_history(
        db,
        topic=topic,
        channel=channel,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/stats", response_model=HistoryStatsResponse)
async def history_stats(db: AsyncSession = Depends(get_db)):
    return await history_service.get_history_stats(db)
