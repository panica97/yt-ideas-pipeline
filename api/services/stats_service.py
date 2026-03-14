"""Async count queries for dashboard statistics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import (
    Channel,
    Draft,
    ResearchHistory,
    Strategy,
    Topic,
)


async def get_stats(db: AsyncSession) -> dict[str, Any]:
    """Return global dashboard statistics."""
    total_topics = (
        await db.execute(select(func.count()).select_from(Topic))
    ).scalar_one()

    total_channels = (
        await db.execute(select(func.count()).select_from(Channel))
    ).scalar_one()

    total_videos = (
        await db.execute(select(func.count()).select_from(ResearchHistory))
    ).scalar_one()

    total_strategies = (
        await db.execute(select(func.count()).select_from(Strategy))
    ).scalar_one()

    total_drafts = (
        await db.execute(select(func.count()).select_from(Draft))
    ).scalar_one()

    drafts_with_todos = (
        await db.execute(
            select(func.count()).select_from(Draft).where(Draft.todo_count > 0)
        )
    ).scalar_one()

    # Last research
    last_r = await db.execute(
        select(
            ResearchHistory.researched_at,
            ResearchHistory.strategies_found,
            Topic.slug.label("topic_slug"),
        )
        .outerjoin(Topic, ResearchHistory.topic_id == Topic.id)
        .order_by(desc(ResearchHistory.researched_at))
        .limit(1)
    )
    last_row = last_r.first()
    last_research = None
    if last_row:
        last_research = {
            "topic": last_row[2],
            "date": last_row[0],
            "strategies_found": last_row[1],
        }

    return {
        "total_topics": total_topics,
        "total_channels": total_channels,
        "total_videos_researched": total_videos,
        "total_strategies": total_strategies,
        "total_drafts": total_drafts,
        "drafts_with_todos": drafts_with_todos,
        "last_research": last_research,
    }
