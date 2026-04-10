---
name: db-persistence
description: Save strategies and drafts to PostgreSQL with deduplication and channel resolution
domain: shared
role: agent
inputs:
  - name: strategies
    type: "Strategy[]"
  - name: drafts
    type: "Draft[]"
outputs:
  - name: confirmation
    type: object
skills_used:
  - db-manager
dependencies: []
---

# DB Persistence Agent

Persists strategies and their variant drafts to PostgreSQL. Handles deduplication, channel resolution, and history logging. This agent is a shared capability used by any domain that needs to write to the database.

## When to Use

Call this agent when you have finalized `Strategy[]` and/or `Draft[]` data that needs to be saved to the database. The data should already be fully processed (purified, translated, TODO-resolved) before reaching this agent.

## Prerequisites

- `DATABASE_URL` environment variable must be set (points to the PostgreSQL instance).
- The database schema must be up to date (Alembic migrations applied).
- Input data must conform to the formats described below.

## Input Formats

### Strategy Data (for inserting parent strategies)

Each strategy is a dict with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Strategy name (used for deduplication, case-insensitive) |
| `description` | string | no | Brief description of the strategy |
| `source_channel` | string | no | Channel name (will be resolved to `source_channel_id`) |
| `source_videos` | list[string] | no | YouTube URLs used as sources |
| `parameters` | list[dict] | no | Strategy parameters |
| `entry_rules` | list[string] | no | Entry rules in natural language |
| `exit_rules` | list[string] | no | Exit rules in natural language |
| `risk_management` | list[string] | no | Risk management rules |
| `notes` | list[string] | no | Additional notes |

### Draft Data (for inserting variant drafts)

Each draft is a dict with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `strat_code` | integer | yes | Unique draft identifier (dedup key) |
| `strat_name` | string | yes | Descriptive variant name (e.g., `RSI_Divergence_SAR_360m`) |
| `draft_json` | dict | yes | The full IBKR JSON draft data |
| `strategy_id` | integer | yes | FK to the parent strategy (obtained after inserting the parent) |
| `parent_strategy` | string | yes | Parent strategy name (used to group variants) |

Optional draft fields: `active` (bool, default false), `tested` (bool, default false), `prod` (bool, default false).

## Execution Steps

### Step 1: Validate Input

Before any DB operations, validate the input:

1. Confirm `DATABASE_URL` is set. If not, attempt YAML fallback (see Fallback section).
2. Verify each strategy has a `name` field (non-empty string).
3. Verify each draft has `strat_code` (integer), `strat_name` (non-empty string), and `draft_json` (dict).
4. If validation fails, report which items are invalid and stop without saving anything.

### Step 2: Group Variants by Parent Strategy

Group all variants/drafts by their `parent_strategy` name. This determines how many parent strategies to create and which drafts belong to each.

```python
parents = {}
for variant in all_variants:
    pname = variant["parent_strategy"]
    parents.setdefault(pname, []).append(variant)
```

### Step 3: Persist Strategies and Drafts

For each parent strategy group, execute the following sequence using the `db-manager` skill (read `.claude/skills/db-manager/SKILL.md` for detailed conventions).

