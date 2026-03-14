"""Sync repository for research history queries (pipeline side).

Provides paginated listing and statistics for research history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Channel, ResearchHistory, Topic


def get_history(
    session: Session,
    *,
    topic: str | None = None,
    channel: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    sort: str = "date",
    order: str = "desc",
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Return paginated research history with optional filters.

    Returns::

        {
            "total": int,
            "page": int,
            "limit": int,
            "items": [ResearchHistory, ...],
        }
    """
    stmt = select(ResearchHistory)

    # Filters
    if topic is not None:
        topic_id_sub = select(Topic.id).where(Topic.slug == topic).scalar_subquery()
        stmt = stmt.where(ResearchHistory.topic_id == topic_id_sub)

    if channel is not None:
        channel_id_sub = (
            select(Channel.id).where(Channel.name == channel).scalar_subquery()
        )
        stmt = stmt.where(ResearchHistory.channel_id == channel_id_sub)

    if from_date is not None:
        stmt = stmt.where(ResearchHistory.researched_at >= from_date)

    if to_date is not None:
        stmt = stmt.where(ResearchHistory.researched_at <= to_date)

    # Count total before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.execute(count_stmt).scalar() or 0

    # Sorting
    sort_column_map = {
        "date": ResearchHistory.researched_at,
        "strategies_found": ResearchHistory.strategies_found,
        "video_id": ResearchHistory.video_id,
    }
    sort_col = sort_column_map.get(sort, ResearchHistory.researched_at)
    if order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    items = list(session.execute(stmt).scalars().all())

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items,
    }


def get_history_stats(session: Session) -> dict[str, Any]:
    """Return aggregate statistics for research history.

    Returns::

        {
            "total_videos": int,
            "total_strategies_found": int,
            "by_topic": {slug: {"videos": int, "strategies": int}},
            "by_channel": {name: {"videos": int, "strategies": int}},
            "last_research": {"topic": str, "date": str, "videos": int, "strategies": int} | None,
        }
    """
    # Totals
    total_videos = session.execute(
        select(func.count(ResearchHistory.id))
    ).scalar() or 0

    total_strategies = session.execute(
        select(func.coalesce(func.sum(ResearchHistory.strategies_found), 0))
    ).scalar() or 0

    # By topic
    by_topic_rows = session.execute(
        select(
            Topic.slug,
            func.count(ResearchHistory.id).label("videos"),
            func.coalesce(func.sum(ResearchHistory.strategies_found), 0).label("strategies"),
        )
        .join(Topic, ResearchHistory.topic_id == Topic.id)
        .group_by(Topic.slug)
    ).all()
    by_topic = {
        row.slug: {"videos": row.videos, "strategies": int(row.strategies)}
        for row in by_topic_rows
    }

    # By channel
    by_channel_rows = session.execute(
        select(
            Channel.name,
            func.count(ResearchHistory.id).label("videos"),
            func.coalesce(func.sum(ResearchHistory.strategies_found), 0).label("strategies"),
        )
        .join(Channel, ResearchHistory.channel_id == Channel.id)
        .group_by(Channel.name)
    ).all()
    by_channel = {
        row.name: {"videos": row.videos, "strategies": int(row.strategies)}
        for row in by_channel_rows
    }

    # Last research
    last_row = session.execute(
        select(
            Topic.slug.label("topic"),
            ResearchHistory.researched_at,
            ResearchHistory.strategies_found,
        )
        .join(Topic, ResearchHistory.topic_id == Topic.id)
        .order_by(ResearchHistory.researched_at.desc())
        .limit(1)
    ).first()

    last_research = None
    if last_row is not None:
        last_research = {
            "topic": last_row.topic,
            "date": last_row.researched_at.isoformat() if last_row.researched_at else None,
            "strategies": last_row.strategies_found,
        }

    return {
        "total_videos": total_videos,
        "total_strategies_found": int(total_strategies),
        "by_topic": by_topic,
        "by_channel": by_channel,
        "last_research": last_research,
    }
