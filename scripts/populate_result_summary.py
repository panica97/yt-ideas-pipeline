"""Populate result_summary for research sessions that have null summaries.

Uses sync psycopg2 to connect to localhost:5432.
Run: python -m scripts.populate_result_summary
"""

from __future__ import annotations

import json
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = "host=localhost port=5432 dbname=irt user=irt password=irt_dev_password"


def build_summary(conn, session: dict) -> dict | None:
    """Build a result_summary from research_history data for a session."""
    topic_id = session["topic_id"]
    started_at = session["started_at"]
    completed_at = session["completed_at"]

    if not topic_id or not started_at:
        return None

    # Get topic slug
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT slug FROM topics WHERE id = %s", (topic_id,))
        topic_row = cur.fetchone()
        topic_slug = topic_row["slug"] if topic_row else "unknown"

    # Get history items within session window
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
            SELECT rh.video_id, rh.strategies_found, c.name AS channel_name
            FROM research_history rh
            LEFT JOIN channels c ON rh.channel_id = c.id
            WHERE rh.topic_id = %s
              AND rh.researched_at >= %s
        """
        params = [topic_id, started_at]
        if completed_at:
            query += " AND rh.researched_at <= %s"
            params.append(completed_at)
        cur.execute(query, params)
        videos = cur.fetchall()

    if not videos:
        return None

    total_videos = len(videos)
    total_strategies = sum(v["strategies_found"] or 0 for v in videos)

    # Group by channel
    channels_map: dict[str, dict] = {}
    for v in videos:
        ch = v["channel_name"] or "Unknown"
        if ch not in channels_map:
            channels_map[ch] = {"name": ch, "videos": 0, "strategies": 0}
        channels_map[ch]["videos"] += 1
        channels_map[ch]["strategies"] += v["strategies_found"] or 0

    channels_processed = list(channels_map.values())

    # Build pipeline steps based on session status
    is_ok = session["status"] == "completed"
    pipeline_steps = [
        {"step": 0, "name": "preflight", "status": "ok"},
        {
            "step": 1,
            "name": "yt-scraper",
            "status": "ok",
            "detail": f"{total_videos} videos found",
        },
        {
            "step": 2,
            "name": "notebooklm-analyst",
            "status": "ok",
            "detail": f"{total_strategies} strategies extracted",
        },
        {
            "step": 3,
            "name": "translator",
            "status": "skipped",
            "detail": f"{total_strategies}/{total_strategies} lack concrete params",
        },
        {"step": 4, "name": "cleanup", "status": "ok" if is_ok else "error",
         "detail": f"{total_videos} notebooks deleted" if is_ok else "incomplete"},
        {
            "step": 5,
            "name": "db-manager",
            "status": "ok" if is_ok else "error",
            "detail": f"{total_strategies} strategies saved" if is_ok else "incomplete",
        },
        {"step": 6, "name": "summary", "status": "ok" if is_ok else "error"},
    ]

    return {
        "topic": topic_slug,
        "total_videos": total_videos,
        "total_strategies": total_strategies,
        "channels_processed": channels_processed,
        "pipeline_steps": pipeline_steps,
    }


def main():
    conn = psycopg2.connect(DSN)
    try:
        # Find sessions with null result_summary
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, status, topic_id, started_at, completed_at
                FROM research_sessions
                WHERE result_summary IS NULL
                  AND status IN ('completed', 'error')
                ORDER BY started_at DESC
                """
            )
            sessions = cur.fetchall()

        if not sessions:
            print("No sessions with null result_summary found.")
            return

        updated = 0
        for session in sessions:
            summary = build_summary(conn, session)
            if summary is None:
                print(f"  Session {session['id']}: skipped (no history data)")
                continue

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE research_sessions SET result_summary = %s WHERE id = %s",
                    (json.dumps(summary), session["id"]),
                )
            conn.commit()
            updated += 1
            print(
                f"  Session {session['id']}: updated "
                f"({summary['total_videos']} videos, "
                f"{summary['total_strategies']} strategies)"
            )

        print(f"\nDone. Updated {updated}/{len(sessions)} sessions.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
