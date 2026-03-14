"""Async CRUD logic for topics."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, Topic


async def get_topic_by_slug(db: AsyncSession, slug: str) -> Topic | None:
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    return result.scalar_one_or_none()


async def create_topic(db: AsyncSession, slug: str, description: str | None) -> Topic:
    existing = await get_topic_by_slug(db, slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Topic '{slug}' ya existe",
        )
    topic = Topic(slug=slug, description=description)
    db.add(topic)
    await db.flush()
    await db.refresh(topic)
    return topic


async def update_topic(db: AsyncSession, slug: str, description: str) -> Topic:
    topic = await get_topic_by_slug(db, slug)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' no encontrado",
        )
    topic.description = description
    await db.flush()
    await db.refresh(topic)
    return topic


async def delete_topic(db: AsyncSession, slug: str) -> None:
    topic = await get_topic_by_slug(db, slug)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' no encontrado",
        )
    # Check if topic has channels
    channel_count_result = await db.execute(
        select(func.count()).select_from(Channel).where(Channel.topic_id == topic.id)
    )
    channel_count = channel_count_result.scalar_one()
    if channel_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar un topic con canales asociados",
        )
    await db.delete(topic)
    await db.flush()
