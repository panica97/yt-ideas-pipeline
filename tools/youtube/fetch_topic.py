#!/usr/bin/env python3
"""Fetch recent uploads from all channels in a topic."""

import io
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import yaml

from .formatting import format_date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def save_db(data, db_path):
    with open(db_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_db(db_path):
    if not os.path.exists(db_path):
        print(f"Error: channels.yaml not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    with open(db_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"topics": {}}


def load_channels(topic, db_path):
    data = load_db(db_path)
    topics = data.get("topics", {})

    # Match topic by substring
    matching = {k: v for k, v in topics.items() if topic in k}
    if not matching:
        print(f"Error: No topic matching '{topic}' found.", file=sys.stderr)
        print(f"Available topics: {', '.join(topics.keys())}", file=sys.stderr)
        sys.exit(1)
    if len(matching) > 1:
        print(f"Error: Ambiguous topic '{topic}'. Matches: {', '.join(matching.keys())}", file=sys.stderr)
        sys.exit(1)

    topic_name = list(matching.keys())[0]
    channels = matching[topic_name].get("channels", [])
    if not channels:
        print(f"No channels in topic '{topic_name}'.", file=sys.stderr)
        sys.exit(0)
    return topic_name, channels, data


def fetch_channel_videos(channel, count):
    """Fetch recent videos from a single channel using yt-dlp."""
    url = channel["url"] + "/videos"
    cmd = [
        "yt-dlp",
        url,
        "--playlist-end", str(count),
        "--dump-json",
        "--no-download",
        "--no-warnings",
        "--quiet",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  Timeout fetching {channel['name']}", file=sys.stderr)
        return []

    if result.returncode != 0 and not result.stdout.strip():
        print(f"  Error fetching {channel['name']}: {result.stderr.strip()[:100]}", file=sys.stderr)
        return []

    videos = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            info["_channel_name"] = channel["name"]
            videos.append(info)
        except json.JSONDecodeError:
            continue
    return videos


def parse_args(argv):
    args = argv[1:]
    days = 7
    count = 30
    topic = None
    db_path = None
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            try:
                days = int(args[i + 1])
            except ValueError:
                print(f"Error: --days requires an integer, got '{args[i + 1]}'", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--count" and i + 1 < len(args):
            try:
                count = int(args[i + 1])
            except ValueError:
                print(f"Error: --count requires an integer, got '{args[i + 1]}'", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--db" and i + 1 < len(args):
            db_path = args[i + 1]
            i += 2
        elif not topic:
            topic = args[i]
            i += 1
        else:
            i += 1

    if not db_path:
        print("Error: --db <path> is required.", file=sys.stderr)
        print("Usage: fetch_topic.py --db <path> <topic> [--days N] [--count N]", file=sys.stderr)
        sys.exit(1)

    if not topic:
        print("Usage: fetch_topic.py --db <path> <topic> [--days N] [--count N]", file=sys.stderr)
        print("Example: fetch_topic.py --db ./channels.yaml ai-agents --days 14 --count 50", file=sys.stderr)
        sys.exit(1)

    return topic, days, count, db_path


def main():
    topic_query, days, count, db_path = parse_args(sys.argv)

    if not shutil.which("yt-dlp"):
        print("Error: yt-dlp not found on PATH. Install with: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)

    topic_name, channels, db_data = load_channels(topic_query, db_path)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    # Fetch per-channel count to have enough results before filtering
    per_channel = max(10, count // len(channels) + 5)

    print(f"Fetching recent videos for topic '{topic_name}' (last {days} days)...", file=sys.stderr)
    print(f"Channels: {', '.join(ch['name'] for ch in channels)}\n", file=sys.stderr)

    all_videos = []
    fetched_channels = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_channel_videos, ch, per_channel): ch for ch in channels}
        for future in as_completed(futures):
            ch = futures[future]
            try:
                videos = future.result()
                print(f"  {ch['name']}: {len(videos)} videos fetched", file=sys.stderr)
                all_videos.extend(videos)
                if videos:
                    fetched_channels.append(ch)
            except Exception as e:
                print(f"  {ch['name']}: error - {e}", file=sys.stderr)

    # Update last_fetched for channels that returned videos
    if fetched_channels:
        today = datetime.now().strftime("%Y-%m-%d")
        for ch in fetched_channels:
            ch["last_fetched"] = today
        save_db(db_data, db_path)

    # Filter by date
    filtered = [v for v in all_videos if (v.get("upload_date") or "00000000") >= cutoff]

    if not filtered:
        print(f"\nNo videos found in the last {days} days.", file=sys.stderr)
        sys.exit(0)

    # Sort newest first
    filtered.sort(key=lambda v: v.get("upload_date", "00000000"), reverse=True)
    filtered = filtered[:count]

    print(f"\nFound {len(filtered)} video(s) from the last {days} days:\n", file=sys.stderr)

    divider = "\u2500" * 60

    for i, info in enumerate(filtered, 1):
        title = info.get("title", "Unknown Title")
        channel = info.get("_channel_name", info.get("channel", info.get("uploader", "Unknown")))
        date = format_date(info.get("upload_date", ""))
        video_id = info.get("id", "")
        url = f"https://youtube.com/watch?v={video_id}" if video_id else "N/A"

        print(divider)
        print(f" {i:>2}. {title}")
        print(f"     {channel}  \u00b7  {date}")
        print(f"     {url}")

    print(divider)


if __name__ == "__main__":
    main()
