---
name: strategy-translator
description: Structure raw strategy ideas for the frontend and generate IBKR draft variants (creative proposer)
---

# Strategy Translator

Takes raw strategy ideas (as extracted by notebooklm-analyst with flat string arrays) and does two things:
1. **Part A** -- Structures the idea for the frontend and updates the DB
2. **Part B** -- Translates valid ideas into IBKR JSON draft variants (creative proposer)

## Input

- `strategy_names`: list of strategy names already saved in DB by db-manager (raw format)
- `notebook_id` (optional): NotebookLM notebook ID for follow-up questions

## Part A: Structure Ideas for the Frontend

For EACH strategy in the input list:

1. Fetch the strategy from the DB by name
2. Transform raw fields into properly structured format:
   - `parameters`: convert from flat strings like `"indicators: ['VWAP', 'ATR']"` into proper objects `[{name, description, type, default, range}]`
   - `entry_rules`: keep as list of strings but clean up (remove prefixes like "long:", "short:" -- make each rule a clear standalone sentence)
   - `exit_rules`: same cleanup
   - `risk_management`: same cleanup
   - `notes`: same cleanup
3. Update the strategy in the DB:

```python
from tools.db.session import sync_session_ctx
from tools.db.strategy_repo import upsert_strategy

with sync_session_ctx() as session:
    upsert_strategy(
        session,
        name=strategy_name,
        parameters=structured_parameters,
        entry_rules=cleaned_entry_rules,
        exit_rules=cleaned_exit_rules,
        risk_management=cleaned_risk_management,
        notes=cleaned_notes,
    )
```

Part A ALWAYS runs for every strategy.

## Part B: Translate to IBKR Drafts (Creative Proposer)

For each idea with concrete entry/exit logic, generate **2-4 JSON draft variants** for the IBKR trading engine.

### Reference Files

Read these files from this skill's own directory (`.claude/skills/strategy-translator/`):
- `schema.json` -- JSON schema of the trading engine (follow strictly)
- `examples/*.json` -- real strategies as few-shot for exact format
- `translation-rules.md` -- filtering and mapping rules

### Filtering (skip)

Discard ideas that do NOT have concrete entry/exit logic:
- Ideas too vague or conceptual -> skip (log as "too vague for translation")
- Historical/abandoned approaches -> skip
- Meta-strategies (portfolio management, prop firm scaling, trading psychology) -> skip

### Creative Process

For each idea with actionable entry/exit rules:

1. Read `schema.json` and the examples in `examples/` to understand the exact format
2. Analyze the idea: what indicators? what entry/exit conditions?
3. Think about variants -- differences can be:
   - **Timeframe**: e.g., 240min vs 360min vs daily
   - **Exit method**: stop & reverse vs time-based exit vs ATR-based SL/TP
   - **Additional filters**: trend filter, volume, volatility
   - **Market specialization**: if the idea mentions better-performing markets
4. If data is missing to complete a field, query the NotebookLM notebook (if `notebook_id` provided):
   ```bash
   notebooklm ask "<question>" -n <notebook_id>
   ```
5. Generate one complete JSON per variant following `schema.json` strictly
6. Mark unknown values with `"_TODO"` -- never guess parameter values
7. Each variant gets a unique `strat_code` and a descriptive `strat_name`
   - Format: `"<Indicator>_<Logic>_<Exit>_<Timeframe>"`
   - Examples: `"RSI_Divergence_SAR_360m"`, `"VWAP_Bounce_ATR_Daily"`

### strat_code Assignment

Get the next available code from the DB:

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import get_all_drafts

with sync_session_ctx() as session:
    existing = get_all_drafts(session)
    max_code = max((d.strat_code for d in existing), default=9000)
    next_code = max_code + 1
```

Each variant gets a unique `strat_code` starting from `next_code` and incrementing.

### Save Drafts

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import upsert_draft

with sync_session_ctx() as session:
    upsert_draft(session, strat_code=next_code, strat_name="<name>", data=draft_json)
    upsert_draft(session, strat_code=next_code+1, strat_name="<name_variant2>", data=draft_json_v2)
    # ... one call per variant
    # Automatically computes todo_count and todo_fields from _TODO values in data
```

## Rules

- Process ALL strategies passed in `strategy_names`
- Part A (structuring) ALWAYS runs for every strategy
- Part B (IBKR translation) runs only for valid ideas -- skip if too vague per `translation-rules.md`
- Use `"_TODO"` for unknown values, never guess
- Each variant must have a distinct `strat_name` that describes the variation clearly
- Objective: 2-4 variants per idea when the idea has enough detail. If only one reasonable implementation exists, one variant is sufficient.

## Output Format

```yaml
structured:
  - name: "<strategy name>"
    status: ok | skipped
    reason: "<if skipped>"
drafts_created:
  - strat_code: 9001
    strat_name: "<descriptive name>"
    strategy: "<parent strategy name>"
    todo_count: <N>
total_drafts: <N>
```

## Error Handling

- DATABASE_URL not set: report the error, cannot proceed
- Connection error: report the error
- Strategy not found in DB: report which strategy and skip it
- NotebookLM query fails: continue without the extra data, use `"_TODO"` for missing fields
