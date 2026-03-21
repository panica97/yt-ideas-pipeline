from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from .base import Base, TimestampMixin


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    channels: Mapped[List[Channel]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    last_fetched: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    topic: Mapped[Topic] = relationship(back_populates="channels")

    __table_args__ = (
        Index("uq_channel_topic_url", "topic_id", "url", unique=True),
    )


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    source_channel_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("channels.id")
    )
    source_videos: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    parameters: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="[]"
    )
    entry_rules: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="[]"
    )
    exit_rules: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="[]"
    )
    risk_management: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="[]"
    )
    notes: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="[]")

    __table_args__ = (
        Index(
            "idx_strategies_fts",
            text(
                "to_tsvector('english', name || ' ' || COALESCE(description, ''))"
            ),
            postgresql_using="gin",
        ),
    )


class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    strat_code: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    strat_name: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id")
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    todo_count: Mapped[int] = mapped_column(Integer, default=0)
    todo_fields: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), server_default="{}"
    )
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    tested: Mapped[bool] = mapped_column(Boolean, default=False)
    prod: Mapped[bool] = mapped_column(Boolean, default=False)


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    sec_type: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="USD")
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    min_tick: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ResearchHistory(Base):
    __tablename__ = "research_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("channels.id")
    )
    topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("topics.id")
    )
    researched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    strategies_found: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("uq_history_video_topic", "video_id", "topic_id", unique=True),
    )


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("topics.id")
    )
    step: Mapped[int] = mapped_column(Integer, default=0)
    step_name: Mapped[Optional[str]] = mapped_column(String(50))
    total_steps: Mapped[int] = mapped_column(Integer, default=6)
    channel: Mapped[Optional[str]] = mapped_column(String(100))
    videos_processing: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), server_default="{}"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_detail: Mapped[Optional[str]] = mapped_column(Text)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        Index(
            "idx_research_sessions_active",
            "status",
            postgresql_where=text("status = 'running'"),
        ),
    )
