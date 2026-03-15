"""Research session endpoints: REST + WebSocket."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.dependencies import get_db, verify_api_key
from api.services import research_session_service

router = APIRouter(tags=["research"])

# The ResearchWatcher instance is set at startup from main.py
_watcher = None


def set_watcher(watcher) -> None:
    global _watcher
    _watcher = watcher


@router.get("/api/research/sessions")
async def get_research_sessions(
    limit: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_api_key),
):
    """Return the last N completed/error research sessions with details."""
    sessions = await research_session_service.get_sessions(db, limit=limit)
    return {"sessions": sessions}


@router.websocket("/api/research/status")
async def research_status_ws(
    websocket: WebSocket,
    api_key: str | None = Query(None),
):
    """WebSocket endpoint for live research updates.

    Auth via query parameter ``api_key``.
    On connect: sends current active sessions.
    On NOTIFY: pushes updated session data.
    """
    # Auth check
    if not api_key or api_key != settings.DASHBOARD_API_KEY:
        await websocket.close(code=4001, reason="API key invalida o no proporcionada")
        return

    await websocket.accept()

    if _watcher is None:
        await websocket.send_json({"sessions": []})
        await websocket.close(code=1011, reason="Research watcher not available")
        return

    _watcher.register(websocket)

    try:
        # Send current active sessions on connect
        sessions = await _watcher.get_active_sessions()
        await websocket.send_json({"sessions": sessions})

        # Keep the connection alive, waiting for client messages or disconnect
        while True:
            # We don't expect client messages, but we need to keep the loop
            # alive to detect disconnection.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _watcher.unregister(websocket)
