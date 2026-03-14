"""LISTEN/NOTIFY handler for real-time research session updates via WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Set

import asyncpg
from fastapi import WebSocket

from api.config import settings
from api.models.schemas.research import get_step_display

logger = logging.getLogger(__name__)


class ResearchWatcher:
    """Maintains a dedicated asyncpg connection for LISTEN research_update
    and broadcasts session state changes to connected WebSocket clients."""

    def __init__(self, database_url: str | None = None):
        url = database_url or settings.DATABASE_URL
        # asyncpg uses plain postgresql:// DSN, not the SQLAlchemy dialect URL
        self._dsn = (
            url.replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
        )
        self._conn: asyncpg.Connection | None = None
        self._clients: Set[WebSocket] = set()
        self._pool: asyncpg.Pool | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to PostgreSQL and start LISTEN."""
        self._running = True
        try:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=2)
            self._conn = await asyncpg.connect(self._dsn)
            await self._conn.add_listener("research_update", self._on_notify)
            logger.info("ResearchWatcher: LISTEN research_update started")
        except Exception:
            logger.exception("ResearchWatcher: failed to start LISTEN")
            # Non-fatal — the watcher will retry via _reconnect if needed.

    async def stop(self) -> None:
        """Clean up connections."""
        self._running = False
        if self._conn:
            try:
                await self._conn.remove_listener("research_update", self._on_notify)
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._pool:
            await self._pool.close()
            self._pool = None
        logger.info("ResearchWatcher: stopped")

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def register(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ------------------------------------------------------------------
    # Notification handling
    # ------------------------------------------------------------------

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Called by asyncpg when a NOTIFY arrives (sync callback)."""
        asyncio.ensure_future(self._handle_notify(payload))

    async def _handle_notify(self, payload: str) -> None:
        try:
            session_id = int(payload)
        except (ValueError, TypeError):
            logger.warning("ResearchWatcher: invalid payload %r", payload)
            return

        session_data = await self._get_session(session_id)
        if session_data:
            await self._broadcast({"sessions": [session_data]})

    async def _get_session(self, session_id: int) -> dict[str, Any] | None:
        """Query the updated session from PostgreSQL."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT rs.*, t.slug AS topic_slug
                    FROM research_sessions rs
                    LEFT JOIN topics t ON rs.topic_id = t.id
                    WHERE rs.id = $1
                    """,
                    session_id,
                )
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "status": row["status"],
                    "topic": row["topic_slug"],
                    "step": row["step"],
                    "step_name": row["step_name"],
                    "step_display": get_step_display(row["step_name"]),
                    "total_steps": row["total_steps"],
                    "channel": row["channel"],
                    "videos_processing": list(row["videos_processing"] or []),
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                    "error_detail": row["error_detail"],
                    "result_summary": json.loads(row["result_summary"]) if row["result_summary"] else None,
                }
        except Exception:
            logger.exception("ResearchWatcher: failed to query session %d", session_id)
            return None

    async def get_active_sessions(self) -> list[dict[str, Any]]:
        """Query all running sessions — sent on WebSocket connect."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT rs.*, t.slug AS topic_slug
                    FROM research_sessions rs
                    LEFT JOIN topics t ON rs.topic_id = t.id
                    WHERE rs.status = 'running'
                    ORDER BY rs.started_at DESC
                    """
                )
                sessions = []
                for row in rows:
                    sessions.append({
                        "id": row["id"],
                        "status": row["status"],
                        "topic": row["topic_slug"],
                        "step": row["step"],
                        "step_name": row["step_name"],
                        "step_display": get_step_display(row["step_name"]),
                        "total_steps": row["total_steps"],
                        "channel": row["channel"],
                        "videos_processing": list(row["videos_processing"] or []),
                        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                        "error_detail": row["error_detail"],
                        "result_summary": json.loads(row["result_summary"]) if row["result_summary"] else None,
                    })
                return sessions
        except Exception:
            logger.exception("ResearchWatcher: failed to query active sessions")
            return []

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Send data to all connected WebSocket clients."""
        dead: set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead
