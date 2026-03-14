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

## Output Format

```yaml
saved:
  - "<strategy name 1>"
  - "<strategy name 2>"
skipped:
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
