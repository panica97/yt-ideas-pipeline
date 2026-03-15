"""Async query logic for research sessions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, ResearchHistory, ResearchSession, Topic


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

        # Fetch related history items (videos) for this session's topic
        # within the session's time window
        videos: list[dict[str, Any]] = []
        if session.topic_id and session.started_at:
            video_q = (
                select(
                    ResearchHistory.video_id,
                    ResearchHistory.url,
                    ResearchHistory.strategies_found,
                    Channel.name.label("channel_name"),
                )
                .outerjoin(Channel, ResearchHistory.channel_id == Channel.id)
                .where(ResearchHistory.topic_id == session.topic_id)
                .where(ResearchHistory.researched_at >= session.started_at)
            )
            if session.completed_at:
                video_q = video_q.where(
                    ResearchHistory.researched_at <= session.completed_at
                )
            video_rows = (await db.execute(video_q)).all()
            for vrow in video_rows:
                videos.append({
                    "video_id": vrow[0],
                    "url": vrow[1],
                    "strategies_found": vrow[2],
                    "channel": vrow[3],
                })

        results.append({
            "id": session.id,
            "status": session.status,
            "topic": topic_slug,
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

    # Fetch related history items (videos) for this session's topic
    # within the session's time window
    videos: list[dict[str, Any]] = []
    if session.topic_id and session.started_at:
        video_q = (
            select(
                ResearchHistory.video_id,
                ResearchHistory.url,
                ResearchHistory.strategies_found,
                ResearchHistory.researched_at,
                Channel.name.label("channel_name"),
            )
            .outerjoin(Channel, ResearchHistory.channel_id == Channel.id)
            .where(ResearchHistory.topic_id == session.topic_id)
            .where(ResearchHistory.researched_at >= session.started_at)
        )
        if session.completed_at:
            video_q = video_q.where(
                ResearchHistory.researched_at <= session.completed_at
            )
        video_rows = (await db.execute(video_q)).all()
        for vrow in video_rows:
            videos.append({
                "video_id": vrow[0],
                "url": vrow[1],
                "strategies_found": vrow[2],
                "researched_at": vrow[3],
                "channel": vrow[4],
            })

    return {
        "id": session.id,
        "status": session.status,
        "topic": topic_slug,
        "topic_id": session.topic_id,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "duration_seconds": duration_seconds,
        "result_summary": session.result_summary,
        "error_detail": session.error_detail,
        "videos": videos,
    }
