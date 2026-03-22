"""Export endpoints — download data as YAML or JSON files."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas.export import ExportFormat
from api.services import export_service

router = APIRouter(prefix="/api/export", tags=["export"])


def _file_response(content: str, filename: str, fmt: ExportFormat) -> Response:
    """Build a downloadable file response with proper headers."""
    if fmt == ExportFormat.yaml:
        media_type = "application/x-yaml"
    else:
        media_type = "application/json"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/channels")
async def export_channels(
    format: ExportFormat = Query(ExportFormat.yaml, alias="format"),
    db: AsyncSession = Depends(get_db),
):
    data = await export_service.export_channels(db)
    if format == ExportFormat.yaml:
        content = export_service.serialize_yaml(data)
        filename = "channels.yaml"
    else:
        content = export_service.serialize_json(data)
        filename = "channels.json"
    return _file_response(content, filename, format)


@router.get("/strategies")
async def export_strategies(
    format: ExportFormat = Query(ExportFormat.yaml, alias="format"),
    db: AsyncSession = Depends(get_db),
):
    data = await export_service.export_strategies(db)
    if format == ExportFormat.yaml:
        content = export_service.serialize_yaml(data)
        filename = "strategies.yaml"
    else:
        content = export_service.serialize_json(data)
        filename = "strategies.json"
    return _file_response(content, filename, format)


@router.get("/drafts/{strat_code}")
async def export_draft(
    strat_code: int,
    format: ExportFormat = Query(ExportFormat.json, alias="format"),
    db: AsyncSession = Depends(get_db),
):
    data = await export_service.export_draft(db, strat_code)
    if format == ExportFormat.yaml:
        content = export_service.serialize_yaml(data)
        filename = f"draft_{strat_code}.yaml"
    else:
        content = export_service.serialize_json(data)
        filename = f"draft_{strat_code}.json"
    return _file_response(content, filename, format)
