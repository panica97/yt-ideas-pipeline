"""Sync repository for drafts (pipeline side).

All functions receive a SQLAlchemy sync ``Session`` and operate
synchronously using psycopg2.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Draft


# ---------------------------------------------------------------------------
# TODO scanning helpers
# ---------------------------------------------------------------------------

def _extract_todo_fields(data: Any, prefix: str = "") -> list[str]:
    """Recursively scan a JSON-like structure for ``_TODO`` values.

    Returns a list of dot-notation paths where the value equals ``"_TODO"``.
    """
    paths: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            current = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str) and "_TODO" in value:
                paths.append(current)
            else:
                paths.extend(_extract_todo_fields(value, current))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current = f"{prefix}[{idx}]"
            if isinstance(item, str) and "_TODO" in item:
                paths.append(current)
            else:
                paths.extend(_extract_todo_fields(item, current))
    return paths


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_draft_by_code(session: Session, strat_code: int) -> Draft | None:
    """Return a draft by its ``strat_code``, or ``None``."""
    stmt = select(Draft).where(Draft.strat_code == strat_code)
    return session.execute(stmt).scalar_one_or_none()


def get_all_drafts(
    session: Session,
    has_todos: bool | None = None,
) -> list[Draft]:
    """Return all drafts, optionally filtered by TODO status.

    Args:
        has_todos: If ``True``, only return drafts with ``todo_count > 0``.
                   If ``False``, only return drafts with ``todo_count == 0``.
                   If ``None``, return all drafts.
    """
    stmt = select(Draft).order_by(Draft.strat_code)
    if has_todos is True:
        stmt = stmt.where(Draft.todo_count > 0)
    elif has_todos is False:
        stmt = stmt.where(Draft.todo_count == 0)
    return list(session.execute(stmt).scalars().all())


def upsert_draft(
    session: Session,
    *,
    strat_code: int,
    strat_name: str,
    data: dict[str, Any],
    strategy_id: int | None = None,
    active: bool = False,
    tested: bool = False,
    prod: bool = False,
) -> Draft:
    """Insert or update a draft.

    Automatically computes ``todo_count`` and ``todo_fields`` by scanning
    the ``data`` JSONB for ``_TODO`` values.

    Deduplication is by ``strat_code`` (unique constraint).
    """
    todo_fields = _extract_todo_fields(data)
    todo_count = len(todo_fields)

    existing = get_draft_by_code(session, strat_code)
    if existing is not None:
        existing.strat_name = strat_name
        existing.data = data
        existing.strategy_id = strategy_id
        existing.todo_count = todo_count
        existing.todo_fields = todo_fields
        existing.active = active
        existing.tested = tested
        existing.prod = prod
        session.flush()
        return existing

    draft = Draft(
        strat_code=strat_code,
        strat_name=strat_name,
        strategy_id=strategy_id,
        data=data,
        todo_count=todo_count,
        todo_fields=todo_fields,
        active=active,
        tested=tested,
        prod=prod,
    )
    session.add(draft)
    session.flush()
    return draft
