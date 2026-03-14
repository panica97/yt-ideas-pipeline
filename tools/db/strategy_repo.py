"""Sync repository for strategies (pipeline side).

All functions receive a SQLAlchemy sync ``Session`` and operate
synchronously using psycopg2.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import Strategy


def get_strategy_by_name(session: Session, name: str) -> Strategy | None:
    """Return a strategy by name (case-insensitive), or ``None``."""
    stmt = select(Strategy).where(func.lower(Strategy.name) == name.lower())
    return session.execute(stmt).scalar_one_or_none()


def get_all_strategies(session: Session) -> list[Strategy]:
    """Return all strategies ordered by name."""
    stmt = select(Strategy).order_by(Strategy.name)
    return list(session.execute(stmt).scalars().all())


def search_strategies(session: Session, query: str) -> list[Strategy]:
    """Full-text search on strategy name + description."""
    ts_query = func.plainto_tsquery("english", query)
    ts_vector = func.to_tsvector(
        "english",
        Strategy.name + " " + func.coalesce(Strategy.description, ""),
    )
    stmt = select(Strategy).where(ts_vector.bool_op("@@")(ts_query)).order_by(Strategy.name)
    return list(session.execute(stmt).scalars().all())


def upsert_strategy(
    session: Session,
    *,
    name: str,
    description: str | None = None,
    source_channel_id: int | None = None,
    source_videos: list[str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    entry_rules: list[str] | None = None,
    exit_rules: list[str] | None = None,
    risk_management: list[str] | None = None,
    notes: list[str] | None = None,
) -> Strategy:
    """Insert a strategy or update it if a strategy with the same name exists.

    Deduplication is case-insensitive on ``name``.
    Returns the inserted/updated ``Strategy`` object.
    """
    existing = get_strategy_by_name(session, name)
    if existing is not None:
        # Update fields
        if description is not None:
            existing.description = description
        if source_channel_id is not None:
            existing.source_channel_id = source_channel_id
        if source_videos is not None:
            existing.source_videos = source_videos
        if parameters is not None:
            existing.parameters = parameters
        if entry_rules is not None:
            existing.entry_rules = entry_rules
        if exit_rules is not None:
            existing.exit_rules = exit_rules
        if risk_management is not None:
            existing.risk_management = risk_management
        if notes is not None:
            existing.notes = notes
        session.flush()
        return existing

    strategy = Strategy(
        name=name,
        description=description,
        source_channel_id=source_channel_id,
        source_videos=source_videos,
        parameters=parameters or [],
        entry_rules=entry_rules or [],
        exit_rules=exit_rules or [],
        risk_management=risk_management or [],
        notes=notes or [],
    )
    session.add(strategy)
    session.flush()
    return strategy


def insert_strategy(session: Session, data: dict[str, Any]) -> Strategy:
    """Insert a strategy from a dict (matching YAML field names).

    Uses ``upsert_strategy`` internally for deduplication.
    The ``source_channel`` field from YAML is ignored here because it's a
    name, not an ID -- the caller should resolve it to ``source_channel_id``
    if needed.
    """
    return upsert_strategy(
        session,
        name=data["name"],
        description=data.get("description"),
        source_videos=data.get("source_videos"),
        parameters=data.get("parameters"),
        entry_rules=data.get("entry_rules"),
        exit_rules=data.get("exit_rules"),
        risk_management=data.get("risk_management"),
        notes=data.get("notes"),
    )
