---
name: db-manager
description: Save strategies to PostgreSQL database with deduplication (case-insensitive by name)
---

# DB Manager

Saves new strategies to the PostgreSQL database, avoiding duplicates.

## Database

PostgreSQL via `tools.db.strategy_repo` (sync session).

## How to save strategies

```python
from tools.db.session import sync_session_ctx
from tools.db.strategy_repo import insert_strategy

with sync_session_ctx() as session:
    for strategy_data in strategies:
        result = insert_strategy(session, strategy_data)
        # result is a Strategy ORM object
        # insert_strategy handles dedup by name (case-insensitive)
```

The `strategy_data` dict should have these keys (matching YAML format):
- `name` (required, string)
- `description` (string)
- `source_videos` (list of strings)
- `parameters` (list of dicts)
- `entry_rules` (list of strings)
- `exit_rules` (list of strings)
- `risk_management` (list of strings)
- `notes` (list of strings)

## Rules

- Use `tools.db.strategy_repo.insert_strategy()` for each strategy
- Deduplication is automatic: case-insensitive name matching
- If a strategy with the same name exists, it is updated (upsert)
- Only add NEW strategies -- existing ones are updated, not duplicated
- The function handles all DB operations within the context manager

## Saving Drafts

The translator step generates **multiple JSON drafts per idea** (variants by timeframe, exit method, filters, etc.). Each variant is a separate draft.

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import upsert_draft

with sync_session_ctx() as session:
    # Each variant gets its own strat_code, starting at 9001 and incrementing
    upsert_draft(session, strat_code=9001, strat_name="RSI_Divergence_SAR_360m", data=draft_json_v1)
    upsert_draft(session, strat_code=9002, strat_name="RSI_Divergence_TimeExit_240m", data=draft_json_v2)
    upsert_draft(session, strat_code=9003, strat_name="RSI_Divergence_ATR_Daily", data=draft_json_v3)
    # Automatically computes todo_count and todo_fields from _TODO values in data
```

`upsert_draft()` deduplicates by `strat_code`. If a draft with the same `strat_code` exists, it is updated.
Additional optional params: `strategy_id`, `active`, `tested`, `prod`.

**Important**: Each variant must have a distinct `strat_name` that describes the variation clearly. Use `"_TODO"` for any values that cannot be determined from the source idea — never guess parameter values.

## Output Format

```yaml
saved:
  - "<strategy name 1>"
  - "<strategy name 2>"
updated:
  - "<duplicate strategy name>"
total_in_db: <number>
```

## Error Handling

- DATABASE_URL not set: report the error, cannot save
- Connection error: report the error
- Input data has invalid format: report which strategies and save nothing

## Fallback

If `DATABASE_URL` is not set, fall back to the YAML file approach:
- Read `data/strategies/strategies.yaml` before writing
- Compare by name (case-insensitive) to detect duplicates
- Write the updated file back to `data/strategies/strategies.yaml`
