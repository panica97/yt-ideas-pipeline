"""Health check endpoint — public, no auth required."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.database import engine

router = APIRouter(tags=["health"])

_EXPECTED_TABLES = [
    "topics",
    "channels",
    "strategies",
    "drafts",
    "research_history",
    "research_sessions",
    "instruments",
]


@router.get("/api/health")
async def health_check():
    """Check database connectivity and table existence."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

            # Check which tables exist
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            existing_tables = {row[0] for row in result.fetchall()}

        tables = {t: t in existing_tables for t in _EXPECTED_TABLES}
        return {
            "status": "ok",
            "database": "connected",
            "tables": tables,
        }
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "disconnected",
                "tables": {t: False for t in _EXPECTED_TABLES},
            },
        )
