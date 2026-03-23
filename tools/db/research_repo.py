"""Sync repository for research sessions and history (pipeline side).

All functions receive a SQLAlchemy sync ``Session`` and operate
synchronously using psycopg2.  After each session state change,
``NOTIFY research_update`` is fired so FastAPI can push updates
to connected WebSocket clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import ResearchHistory, ResearchSession, Topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notify(session: Session, session_id: int) -> None:
    """Send a PostgreSQL NOTIFY on the ``research_update`` channel."""
    session.execute(
        text("NOTIFY research_update, :payload"),
        {"payload": str(session_id)},
    )


def resolve_topic_id(session: Session, topic_slug: str) -> int | None:
    """Resolve a topic slug to its ID."""
    stmt = select(Topic.id).where(Topic.slug == topic_slug)
    result = session.execute(stmt).scalar_one_or_none()
    return result


# ---------------------------------------------------------------------------
# Research sessions
# ---------------------------------------------------------------------------

def create_session(
    session: Session,
    topic_slug: str | None = None,
    label: str | None = None,
    total_steps: int = 8,
) -> ResearchSession:
    """Create a new research session in 'running' state.

    Args:
        session: SQLAlchemy sync session.
        topic_slug: The topic slug being researched (optional).
        label: Free-text description for non-topic sessions (optional).
        total_steps: Number of pipeline steps (TOPIC=8, VIDEO=6, IDEA=5).

    Returns:
        The newly created ``ResearchSession`` row.
    """
    topic_id = resolve_topic_id(session, topic_slug) if topic_slug else None
    rs = ResearchSession(
        status="running",
        topic_id=topic_id,
        label=label,
        step=0,
        step_name="preflight",
        total_steps=total_steps,
    )
    session.add(rs)
    session.flush()  # get the auto-generated ID
    _notify(session, rs.id)
    return rs


def update_session_step(
    session: Session,
    session_id: int,
    step: int,
    step_name: str,
    channel: str | None = None,
    videos: list[str] | None = None,
) -> None:
    """Update the current step of a running research session.

    Fires ``NOTIFY research_update`` after the update.
    """
    stmt = select(ResearchSession).where(ResearchSession.id == session_id)
    rs = session.execute(stmt).scalar_one_or_none()
    if rs is None:
        return
    rs.step = step
    rs.step_name = step_name
    if channel is not None:
        rs.channel = channel
    if videos is not None:
        rs.videos_processing = videos
    rs.updated_at = datetime.utcnow()
    session.flush()
    _notify(session, session_id)


def complete_session(
    session: Session,
    session_id: int,
    result_summary: dict[str, Any] | None = None,
    strategies_found: int | None = None,
    drafts_created: int | None = None,
) -> None:
    """Mark a research session as completed.

    Fires ``NOTIFY research_update`` after the update.
    """
    stmt = select(ResearchSession).where(ResearchSession.id == session_id)
    rs = session.execute(stmt).scalar_one_or_none()
    if rs is None:
        return
    rs.status = "completed"
    rs.completed_at = datetime.utcnow()
    rs.result_summary = result_summary
    if strategies_found is not None:
        rs.strategies_found = strategies_found
    if drafts_created is not None:
        rs.drafts_created = drafts_created
    rs.updated_at = datetime.utcnow()
    session.flush()
    _notify(session, session_id)


def error_session(
    session: Session,
    session_id: int,
    error_detail: str,
) -> None:
    """Mark a research session as errored.

    Fires ``NOTIFY research_update`` after the update.
    """
    stmt = select(ResearchSession).where(ResearchSession.id == session_id)
    rs = session.execute(stmt).scalar_one_or_none()
    if rs is None:
        return
    rs.status = "error"
    rs.error_detail = error_detail
    rs.completed_at = datetime.utcnow()
    rs.updated_at = datetime.utcnow()
    session.flush()
    _notify(session, session_id)


def get_active_sessions(session: Session) -> list[ResearchSession]:
    """Return all sessions with ``status = 'running'``."""
    stmt = (
        select(ResearchSession)
        .where(ResearchSession.status == "running")
        .order_by(ResearchSession.started_at.desc())
    )
    return list(session.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Research history
# ---------------------------------------------------------------------------

def add_history(
    session: Session,
    video_id: str,
    url: str,
    channel_id: int | None = None,
    topic_id: int | None = None,
    strategies_found: int = 0,
    classification: str | None = None,
    title: str | None = None,
    session_id: int | None = None,
) -> ResearchHistory:
    """Insert a research history entry with deduplication.

    If a history entry with the same ``(video_id, topic_id)`` already exists,
    the existing row is returned unchanged.

    Args:
        session_id: Optional FK to ``research_sessions.id`` for direct
            session-history correlation (preferred over time-window matching).
    """
    if topic_id is None:
        stmt = select(ResearchHistory).where(
            ResearchHistory.video_id == video_id,
            ResearchHistory.topic_id.is_(None),
        )
    else:
        stmt = select(ResearchHistory).where(
            ResearchHistory.video_id == video_id,
            ResearchHistory.topic_id == topic_id,
        )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = ResearchHistory(
        video_id=video_id,
        url=url,
        channel_id=channel_id,
        topic_id=topic_id,
        strategies_found=strategies_found,
        classification=classification,
        title=title,
        session_id=session_id,
    )
    session.add(entry)
    session.flush()
    return entry
