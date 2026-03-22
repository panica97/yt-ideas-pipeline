"""Async CRUD logic for channels."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tools.db.models import Channel, Topic


async def list_all_topics_with_channels(db: AsyncSession) -> list[Topic]:
    result = await db.execute(
        select(Topic).options(selectinload(Topic.channels)).order_by(Topic.slug)
    )
    return list(result.scalars().unique().all())


async def get_topic_with_channels(db: AsyncSession, topic_slug: str) -> Topic:
    result = await db.execute(
        select(Topic)
        .options(selectinload(Topic.channels))
        .where(Topic.slug == topic_slug)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic_slug}' not found",
        )
    return topic


async def add_channel(
    db: AsyncSession, topic_slug: str, name: str, url: str
) -> Channel:
    # Get topic
    result = await db.execute(select(Topic).where(Topic.slug == topic_slug))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic_slug}' not found",
        )

    # Check duplicate URL in same topic
    existing = await db.execute(
        select(Channel).where(
            Channel.topic_id == topic.id, Channel.url == url
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel with URL '{url}' already exists in topic '{topic_slug}'",
        )

    channel = Channel(topic_id=topic.id, name=name, url=url)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


async def delete_channel(
    db: AsyncSession, topic_slug: str, channel_name: str
) -> None:
    # Get topic
    result = await db.execute(select(Topic).where(Topic.slug == topic_slug))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic_slug}' not found",
        )

    # Get channel
    ch_result = await db.execute(
        select(Channel).where(
            Channel.topic_id == topic.id, Channel.name == channel_name
        )
    )
    channel = ch_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_name}' not found in topic '{topic_slug}'",
        )

    # A topic must have at least one channel to be functional in the
    # research pipeline, so deleting the last one is not allowed.
    count_result = await db.execute(
        select(func.count())
        .select_from(Channel)
        .where(Channel.topic_id == topic.id)
    )
    channel_count = count_result.scalar_one()
    if channel_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the only channel of the topic",
        )

    await db.delete(channel)
    await db.commit()
