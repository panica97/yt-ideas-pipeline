#!/usr/bin/env python3
"""Channel database CRUD for yt-search skill."""

import io
import os
import re
import sys

import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def load_db(path):
    if not os.path.exists(path):
        return {"topics": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"topics": {}}


def save_db(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def normalize_url(url):
    """Normalize channel URL to consistent format."""
    url = url.rstrip("/")
    return url


def cmd_topics(db):
    topics = db.get("topics", {})
    if not topics:
        print("No topics defined yet. Use 'add' to create one.")
        return
    for name, info in topics.items():
        desc = info.get("description", "")
        count = len(info.get("channels", []))
        desc_str = f" - {desc}" if desc else ""
        print(f"  {name} ({count} channels){desc_str}")


def cmd_list(db, topic_filter=None):
    topics = db.get("topics", {})
    if topic_filter:
        matching = {k: v for k, v in topics.items() if topic_filter in k}
        if not matching:
            print(f"No topic matching '{topic_filter}' found.")
            return
    else:
        matching = topics

    if not matching:
        print("No topics defined yet.")
        return

    for name, info in matching.items():
        desc = info.get("description", "")
        print(f"\n[{name}]" + (f" - {desc}" if desc else ""))
        channels = info.get("channels", [])
        if not channels:
            print("  (no channels)")
        for ch in channels:
            fetched = ch.get("last_fetched")
            fetched_str = f"  (last fetched: {fetched})" if fetched else ""
            print(f"  - {ch['name']}  {ch['url']}{fetched_str}")


def cmd_add(db, db_path, topic, url, name=None):
    url = normalize_url(url)
    if not name:
        # Extract name from URL: @Handle -> Handle
        match = re.search(r"@([^/]+)$", url)
        name = match.group(1) if match else url.split("/")[-1]

    topics = db.setdefault("topics", {})
    topic_data = topics.setdefault(topic, {"description": "", "channels": []})
    channels = topic_data.setdefault("channels", [])

    # Check for duplicates
    for ch in channels:
        if normalize_url(ch["url"]) == url:
            print(f"Channel '{url}' already exists in topic '{topic}'.")
            return

    channels.append({"name": name, "url": url, "last_fetched": None})
    save_db(db, db_path)
    print(f"Added '{name}' ({url}) to topic '{topic}'.")


def cmd_remove(db, db_path, topic, url):
    url = normalize_url(url)
    topics = db.get("topics", {})
    if topic not in topics:
        print(f"Topic '{topic}' not found.")
        return

    channels = topics[topic].get("channels", [])
    original_len = len(channels)
    channels = [ch for ch in channels if normalize_url(ch["url"]) != url]

    if len(channels) == original_len:
        print(f"Channel '{url}' not found in topic '{topic}'.")
        return

    topics[topic]["channels"] = channels
    save_db(db, db_path)
    print(f"Removed '{url}' from topic '{topic}'.")


def parse_db_flag(args):
    """Extract --db path from args, return (db_path, remaining_args)."""
    remaining = []
    db_path = None
    i = 0
    while i < len(args):
        if args[i] == "--db" and i + 1 < len(args):
            db_path = args[i + 1]
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    if not db_path:
        print("Error: --db <path> is required.", file=sys.stderr)
        print("Usage: channels.py --db <path> <command> [args]", file=sys.stderr)
        sys.exit(1)
    return db_path, remaining


def main():
    db_path, args = parse_db_flag(sys.argv[1:])

    if not args:
        print("Usage: channels.py --db <path> <command> [args]")
        print("Commands:")
        print("  topics                      - List all topics")
        print("  list [topic]                - Show channels (all or per topic)")
        print("  add <topic> <url> [--name N] - Add channel to topic")
        print("  remove <topic> <url>        - Remove channel from topic")
        sys.exit(1)

    command = args[0]
    db = load_db(db_path)

    if command == "topics":
        cmd_topics(db)
    elif command == "list":
        topic_filter = args[1] if len(args) > 1 else None
        cmd_list(db, topic_filter)
    elif command == "add":
        if len(args) < 3:
            print("Usage: channels.py --db <path> add <topic> <url> [--name 'Channel Name']", file=sys.stderr)
            sys.exit(1)
        topic = args[1]
        url = args[2]
        name = None
        if "--name" in args:
            idx = args.index("--name")
            if idx + 1 < len(args):
                name = args[idx + 1]
        cmd_add(db, db_path, topic, url, name)
    elif command == "remove":
        if len(args) < 3:
            print("Usage: channels.py --db <path> remove <topic> <url>", file=sys.stderr)
            sys.exit(1)
        cmd_remove(db, db_path, args[1], args[2])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
