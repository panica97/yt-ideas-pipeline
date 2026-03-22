"""Async CRUD logic for instruments."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Instrument

from api.models.schemas.instrument import InstrumentCreate, InstrumentUpdate


async def list_instruments(db: AsyncSession) -> list[Instrument]:
    """Return all instruments ordered by symbol."""
    result = await db.execute(select(Instrument).order_by(Instrument.symbol))
    return list(result.scalars().all())


async def get_instrument(db: AsyncSession, symbol: str) -> Instrument:
    """Return a single instrument by symbol, or raise 404."""
    result = await db.execute(
        select(Instrument).where(Instrument.symbol == symbol)
    )
    instrument = result.scalar_one_or_none()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument '{symbol}' not found",
        )
    return instrument


async def create_instrument(
    db: AsyncSession, data: InstrumentCreate
) -> Instrument:
    """Create a new instrument. Raise 409 if symbol already exists."""
    existing = await db.execute(
        select(Instrument).where(Instrument.symbol == data.symbol)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Instrument with symbol '{data.symbol}' already exists",
        )

    instrument = Instrument(**data.model_dump())
    db.add(instrument)
    await db.commit()
    await db.refresh(instrument)
    return instrument


async def update_instrument(
    db: AsyncSession, symbol: str, data: InstrumentUpdate
) -> Instrument:
    """Update an existing instrument by symbol. Raise 404 if not found."""
    instrument = await get_instrument(db, symbol)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(instrument, field, value)

    await db.commit()
    await db.refresh(instrument)
    return instrument


async def delete_instrument(db: AsyncSession, symbol: str) -> None:
    """Delete an instrument by symbol. Raise 404 if not found."""
    instrument = await get_instrument(db, symbol)
    await db.delete(instrument)
    await db.commit()
