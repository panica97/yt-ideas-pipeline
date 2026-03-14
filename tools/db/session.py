from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker


def _to_sync_url(url: str) -> str:
    """Convert an async database URL to a sync one (asyncpg -> psycopg2)."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def _to_async_url(url: str) -> str:
    """Convert a sync database URL to an async one (psycopg2 -> asyncpg)."""
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# Sync (pipeline)
# ---------------------------------------------------------------------------

def get_sync_engine(url: str | None = None) -> Engine:
    """Create a sync SQLAlchemy engine (psycopg2 driver).

    If *url* is not provided, reads ``DATABASE_URL_SYNC`` or ``DATABASE_URL``
    from the environment and converts to a sync driver URL.
    """
    if url is None:
        url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "")
    url = _to_sync_url(url)
    return create_engine(url, pool_pre_ping=True)


def get_sync_session(url: str | None = None) -> Session:
    """Return a new sync ``Session`` bound to the default engine."""
    engine = get_sync_engine(url)
    factory = sessionmaker(bind=engine)
    return factory()


@contextmanager
def sync_session_ctx(url: str | None = None):
    """Context manager that yields a sync session and commits/rolls back."""
    session = get_sync_session(url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Async (API)
# ---------------------------------------------------------------------------

def get_async_engine(url: str | None = None):
    """Create an async SQLAlchemy engine (asyncpg driver).

    If *url* is not provided, reads ``DATABASE_URL`` from the environment.
    """
    if url is None:
        url = os.environ.get("DATABASE_URL", "")
    url = _to_async_url(url)
    return create_async_engine(url, pool_pre_ping=True)


def get_async_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory."""
    engine = get_async_engine(url)
    return async_sessionmaker(engine, expire_on_commit=False)