```python
from tools.db.session import sync_session_ctx
from tools.db.strategy_repo import insert_strategy
from tools.db.draft_repo import upsert_draft
from tools.db.channel_repo import get_channel_by_name

with sync_session_ctx() as session:
    saved = []
    updated = []
    drafts_created = 0
    drafts_updated = 0

    for parent_name, variants in parents.items():
        # 3a. Channel Resolution
        # Resolve source_channel name to source_channel_id
        source_channel_id = None
        ch_name = variants[0].get("source_channel")
        if ch_name:
            ch = get_channel_by_name(session, ch_name)
            if ch:
                source_channel_id = ch.id

        # 3b. Deduplication Check + Insert/Update Strategy
        # insert_strategy() uses upsert_strategy() internally
        # which does case-insensitive name matching:
        # - If a strategy with the same name exists -> UPDATE it
        # - If no match -> INSERT new strategy
        from tools.db.strategy_repo import get_strategy_by_name
        existing = get_strategy_by_name(session, parent_name)
        
        parent = insert_strategy(session, {
            "name": parent_name,
            "description": variants[0].get("description", ""),
            "source_channel_id": source_channel_id,
            "source_videos": variants[0].get("source_videos", []),
            "entry_rules": variants[0].get("entry_rules", []),
            "exit_rules": variants[0].get("exit_rules", []),
            "risk_management": variants[0].get("risk_management", []),
            "notes": variants[0].get("notes", []),
        })

        if existing:
            updated.append(parent_name)
        else:
            saved.append(parent_name)

        # 3c. Upsert Drafts linked to parent
        # Each variant draft is linked via strategy_id
        for v in variants:
            from tools.db.draft_repo import get_draft_by_code
            existing_draft = get_draft_by_code(session, v["strat_code"])
            
            upsert_draft(
                session,
                strat_code=v["strat_code"],
                strat_name=v["strat_name"] if "strat_name" in v else v.get("variant_name", ""),
                data=v["draft_json"],
                strategy_id=parent.id,
                active=v.get("active", False),
                tested=v.get("tested", False),
                prod=v.get("prod", False),
            )
            
            if existing_draft:
                drafts_updated += 1
            else:
                drafts_created += 1
```

**Key rules:**
- Always create the parent strategy BEFORE its variant drafts.
- Always pass `strategy_id` when calling `upsert_draft()`.
- `upsert_draft()` automatically computes `todo_count` and `todo_fields` by scanning the `data` JSONB for `_TODO` values.
- Deduplication for strategies is case-insensitive by `name`.
- Deduplication for drafts is by `strat_code` (unique constraint).

### Step 4: History Logging (optional)

If video metadata is provided alongside the strategies (i.e., the caller passes `videos_processed` data), log each video to the research history:

```python
from tools.db.research_repo import add_history, resolve_topic_id

with sync_session_ctx() as session:
    topic_id = resolve_topic_id(session, topic_slug) if topic_slug else None
    
    for video in videos_processed:
        add_history(
            session,
            video_id=video["video_id"],
            url=video["url"],
            channel_id=video.get("channel_id"),
            topic_id=topic_id,
            strategies_found=video.get("strategies_found", 0),
            classification=video.get("classification"),
            title=video.get("title"),
            session_id=video.get("session_id"),
        )
```

History logging is deduplicated by `(video_id, topic_id)` -- if an entry already exists, it is returned unchanged.

**Do not log history if no video metadata is provided.** History logging is the caller's responsibility to request; this agent does not assume a research context.

## Output Format

Return a structured confirmation:

```yaml
status: OK | ERROR
saved:
  - "Strategy Name 1"
  - "Strategy Name 2"
updated:
  - "Duplicate Strategy Name"
skipped: []
drafts_created: <count>
drafts_updated: <count>
history_logged: <count>  # only if history logging was requested
errors: []               # list of error messages if any operations failed
```

## Error Handling

- **DATABASE_URL not set**: Report the error. Attempt YAML fallback if possible.
- **Connection error**: Report the error with details. Do not retry automatically.
- **Invalid input data**: Report which strategies/drafts have invalid data and what fields are missing. Save nothing for invalid items, but continue processing valid ones.
- **Channel resolution failure**: If `get_channel_by_name()` returns `None`, set `source_channel_id = None` and continue. Do not fail the operation because a channel is not in the DB.
- **Partial failure**: If some strategies save but others fail, report both the successes and failures in the output.

## YAML Fallback

If `DATABASE_URL` is not set, fall back to file-based persistence:

1. Read `data/strategies/strategies.yaml` (create if it doesn't exist).
2. Compare each strategy by name (case-insensitive) to detect duplicates.
3. Append new strategies, update existing ones.
4. Write the updated file back to `data/strategies/strategies.yaml`.

Note: YAML fallback does NOT support drafts or history logging -- only strategy records.

## Scope Boundaries

This agent:
- **DOES**: Insert/update strategies, upsert drafts, resolve channels, log history, handle deduplication.
- **DOES NOT**: Know about sessions, pipelines, or pipeline orchestration.
- **DOES NOT**: Know about video discovery, strategy extraction, or NotebookLM.
- **DOES NOT**: Create or manage research sessions (that is the Manager's responsibility).
- **DOES NOT**: Transform, purify, or translate strategies -- data must arrive ready to persist.
