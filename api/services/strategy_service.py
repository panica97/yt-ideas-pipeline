"""Async query logic for strategies and drafts."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, Draft, Strategy


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

async def list_strategies(
    db: AsyncSession,
    channel: str | None = None,
    search: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Return (total, strategies) with optional channel/FTS filters."""
    query = select(Strategy, Channel.name.label("source_channel_name")).outerjoin(
        Channel, Strategy.source_channel_id == Channel.id
    )

    if channel:
        query = query.where(Channel.name == channel)

    if search:
        query = query.where(
            text(
                "to_tsvector('english', strategies.name || ' ' || COALESCE(strategies.description, '')) "
                "@@ plainto_tsquery('english', :search)"
            ).bindparams(search=search)
        )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Results
    query = query.order_by(Strategy.name)
    rows = (await db.execute(query)).all()

    strategies = []
    for row in rows:
        strat = row[0]  # Strategy model
        ch_name = row[1]  # source_channel_name
        strategies.append({
            "id": strat.id,
            "name": strat.name,
            "description": strat.description,
            "source_channel": ch_name,
            "source_videos": strat.source_videos,
            "parameters": strat.parameters,
            "entry_rules": strat.entry_rules,
            "exit_rules": strat.exit_rules,
            "risk_management": strat.risk_management,
            "notes": strat.notes,
            "created_at": strat.created_at,
            "updated_at": strat.updated_at,
        })

    return total, strategies


async def get_strategy_by_name(
    db: AsyncSession, name: str
) -> dict[str, Any]:
    query = select(Strategy, Channel.name.label("source_channel_name")).outerjoin(
        Channel, Strategy.source_channel_id == Channel.id
    ).where(Strategy.name == name)

    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estrategia '{name}' no encontrada",
        )

    strat = row[0]
    ch_name = row[1]
    return {
        "id": strat.id,
        "name": strat.name,
        "description": strat.description,
        "source_channel": ch_name,
        "source_videos": strat.source_videos,
        "parameters": strat.parameters,
        "entry_rules": strat.entry_rules,
        "exit_rules": strat.exit_rules,
        "risk_management": strat.risk_management,
        "notes": strat.notes,
        "created_at": strat.created_at,
        "updated_at": strat.updated_at,
    }


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def _extract_todo_fields(
    data: Any, prefix: str = ""
) -> list[dict[str, str | None]]:
    """Recursively find all _TODO values in a nested dict/list."""
    results: list[dict[str, str | None]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str) and value.strip() == "_TODO":
                results.append({"path": path, "context": None})
            else:
                results.extend(_extract_todo_fields(value, path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            path = f"{prefix}[{i}]"
            results.extend(_extract_todo_fields(item, path))
    return results


async def list_drafts(
    db: AsyncSession,
    has_todos: bool | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = select(Draft)

    if has_todos is True:
        query = query.where(Draft.todo_count > 0)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = query.order_by(Draft.strat_code)
    drafts = (await db.execute(query)).scalars().all()

    items = []
    for d in drafts:
        symbol = None
        if isinstance(d.data, dict):
            # Try to extract symbol from draft data
            instrument = d.data.get("instrument", {})
            if isinstance(instrument, dict):
                symbol = instrument.get("symbol")
        items.append({
            "strat_code": d.strat_code,
            "strat_name": d.strat_name,
            "symbol": symbol,
            "active": d.active,
            "tested": d.tested,
            "prod": d.prod,
            "todo_count": d.todo_count,
            "todo_fields": d.todo_fields,
        })

    return total, items


async def get_draft_by_code(
    db: AsyncSession, strat_code: int
) -> dict[str, Any]:
    result = await db.execute(
        select(Draft).where(Draft.strat_code == strat_code)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft con strat_code {strat_code} no encontrado",
        )

    todo_fields_detail = _extract_todo_fields(draft.data) if draft.data else []

    return {
        "strat_code": draft.strat_code,
        "strat_name": draft.strat_name,
        "active": draft.active,
        "tested": draft.tested,
        "prod": draft.prod,
        "todo_count": draft.todo_count,
        "todo_fields": draft.todo_fields,
        "data": draft.data,
        "_todo_summary": {
            "count": len(todo_fields_detail),
            "fields": todo_fields_detail,
        },
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }
