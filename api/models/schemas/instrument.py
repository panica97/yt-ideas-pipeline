"""Pydantic v2 schemas for instruments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InstrumentBase(BaseModel):
    symbol: str
    sec_type: str
    exchange: str
    currency: str = "USD"
    multiplier: float
    min_tick: float
    description: str | None = None


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentUpdate(BaseModel):
    sec_type: str | None = None
    exchange: str | None = None
    currency: str | None = None
    multiplier: float | None = None
    min_tick: float | None = None
    description: str | None = None


class InstrumentResponse(InstrumentBase):
    id: int
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InstrumentsListResponse(BaseModel):
    total: int
    instruments: list[InstrumentResponse]
