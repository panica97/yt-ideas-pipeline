"""Async query logic for research sessions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, ResearchHistory, ResearchSession, Topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_video_query(
    session: ResearchSession,
    *,
    extra_columns: tuple = (),
) -> "select":
    """Build a query for history items linked to *session*.

    Strategy:
    1. If any history rows already carry ``session_id`` (new records), use that
       for exact correlation -- no time-window ambiguity.
    2. Fall back to the legacy time-window + topic_id heuristic so that
       sessions created before the ``session_id`` column was added still
       resolve their videos correctly.
    """
    base_cols = (
        ResearchHistory.video_id,
        ResearchHistory.url,
        ResearchHistory.strategies_found,
        ResearchHistory.classification,
        ResearchHistory.title,
    )
    cols = base_cols + extra_columns + (Channel.name.label("channel_name"),)

    video_q = (
        select(*cols)
        .outerjoin(Channel, ResearchHistory.channel_id == Channel.id)
    )

    # Prefer direct session_id match; fall back to time-window for old rows
    # We combine both: rows explicitly tagged with this session_id, OR rows
    # matching the legacy time-window heuristic (only when topic_id is set,
    # to avoid the cross-session bleed that M-06 describes).
    direct = ResearchHistory.session_id == session.id

    if session.started_at:
        time_filter = ResearchHistory.researched_at >= session.started_at
        if session.completed_at:
            time_filter = time_filter & (
                ResearchHistory.researched_at <= session.completed_at
            )
        if session.topic_id is not None:
            # Legacy: time-window scoped by topic -- safe from cross-bleed
            legacy = time_filter & (
                ResearchHistory.topic_id == session.topic_id
            )
        else:
            # No topic_id -- legacy path would bleed across sessions, so
            # only use it for rows that have no session_id at all (truly old).
            legacy = time_filter & (
                ResearchHistory.session_id.is_(None)
            ) & (
                ResearchHistory.topic_id.is_(None)
            )
        video_q = video_q.where(or_(direct, legacy))
    else:
        video_q = video_q.where(direct)

    return video_q


async def get_sessions(
    db: AsyncSession,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the last N completed/error research sessions with videos."""
    # Fetch sessions joined with topic
    session_q = (
        select(ResearchSession, Topic.slug.label("topic_slug"))
        .outerjoin(Topic, ResearchSession.topic_id == Topic.id)
        .where(ResearchSession.status.in_(["completed", "error"]))
        .order_by(desc(ResearchSession.started_at))
        .limit(limit)
    )
    session_rows = (await db.execute(session_q)).all()

    results: list[dict[str, Any]] = []
    for row in session_rows:
        session: ResearchSession = row[0]
        topic_slug: str | None = row[1]

        # Compute duration
        duration_seconds: int | None = None
        if session.started_at and session.completed_at:
            delta = session.completed_at - session.started_at
            duration_seconds = int(delta.total_seconds())

        # Fetch related history items (videos) for this session
        video_q = _build_video_query(session)
        video_rows = (await db.execute(video_q)).all()
        videos: list[dict[str, Any]] = []
        for vrow in video_rows:
            videos.append({
                "video_id": vrow[0],
                "url": vrow[1],
                "strategies_found": vrow[2],
                "classification": vrow[3],
                "title": vrow[4],
                "channel": vrow[5],
            })

        results.append({
            "id": session.id,
            "status": session.status,
            "topic": topic_slug,
            "label": session.label,
            "title": topic_slug or session.label or "Untitled session",
            "strategies_found": session.strategies_found,
            "drafts_created": session.drafts_created,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "duration_seconds": duration_seconds,
            "result_summary": session.result_summary,
            "error_detail": session.error_detail,
            "videos": videos,
        })

    return results


async def get_session_by_id(
    db: AsyncSession,
    session_id: int,
) -> dict[str, Any] | None:
    """Return a single research session with its videos, or None if not found."""
    session_q = (
        select(ResearchSession, Topic.slug.label("topic_slug"))
        .outerjoin(Topic, ResearchSession.topic_id == Topic.id)
        .where(ResearchSession.id == session_id)
    )
    row = (await db.execute(session_q)).first()
    if not row:
        return None

    session: ResearchSession = row[0]
    topic_slug: str | None = row[1]

    # Compute duration
    duration_seconds: int | None = None
    if session.started_at and session.completed_at:
        delta = session.completed_at - session.started_at
        duration_seconds = int(delta.total_seconds())

    # Fetch related history items (videos) for this session
    video_q = _build_video_query(
        session, extra_columns=(ResearchHistory.researched_at,)
    )
    video_rows = (await db.execute(video_q)).all()
    videos: list[dict[str, Any]] = []
    for vrow in video_rows:
        videos.append({
            "video_id": vrow[0],
            "url": vrow[1],
            "strategies_found": vrow[2],
            "classification": vrow[3],
            "title": vrow[4],
            "researched_at": vrow[5],
            "channel": vrow[6],
        })

    return {
        "id": session.id,
        "status": session.status,
        "topic": topic_slug,
        "label": session.label,
        "title": topic_slug or session.label or "Untitled session",
        "topic_id": session.topic_id,
        "strategies_found": session.strategies_found,
        "drafts_created": session.drafts_created,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "duration_seconds": duration_seconds,
        "result_summary": session.result_summary,
        "error_detail": session.error_detail,
        "videos": videos,
    }
