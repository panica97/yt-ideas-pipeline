"""Instrument CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas.data_info import (
    ScanFailRequest,
    ScanJobResponse,
    ScanResultsRequest,
)
from api.models.schemas.instrument import (
    InstrumentCreate,
    InstrumentResponse,
    InstrumentsListResponse,
    InstrumentUpdate,
)
from api.services import data_info_service, instrument_service

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("", response_model=InstrumentsListResponse)
async def list_instruments(db: AsyncSession = Depends(get_db)):
    instruments = await instrument_service.list_instruments(db)
    return {"total": len(instruments), "instruments": instruments}


@router.post("", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
async def create_instrument(body: InstrumentCreate, db: AsyncSession = Depends(get_db)):
    return await instrument_service.create_instrument(db, body)


# ---------------------------------------------------------------------------
# Scan-data endpoints (worker polling flow)
#
# IMPORTANT: /scan-data/pending must be registered BEFORE /scan-data/{job_id}
# to avoid FastAPI treating "pending" as a path parameter.
# ---------------------------------------------------------------------------

@router.post("/scan-data", response_model=ScanJobResponse, status_code=status.HTTP_201_CREATED)
async def create_scan_job(db: AsyncSession = Depends(get_db)):
    return await data_info_service.create_scan_job(db)


@router.get("/scan-data/pending", response_model=ScanJobResponse | None)
async def get_pending_scan_job(db: AsyncSession = Depends(get_db)):
    job = await data_info_service.get_pending_scan_job(db)
    if job is None:
        return Response(status_code=204)
    return job


@router.get("/scan-data/{job_id}", response_model=ScanJobResponse)
async def get_scan_job(job_id: int, db: AsyncSession = Depends(get_db)):
    return await data_info_service.get_scan_job(db, job_id)


@router.patch("/scan-data/{job_id}/claim", response_model=ScanJobResponse)
async def claim_scan_job(job_id: int, db: AsyncSession = Depends(get_db)):
    return await data_info_service.claim_scan_job(db, job_id)


@router.post("/scan-data/{job_id}/results", response_model=ScanJobResponse)
async def complete_scan_job(
    job_id: int,
    body: ScanResultsRequest,
    db: AsyncSession = Depends(get_db),
):
    return await data_info_service.complete_scan_job(db, job_id, body.results)


@router.patch("/scan-data/{job_id}/fail", response_model=ScanJobResponse)
async def fail_scan_job(
    job_id: int,
    body: ScanFailRequest,
    db: AsyncSession = Depends(get_db),
):
    return await data_info_service.fail_scan_job(db, job_id, body.error_message)


# ---------------------------------------------------------------------------
# Instrument CRUD (continued)
# ---------------------------------------------------------------------------

@router.get("/{symbol}", response_model=InstrumentResponse)
async def get_instrument(symbol: str, db: AsyncSession = Depends(get_db)):
    return await instrument_service.get_instrument(db, symbol)


@router.put("/{symbol}", response_model=InstrumentResponse)
async def update_instrument(symbol: str, body: InstrumentUpdate, db: AsyncSession = Depends(get_db)):
    return await instrument_service.update_instrument(db, symbol, body)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instrument(symbol: str, db: AsyncSession = Depends(get_db)):
    await instrument_service.delete_instrument(db, symbol)
