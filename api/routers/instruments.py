"""Instrument CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.instrument import (
    InstrumentCreate,
    InstrumentResponse,
    InstrumentsListResponse,
    InstrumentUpdate,
)
from api.services import instrument_service

router = APIRouter(prefix="/api/instruments", tags=["instruments"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=InstrumentsListResponse)
async def list_instruments(db: AsyncSession = Depends(get_db)):
    instruments = await instrument_service.list_instruments(db)
    return {"total": len(instruments), "instruments": instruments}


@router.get("/{symbol}", response_model=InstrumentResponse)
async def get_instrument(symbol: str, db: AsyncSession = Depends(get_db)):
    return await instrument_service.get_instrument(db, symbol)


@router.post("", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
async def create_instrument(body: InstrumentCreate, db: AsyncSession = Depends(get_db)):
    return await instrument_service.create_instrument(db, body)


@router.put("/{symbol}", response_model=InstrumentResponse)
async def update_instrument(symbol: str, body: InstrumentUpdate, db: AsyncSession = Depends(get_db)):
    return await instrument_service.update_instrument(db, symbol, body)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instrument(symbol: str, db: AsyncSession = Depends(get_db)):
    await instrument_service.delete_instrument(db, symbol)
