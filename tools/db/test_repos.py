"""Verification script: ensure all repos import correctly and models are consistent.

Usage::

    python -m tools.db.test_repos

This does NOT require a database connection -- it only verifies that all
modules import cleanly and model classes have the expected attributes.
"""

from __future__ import annotations

import sys


def test_imports():
    """Verify all repo modules import without errors."""
    errors = []

    modules = [
        ("tools.db", None),
        ("tools.db.base", ["Base", "TimestampMixin"]),
        ("tools.db.models", [
            "Topic", "Channel", "Strategy", "Draft",
            "ResearchHistory", "ResearchSession",
        ]),
        ("tools.db.session", [
            "get_sync_engine", "get_sync_session", "sync_session_ctx",
            "get_async_engine", "get_async_session_factory",
        ]),
        ("tools.db.channel_repo", [
            "get_all_topics", "get_topic_by_slug", "create_topic",
            "update_topic", "delete_topic", "get_channels_by_topic",
            "create_channel", "delete_channel", "update_channel_last_fetched",
            "get_topics_as_dict",
        ]),
        ("tools.db.strategy_repo", [
            "get_strategy_by_name", "get_all_strategies",
            "search_strategies", "upsert_strategy", "insert_strategy",
        ]),
        ("tools.db.draft_repo", [
            "get_draft_by_code", "get_all_drafts", "upsert_draft",
            "_extract_todo_fields",
        ]),
        ("tools.db.research_repo", [
            "create_session", "update_session_step", "complete_session",
            "error_session", "get_active_sessions", "add_history",
        ]),
        ("tools.db.history_repo", [
            "get_history", "get_history_stats",
        ]),
    ]

    for module_name, expected_attrs in modules:
        try:
            mod = __import__(module_name, fromlist=["__name__"])
            if expected_attrs:
                for attr in expected_attrs:
                    if not hasattr(mod, attr):
                        errors.append(f"  {module_name} missing attribute: {attr}")
            print(f"  [OK] {module_name}")
        except Exception as e:
            errors.append(f"  [FAIL] {module_name}: {e}")
            print(f"  [FAIL] {module_name}: {e}")

    return errors


def test_todo_extraction():
    """Verify the _extract_todo_fields helper works correctly."""
    from tools.db.draft_repo import _extract_todo_fields

    errors = []

    # Test 1: simple dict
    data = {"a": "_TODO", "b": "ok", "c": {"d": "_TODO"}}
    result = _extract_todo_fields(data)
    expected = ["a", "c.d"]
    if sorted(result) != sorted(expected):
        errors.append(f"  TODO test 1 failed: got {result}, expected {expected}")
    else:
        print("  [OK] TODO extraction: simple dict")

    # Test 2: nested list
    data = {"items": [{"x": "_TODO"}, {"x": "ok"}]}
    result = _extract_todo_fields(data)
    expected = ["items[0].x"]
    if result != expected:
        errors.append(f"  TODO test 2 failed: got {result}, expected {expected}")
    else:
        print("  [OK] TODO extraction: nested list")

    # Test 3: no TODOs
    data = {"a": 1, "b": "hello"}
    result = _extract_todo_fields(data)
    if result:
        errors.append(f"  TODO test 3 failed: got {result}, expected []")
    else:
        print("  [OK] TODO extraction: no TODOs")

    # Test 4: real draft structure
    data = {
        "strat_code": 9001,
        "stop_loss_init": {
            "indicator_params": {"multiple": "_TODO"}
        },
        "control_params": {
            "start_date": "_TODO",
            "end_date": "_TODO",
        }
    }
    result = _extract_todo_fields(data)
    expected = [
        "stop_loss_init.indicator_params.multiple",
        "control_params.start_date",
        "control_params.end_date",
    ]
    if sorted(result) != sorted(expected):
        errors.append(f"  TODO test 4 failed: got {result}, expected {expected}")
    else:
        print("  [OK] TODO extraction: real draft structure")

    return errors


def test_model_columns():
    """Verify model classes have expected columns."""
    from tools.db.models import (
        Topic, Channel, Strategy, Draft, ResearchHistory, ResearchSession,
    )

    errors = []

    checks = {
        "Topic": (Topic, ["id", "slug", "description", "channels"]),
        "Channel": (Channel, ["id", "topic_id", "name", "url", "last_fetched", "topic"]),
        "Strategy": (Strategy, ["id", "name", "description", "source_channel_id",
                                "source_videos", "parameters", "entry_rules",
                                "exit_rules", "risk_management", "notes"]),
        "Draft": (Draft, ["id", "strat_code", "strat_name", "strategy_id",
                          "data", "todo_count", "todo_fields", "active", "tested", "prod"]),
        "ResearchHistory": (ResearchHistory, ["id", "video_id", "url", "channel_id",
                                              "topic_id", "researched_at", "strategies_found"]),
        "ResearchSession": (ResearchSession, ["id", "status", "topic_id", "step",
                                              "step_name", "total_steps", "channel",
                                              "videos_processing", "started_at",
                                              "completed_at", "error_detail", "result_summary"]),
    }

    for name, (cls, attrs) in checks.items():
        missing = [a for a in attrs if not hasattr(cls, a)]
        if missing:
            errors.append(f"  {name} missing: {missing}")
            print(f"  [FAIL] {name} missing attributes: {missing}")
        else:
            print(f"  [OK] {name}: all {len(attrs)} attributes present")

    return errors


def main():
    print("=" * 60)
    print("IRT Database Repos — Verification")
    print("=" * 60)
    print()

    all_errors = []

    print("[1/3] Testing imports...")
    all_errors.extend(test_imports())
    print()

    print("[2/3] Testing TODO extraction...")
    all_errors.extend(test_todo_extraction())
    print()

    print("[3/3] Testing model columns...")
    all_errors.extend(test_model_columns())
    print()

    print("=" * 60)
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        for err in all_errors:
            print(err)
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
