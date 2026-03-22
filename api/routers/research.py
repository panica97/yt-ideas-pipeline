"""Research session endpoints: REST + WebSocket."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.dependencies import get_db
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
):
    """Return the last N completed/error research sessions with details."""
    sessions = await research_session_service.get_sessions(db, limit=limit)
    return {"sessions": sessions}


@router.get("/api/research/sessions/{session_id}")
async def get_research_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return a single research session with full details."""
    session = await research_session_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.websocket("/api/research/status")
async def research_status_ws(websocket: WebSocket):
    """WebSocket endpoint for live research updates.

    Auth via first message: client sends ``{"type": "auth", "api_key": "..."}``
    after connection is accepted.
    On auth success: sends current active sessions.
    On NOTIFY: pushes updated session data.
    """
    await websocket.accept()

    # Wait for auth message as the first frame
    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        api_key = msg.get("api_key") if isinstance(msg, dict) else None
    except Exception:
        await websocket.close(code=4001, reason="Invalid auth message")
        return

    if not api_key or api_key != settings.DASHBOARD_API_KEY:
        await websocket.close(code=4001, reason="Invalid or missing API key")
        return

    if _watcher is None:
        await websocket.send_json({"sessions": []})
        await websocket.close(code=1011, reason="Research watcher not available")
        return

    _watcher.register(websocket)

    try:
        # Send current active sessions on successful auth
        sessions = await _watcher.get_active_sessions()
        await websocket.send_json({"sessions": sessions})

        # Keep the connection alive, waiting for client messages or disconnect
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _watcher.unregister(websocket)
