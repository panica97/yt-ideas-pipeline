"""Generate YAML/JSON exports from database on the fly."""

from __future__ import annotations

import io
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tools.db.models import Channel, Draft, Strategy, Topic

try:
    from ruamel.yaml import YAML

    def _dump_yaml(data: Any) -> str:
        yaml = YAML()
        yaml.default_flow_style = False
        stream = io.StringIO()
        yaml.dump(data, stream)
        return stream.getvalue()

except ImportError:
    import yaml as pyyaml  # type: ignore[no-redef]

    def _dump_yaml(data: Any) -> str:  # type: ignore[misc]
        return pyyaml.dump(data, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

async def export_channels(db: AsyncSession) -> dict[str, Any]:
    """Build the channels structure matching the original channels.yaml format."""
    result = await db.execute(
        select(Topic).options(selectinload(Topic.channels)).order_by(Topic.slug)
    )
    topics = result.scalars().unique().all()

    data: dict[str, Any] = {}
    for topic in topics:
        channels_list = []
        for ch in topic.channels:
            entry: dict[str, Any] = {"name": ch.name, "url": ch.url}
            if ch.last_fetched:
                entry["last_fetched"] = ch.last_fetched.isoformat()
            channels_list.append(entry)
        data[topic.slug] = {
            "description": topic.description,
            "channels": channels_list,
        }
    return data


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

async def export_strategies(db: AsyncSession) -> list[dict[str, Any]]:
    """Build strategies list for export."""
    result = await db.execute(
        select(Strategy, Channel.name.label("channel_name"))
        .outerjoin(Channel, Strategy.source_channel_id == Channel.id)
        .order_by(Strategy.name)
    )
    rows = result.all()

    strategies = []
    for row in rows:
        strat = row[0]
        ch_name = row[1]
        entry: dict[str, Any] = {
            "name": strat.name,
            "description": strat.description,
            "source_channel": ch_name,
            "source_videos": strat.source_videos or [],
            "parameters": strat.parameters or [],
            "entry_rules": strat.entry_rules or [],
            "exit_rules": strat.exit_rules or [],
            "risk_management": strat.risk_management or [],
            "notes": strat.notes or [],
        }
        strategies.append(entry)
    return strategies


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

async def export_draft(db: AsyncSession, strat_code: int) -> dict[str, Any]:
    """Export a single draft by strat_code."""
    result = await db.execute(
        select(Draft).where(Draft.strat_code == strat_code)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft con strat_code {strat_code} no encontrado",
        )
    return draft.data


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def serialize_yaml(data: Any) -> str:
    return _dump_yaml(data)


def serialize_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
