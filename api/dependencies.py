from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def verify_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> str:
    """Validate the API key from the X-API-Key header."""
    if not x_api_key or x_api_key != settings.DASHBOARD_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
