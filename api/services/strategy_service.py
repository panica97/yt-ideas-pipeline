"""Async query logic for strategies and drafts."""

from __future__ import annotations

import copy
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tools.db.models import Channel, Draft, ResearchSession, Strategy


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

async def list_strategies(
    db: AsyncSession,
    channel: str | None = None,
    search: str | None = None,
    session_id: int | None = None,
    has_draft: bool | None = None,
    has_todos: bool | None = None,
    status: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Return (total, strategies) with optional channel/FTS filters."""
    query = select(Strategy, Channel.name.label("source_channel_name")).outerjoin(
        Channel, Strategy.source_channel_id == Channel.id
    )

    if has_draft is True:
        query = query.where(
            Strategy.id.in_(select(Draft.strategy_id).where(Draft.strategy_id.isnot(None)))
        )
    elif has_draft is False:
        query = query.where(
            ~Strategy.id.in_(select(Draft.strategy_id).where(Draft.strategy_id.isnot(None)))
        )

    if has_todos is True:
        query = query.where(
            Strategy.id.in_(
                select(Draft.strategy_id)
                .where(Draft.strategy_id.isnot(None))
                .where(Draft.todo_count > 0)
            )
        )
    elif has_todos is False:
        query = query.where(
            Strategy.id.in_(
                select(Draft.strategy_id)
                .where(Draft.strategy_id.isnot(None))
                .where(Draft.todo_count == 0)
            )
        )

    if status:
        query = query.where(Strategy.status == status)

    if channel:
        query = query.where(Channel.name == channel)

    if search:
        query = query.where(
            text(
                "to_tsvector('english', strategies.name || ' ' || COALESCE(strategies.description, '')) "
                "@@ plainto_tsquery('english', :search)"
            ).bindparams(search=search)
        )

    if session_id is not None:
        # Filter strategies created within the session's time window
        session_row = (
            await db.execute(
                select(ResearchSession).where(ResearchSession.id == session_id)
            )
        ).scalar_one_or_none()
        if session_row and session_row.started_at:
            query = query.where(Strategy.created_at >= session_row.started_at)
            if session_row.completed_at:
                query = query.where(Strategy.created_at <= session_row.completed_at)

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
            "status": strat.status,
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
        "status": strat.status,
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


VALID_STATUSES = {"pending", "idea", "validated"}


async def set_strategy_status(
    db: AsyncSession, name: str, new_status: str
) -> dict[str, Any]:
    """Set strategy status to a valid value ('pending', 'idea', 'validated')."""
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Estado invalido '{new_status}'. Valores validos: {', '.join(sorted(VALID_STATUSES))}",
        )
    result = await db.execute(
        select(Strategy).where(Strategy.name == name)
    )
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estrategia '{name}' no encontrada",
        )
    strat.status = new_status
    await db.commit()
    await db.refresh(strat)
    return await get_strategy_by_name(db, name)


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
    status: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = select(Draft)

    if status:
        query = query.join(Strategy, Draft.strategy_id == Strategy.id).where(
            Strategy.status == status
        )

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


async def get_drafts_by_strategy(
    db: AsyncSession, strategy_name: str
) -> list[dict[str, Any]]:
    """Return all drafts linked to a strategy by name."""
    result = await db.execute(
        select(Strategy).where(Strategy.name == strategy_name)
    )
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estrategia '{strategy_name}' no encontrada",
        )

    drafts_result = await db.execute(
        select(Draft).where(Draft.strategy_id == strat.id).order_by(Draft.strat_code)
    )
    drafts = drafts_result.scalars().all()

    items = []
    for d in drafts:
        symbol = None
        if isinstance(d.data, dict):
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
            "data": d.data,
        })

    return items


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


# ---------------------------------------------------------------------------
# Fill TODO
# ---------------------------------------------------------------------------

def _parse_path_segments(path: str) -> list[str | int]:
    """Parse a dot/bracket path into a list of keys and indices.

    Examples:
        "multiplier"                          -> ["multiplier"]
        "control_params.start_date"           -> ["control_params", "start_date"]
        "ind_list.4 hours[1].params.timePeriod_1"
            -> ["ind_list", "4 hours", 1, "params", "timePeriod_1"]
    """
    segments: list[str | int] = []
    # Split by '.' but preserve keys that contain spaces (e.g. "4 hours")
    # Strategy: split on '[' first, then handle dots inside each part.
    # We use a regex to tokenize: either a bracket index or a dot-separated key.
    tokens = re.split(r"\[(\d+)\]", path)
    for i, token in enumerate(tokens):
        if i % 2 == 1:
            # This is a bracket index capture
            segments.append(int(token))
        else:
            # This is a dot-separated string portion
            if token:
                # Strip leading/trailing dots
                token = token.strip(".")
                if token:
                    segments.extend(token.split("."))
    return segments


def _navigate_to_parent(
    data: Any, segments: list[str | int]
) -> tuple[Any, str | int]:
    """Walk *data* following *segments* and return (parent, final_key).

    Raises ValueError with a descriptive message on navigation failure.
    """
    current = data
    for seg in segments[:-1]:
        if isinstance(seg, int):
            if not isinstance(current, list) or seg >= len(current):
                raise ValueError(f"Índice [{seg}] fuera de rango o tipo incorrecto")
            current = current[seg]
        else:
            if not isinstance(current, dict) or seg not in current:
                raise ValueError(f"Clave '{seg}' no encontrada en el path")
            current = current[seg]
    return current, segments[-1]


async def fill_todo(
    db: AsyncSession, strat_code: int, path: str, value: Any
) -> dict[str, Any]:
    """Replace a ``_TODO`` sentinel inside a draft's JSONB *data* field."""
    result = await db.execute(
        select(Draft).where(Draft.strat_code == strat_code)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft con strat_code {strat_code} no encontrado",
        )

    segments = _parse_path_segments(path)
    if not segments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path vacío",
        )

    data = copy.deepcopy(draft.data) if draft.data else {}

    try:
        parent, final_key = _navigate_to_parent(data, segments)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Path inválido: {exc}",
        )

    # Resolve final key
    if isinstance(final_key, int):
        if not isinstance(parent, list) or final_key >= len(parent):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Índice [{final_key}] fuera de rango",
            )
        current_value = parent[final_key]
    else:
        if not isinstance(parent, dict) or final_key not in parent:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Path '{path}' no existe en data",
            )
        current_value = parent[final_key]

    if not (isinstance(current_value, str) and current_value.strip() == "_TODO"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El valor en '{path}' no es '_TODO' (valor actual: {current_value!r})",
        )

    # Apply the new value
    if isinstance(final_key, int):
        parent[final_key] = value
    else:
        parent[final_key] = value

    # Recalculate todo_fields and todo_count
    todo_details = _extract_todo_fields(data)
    todo_paths = [t["path"] for t in todo_details]

    draft.data = data
    draft.todo_fields = todo_paths
    draft.todo_count = len(todo_paths)

    await db.commit()
    await db.refresh(draft)

    return await get_draft_by_code(db, strat_code)
