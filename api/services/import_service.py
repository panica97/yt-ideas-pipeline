"""One-time import script: migrate YAML/JSON data to PostgreSQL.

Usage::

    python -m api.services.import_service

Or from Docker::

    docker compose run api python -m api.services.import_service

Reads from:
    - data/channels/channels.yaml  -> topics + channels
    - data/strategies/strategies.yaml -> strategies
    - data/strategies/drafts/*.json -> drafts
    - data/research/history.yaml -> research_history

Handles deduplication: safe to re-run without creating duplicates.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

# Ensure project root is on the path so tools.db can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.db.session import sync_session_ctx  # noqa: E402
from tools.db.models import (  # noqa: E402
    Channel,
    Draft,
    ResearchHistory,
    Strategy,
    Topic,
)
from sqlalchemy import select, func  # noqa: E402


DATA_DIR = PROJECT_ROOT / "data"


def import_channels(session, data_dir: Path) -> dict[str, int]:
    """Import topics and channels from channels.yaml.

    Returns counts of imported items.
    """
    channels_file = data_dir / "channels" / "channels.yaml"
    if not channels_file.exists():
        print(f"  [skip] {channels_file} not found")
        return {"topics": 0, "channels": 0}

    with open(channels_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "topics" not in data:
        print(f"  [skip] {channels_file} has no topics")
        return {"topics": 0, "channels": 0}

    topics_imported = 0
    channels_imported = 0

    for slug, info in data["topics"].items():
        # Check if topic exists
        existing_topic = session.execute(
            select(Topic).where(Topic.slug == slug)
        ).scalar_one_or_none()

        if existing_topic is None:
            topic = Topic(slug=slug, description=info.get("description", ""))
            session.add(topic)
            session.flush()
            topics_imported += 1
            print(f"  [+] Topic: {slug}")
        else:
            topic = existing_topic
            print(f"  [=] Topic: {slug} (already exists)")

        # Import channels
        for ch_data in info.get("channels", []):
            url = ch_data["url"].rstrip("/")
            existing_ch = session.execute(
                select(Channel).where(
                    Channel.topic_id == topic.id,
                    Channel.url == url,
                )
            ).scalar_one_or_none()

            if existing_ch is None:
                channel = Channel(
                    topic_id=topic.id,
                    name=ch_data["name"],
                    url=url,
                )
                # Parse last_fetched if present
                lf = ch_data.get("last_fetched")
                if lf and lf != "null":
                    from datetime import datetime
                    try:
                        channel.last_fetched = datetime.strptime(str(lf), "%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                session.add(channel)
                session.flush()
                channels_imported += 1
                print(f"    [+] Channel: {ch_data['name']}")
            else:
                print(f"    [=] Channel: {ch_data['name']} (already exists)")

    return {"topics": topics_imported, "channels": channels_imported}


def import_strategies(session, data_dir: Path) -> dict[str, int]:
    """Import strategies from strategies.yaml.

    Returns count of imported strategies.
    """
    strategies_file = data_dir / "strategies" / "strategies.yaml"
    if not strategies_file.exists():
        print(f"  [skip] {strategies_file} not found")
        return {"strategies": 0}

    with open(strategies_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "strategies" not in data:
        print(f"  [skip] {strategies_file} has no strategies")
        return {"strategies": 0}

    imported = 0

    for strat_data in data["strategies"]:
        name = strat_data.get("name", "")
        if not name:
            print(f"  [!] Skipping strategy with no name")
            continue

        existing = session.execute(
            select(Strategy).where(func.lower(Strategy.name) == name.lower())
        ).scalar_one_or_none()

        if existing is not None:
            print(f"  [=] Strategy: {name} (already exists)")
            continue

        # Resolve source_channel to source_channel_id if possible
        source_channel_id = None
        source_channel_name = strat_data.get("source_channel")
        if source_channel_name:
            ch = session.execute(
                select(Channel).where(Channel.name == source_channel_name)
            ).scalar_one_or_none()
            if ch:
                source_channel_id = ch.id

        strategy = Strategy(
            name=name,
            description=strat_data.get("description"),
            source_channel_id=source_channel_id,
            source_videos=strat_data.get("source_videos"),
            parameters=strat_data.get("parameters", []),
            entry_rules=strat_data.get("entry_rules", []),
            exit_rules=strat_data.get("exit_rules", []),
            risk_management=strat_data.get("risk_management", []),
            notes=strat_data.get("notes", []),
        )
        session.add(strategy)
        session.flush()
        imported += 1
        print(f"  [+] Strategy: {name}")

    return {"strategies": imported}


def _extract_todo_fields(data, prefix=""):
    """Recursively find _TODO values in a dict/list."""
    paths = []
    if isinstance(data, dict):
        for key, value in data.items():
            current = f"{prefix}.{key}" if prefix else key
            if value == "_TODO":
                paths.append(current)
            else:
                paths.extend(_extract_todo_fields(value, current))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current = f"{prefix}[{idx}]"
            if item == "_TODO":
                paths.append(current)
            else:
                paths.extend(_extract_todo_fields(item, current))
    return paths


def import_drafts(session, data_dir: Path) -> dict[str, int]:
    """Import drafts from data/strategies/drafts/*.json.

    Returns count of imported drafts.
    """
    drafts_dir = data_dir / "strategies" / "drafts"
    if not drafts_dir.exists():
        print(f"  [skip] {drafts_dir} not found")
        return {"drafts": 0}

    imported = 0
    json_files = sorted(drafts_dir.glob("*.json"))
    if not json_files:
        print(f"  [skip] No JSON files in {drafts_dir}")
        return {"drafts": 0}

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                draft_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [!] Error reading {json_file.name}: {e}")
            continue

        strat_code = draft_data.get("strat_code")
        if strat_code is None:
            print(f"  [!] Skipping {json_file.name}: no strat_code")
            continue

        existing = session.execute(
            select(Draft).where(Draft.strat_code == strat_code)
        ).scalar_one_or_none()

        if existing is not None:
            print(f"  [=] Draft: {strat_code} (already exists)")
            continue

        strat_name = draft_data.get("strat_name", f"draft_{strat_code}")
        todo_fields = _extract_todo_fields(draft_data)
        todo_count = len(todo_fields)

        # Try to link to strategy by name
        strategy_id = None
        if strat_name:
            strat = session.execute(
                select(Strategy).where(func.lower(Strategy.name).contains(strat_name.lower()))
            ).scalar_one_or_none()
            if strat:
                strategy_id = strat.id

        draft = Draft(
            strat_code=strat_code,
            strat_name=strat_name,
            strategy_id=strategy_id,
            data=draft_data,
            todo_count=todo_count,
            todo_fields=todo_fields,
            active=draft_data.get("active", False),
            tested=draft_data.get("tested", False),
            prod=draft_data.get("prod", False),
        )
        session.add(draft)
        session.flush()
        imported += 1
        print(f"  [+] Draft: {strat_code} ({strat_name}) - {todo_count} TODOs")

    return {"drafts": imported}


def import_history(session, data_dir: Path) -> dict[str, int]:
    """Import research history from data/research/history.yaml.

    Returns count of imported history entries.
    """
    history_file = data_dir / "research" / "history.yaml"
    if not history_file.exists():
        print(f"  [skip] {history_file} not found")
        return {"history": 0}

    with open(history_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        print(f"  [skip] {history_file} is empty")
        return {"history": 0}

    entries = data.get("researched_videos", [])
    if not entries:
        print(f"  [skip] No researched_videos in {history_file}")
        return {"history": 0}

    imported = 0

    for entry in entries:
        video_id = entry.get("video_id")
        if not video_id:
            continue

        # Resolve topic
        topic_slug = entry.get("topic")
        topic_id = None
        if topic_slug:
            topic = session.execute(
                select(Topic).where(Topic.slug == topic_slug)
            ).scalar_one_or_none()
            if topic:
                topic_id = topic.id

        # Resolve channel
        channel_name = entry.get("channel")
        channel_id = None
        if channel_name:
            ch = session.execute(
                select(Channel).where(Channel.name == channel_name)
            ).scalar_one_or_none()
            if ch:
                channel_id = ch.id

        # Check for duplicates
        existing = session.execute(
            select(ResearchHistory).where(
                ResearchHistory.video_id == video_id,
                ResearchHistory.topic_id == topic_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            print(f"  [=] History: {video_id} (already exists)")
            continue

        history = ResearchHistory(
            video_id=video_id,
            url=entry.get("url", f"https://youtube.com/watch?v={video_id}"),
            channel_id=channel_id,
            topic_id=topic_id,
            strategies_found=entry.get("strategies_found", 0),
        )
        session.add(history)
        session.flush()
        imported += 1
        print(f"  [+] History: {video_id}")

    return {"history": imported}


def main():
    """Run the full import pipeline."""
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_SYNC")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        print("Set it to your PostgreSQL connection string, e.g.:")
        print("  export DATABASE_URL=postgresql+asyncpg://irt:password@localhost:5432/irt")
        sys.exit(1)

    print("=" * 60)
    print("IRT Data Import: YAML/JSON -> PostgreSQL")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print()

    totals = {}

    with sync_session_ctx() as session:
        print("[1/4] Importing channels...")
        totals.update(import_channels(session, DATA_DIR))
        print()

        print("[2/4] Importing strategies...")
        totals.update(import_strategies(session, DATA_DIR))
        print()

        print("[3/4] Importing drafts...")
        totals.update(import_drafts(session, DATA_DIR))
        print()

        print("[4/4] Importing history...")
        totals.update(import_history(session, DATA_DIR))
        print()

    print("=" * 60)
    print("Import complete:")
    for key, count in totals.items():
        print(f"  {key}: {count} new")
    print("=" * 60)


if __name__ == "__main__":
    main()
