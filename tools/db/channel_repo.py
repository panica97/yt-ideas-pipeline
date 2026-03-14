"""Sync repository for topics and channels (pipeline side).

All functions receive a SQLAlchemy sync ``Session`` and operate
synchronously using psycopg2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Channel, Topic


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

def get_all_topics(session: Session) -> list[Topic]:
    """Return all topics with their channels eagerly loaded."""
    stmt = select(Topic).options(joinedload(Topic.channels)).order_by(Topic.slug)
    return list(session.execute(stmt).unique().scalars().all())


def get_topic_by_slug(session: Session, slug: str) -> Topic | None:
    """Return a single topic by slug, or ``None``."""
    stmt = select(Topic).options(joinedload(Topic.channels)).where(Topic.slug == slug)
    return session.execute(stmt).unique().scalar_one_or_none()


def create_topic(session: Session, slug: str, description: str | None = None) -> Topic:
    """Insert a new topic and return it."""
    topic = Topic(slug=slug, description=description)
    session.add(topic)
    session.flush()
    return topic


def update_topic(session: Session, slug: str, description: str) -> Topic | None:
    """Update a topic's description. Returns the topic or ``None`` if not found."""
    topic = get_topic_by_slug(session, slug)
    if topic is None:
        return None
    topic.description = description
    session.flush()
    return topic


def delete_topic(session: Session, slug: str) -> bool:
    """Delete a topic if it has no channels. Returns ``True`` on success.

    Raises ``ValueError`` if the topic has channels.
    Returns ``False`` if the topic does not exist.
    """
    topic = get_topic_by_slug(session, slug)
    if topic is None:
        return False
    if topic.channels:
        raise ValueError(f"No se puede eliminar el topic '{slug}' porque tiene canales asociados")
    session.delete(topic)
    session.flush()
    return True


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def get_channels_by_topic(session: Session, slug: str) -> list[Channel]:
    """Return all channels for a given topic slug."""
    topic = get_topic_by_slug(session, slug)
    if topic is None:
        return []
    return list(topic.channels)


def create_channel(
    session: Session,
    topic_slug: str,
    name: str,
    url: str,
) -> Channel:
    """Add a channel to a topic. Raises ``ValueError`` if topic not found."""
    topic = get_topic_by_slug(session, topic_slug)
    if topic is None:
        raise ValueError(f"Topic '{topic_slug}' no encontrado")
    channel = Channel(topic_id=topic.id, name=name, url=url.rstrip("/"))
    session.add(channel)
    session.flush()
    return channel


def delete_channel(session: Session, topic_slug: str, channel_name: str) -> bool:
    """Delete a channel by topic slug and channel name.

    Returns ``True`` on success, ``False`` if not found.
    """
    topic = get_topic_by_slug(session, topic_slug)
    if topic is None:
        return False
    stmt = (
        select(Channel)
        .where(Channel.topic_id == topic.id, Channel.name == channel_name)
    )
    channel = session.execute(stmt).scalar_one_or_none()
    if channel is None:
        return False
    session.delete(channel)
    session.flush()
    return True


def update_channel_last_fetched(
    session: Session,
    channel_id: int,
    timestamp: datetime | None = None,
) -> None:
    """Update the ``last_fetched`` timestamp on a channel."""
    if timestamp is None:
        timestamp = datetime.now()
    stmt = select(Channel).where(Channel.id == channel_id)
    channel = session.execute(stmt).scalar_one_or_none()
    if channel is not None:
        channel.last_fetched = timestamp
        session.flush()


# ---------------------------------------------------------------------------
# Convenience: dict matching YAML structure
# ---------------------------------------------------------------------------

def get_topics_as_dict(session: Session) -> dict[str, Any]:
    """Return topics + channels in the same dict shape as ``channels.yaml``.

    Returns::

        {"topics": {"slug": {"description": "...", "channels": [{...}]}}}
    """
    topics = get_all_topics(session)
    result: dict[str, Any] = {}
    for t in topics:
        result[t.slug] = {
            "description": t.description or "",
            "channels": [
                {
                    "name": ch.name,
                    "url": ch.url,
                    "last_fetched": (
                        ch.last_fetched.strftime("%Y-%m-%d") if ch.last_fetched else None
                    ),
                }
                for ch in t.channels
            ],
        }
    return {"topics": result}
