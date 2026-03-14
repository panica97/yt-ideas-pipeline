"""Dashboard statistics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.stats import StatsResponse
from api.services import stats_service

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    return await stats_service.get_stats(db)
