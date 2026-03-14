"""Pydantic v2 schemas for research sessions (WebSocket)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResearchSessionResponse(BaseModel):
    id: int
    status: str = "running"
    topic: str | None = None
    step: int = 0
    step_name: str | None = None
    step_display: str | None = None
    total_steps: int = 6
    channel: str | None = None
    videos_processing: list[str] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_detail: str | None = None
    result_summary: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


# Step name -> Human-readable Spanish display name
STEP_DISPLAY_NAMES: dict[str, str] = {
    "preflight": "Comprobacion de autenticacion",
    "yt-scraper": "Buscando videos",
    "notebooklm-analyst": "Extrayendo estrategias",
    "translator": "Traduciendo a JSON",
    "cleanup": "Limpieza",
    "db-manager": "Guardando en base de datos",
    "summary": "Resumen final",
}


def get_step_display(step_name: str | None) -> str | None:
    if step_name is None:
        return None
    return STEP_DISPLAY_NAMES.get(step_name, step_name)
