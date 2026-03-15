"""Async query logic for research history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, ResearchHistory, ResearchSession, Topic


_VALID_SORT_FIELDS = {
    "researched_at": ResearchHistory.researched_at,
    "strategies_found": ResearchHistory.strategies_found,
    "video_id": ResearchHistory.video_id,
}


async def list_history(
    db: AsyncSession,
    *,
    topic: str | None = None,
    channel: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session_id: int | None = None,
    sort: str = "researched_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 50,
) -> tuple[int, list[dict[str, Any]]]:
    """Return (total, items) with dynamic filters and pagination."""
    query = (
        select(
            ResearchHistory,
            Channel.name.label("channel_name"),
            Topic.slug.label("topic_slug"),
        )
        .outerjoin(Channel, ResearchHistory.channel_id == Channel.id)
        .outerjoin(Topic, ResearchHistory.topic_id == Topic.id)
    )

    if topic:
        query = query.where(Topic.slug == topic)
    if channel:
        query = query.where(Channel.name == channel)
    if date_from:
        query = query.where(ResearchHistory.researched_at >= date_from)
    if date_to:
        query = query.where(ResearchHistory.researched_at <= date_to)

    if session_id is not None:
        # Filter by research session's time window and topic
        session_row = (
            await db.execute(
                select(ResearchSession).where(ResearchSession.id == session_id)
            )
        ).scalar_one_or_none()
        if session_row and session_row.started_at:
            query = query.where(
                ResearchHistory.researched_at >= session_row.started_at
            )
            if session_row.completed_at:
                query = query.where(
                    ResearchHistory.researched_at <= session_row.completed_at
                )
            if session_row.topic_id:
                query = query.where(
                    ResearchHistory.topic_id == session_row.topic_id
                )

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Sort
    sort_col = _VALID_SORT_FIELDS.get(sort, ResearchHistory.researched_at)
    direction = desc if order == "desc" else asc
    query = query.order_by(direction(sort_col))

    # Pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    rows = (await db.execute(query)).all()
    items = []
    for row in rows:
        hist = row[0]
        ch_name = row[1]
        topic_slug = row[2]
        items.append({
            "video_id": hist.video_id,
            "url": hist.url,
            "channel": ch_name,
            "topic": topic_slug,
            "researched_at": hist.researched_at,
            "strategies_found": hist.strategies_found,
            "title": hist.title,
        })

    return total, items


async def get_history_stats(db: AsyncSession) -> dict[str, Any]:
    """Aggregate history statistics."""
    # Total videos
    total_videos_r = await db.execute(
        select(func.count()).select_from(ResearchHistory)
    )
    total_videos = total_videos_r.scalar_one()

    # Total strategies found
    total_strats_r = await db.execute(
        select(func.coalesce(func.sum(ResearchHistory.strategies_found), 0))
    )
    total_strategies_found = total_strats_r.scalar_one()

    # By topic
    by_topic_rows = await db.execute(
        select(Topic.slug, func.count())
        .join(ResearchHistory, ResearchHistory.topic_id == Topic.id)
        .group_by(Topic.slug)
    )
    by_topic = {row[0]: row[1] for row in by_topic_rows.all()}

    # By channel
    by_channel_rows = await db.execute(
        select(Channel.name, func.count())
        .join(ResearchHistory, ResearchHistory.channel_id == Channel.id)
        .group_by(Channel.name)
    )
    by_channel = {row[0]: row[1] for row in by_channel_rows.all()}

    # Last research
    last_r = await db.execute(
        select(
            ResearchHistory,
            Topic.slug.label("topic_slug"),
        )
        .outerjoin(Topic, ResearchHistory.topic_id == Topic.id)
        .order_by(desc(ResearchHistory.researched_at))
        .limit(1)
    )
    last_row = last_r.first()
    last_research = None
    if last_row:
        hist = last_row[0]
        last_research = {
            "topic": last_row[1],
            "date": hist.researched_at,
            "videos": 1,
            "strategies": hist.strategies_found,
        }

    return {
        "total_videos": total_videos,
        "total_strategies_found": total_strategies_found,
        "by_topic": by_topic,
        "by_channel": by_channel,
        "last_research": last_research,
    }
