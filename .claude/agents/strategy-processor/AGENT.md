---
name: strategy-processor
description: Purify strategies, split directions, generate variants, translate to IBKR JSON, and auto-fill TODOs
domain: research
role: agent
inputs:
  - name: strategies
    type: "Strategy[]"
    required: true
outputs:
  - name: drafts
    type: "Draft[]"
skills_used:
  - strategy-variants
  - strategy-translator
  - todo-review
dependencies: []
---

# Strategy Processor Agent

Takes raw strategy YAML and produces complete IBKR JSON drafts ready for backtesting. Runs three skills in sequence: strategy-variants (purify, split, propose variants), strategy-translator (translate to JSON), and todo-review (auto-fill resolvable fields).

This agent is self-contained. It does not know about sessions, DB persistence, video discovery, or strategy extraction.

## How to Use

Given a `Strategy[]` (list of strategy objects in YAML format as defined in `DATA_FORMATS.md`), this agent processes them through three sequential steps and returns `Draft[]` (IBKR JSON drafts saved in the database).

## Step 1: Strategy Variants

Read `.claude/skills/strategy-variants/SKILL.md` for the full skill interface.

Pass the entire strategy YAML to the strategy-variants skill. The skill performs four operations on each strategy:

### 1.1 Purify

- Removes all risk management rules (SL, TP, trailing stops, breakeven, position sizing)
- Captures what was removed in the notes (e.g., `"removed_sl_tp": "ATR-based SL at 1.5x, TP at 3x"`)
- Keeps only entry_rules and exit_rules

### 1.2 Separate Directions

- If a strategy has both long AND short entry rules, split it into two independent strategies
- Name them clearly: `"RSI_Exhaustion"` becomes `"RSI_Exhaustion_Long"` and `"RSI_Exhaustion_Short"`
- If short rules are described as "mirror of long", invert the conditions explicitly
- If the strategy is inherently one-directional, keep as-is

### 1.3 Propose Exit Method

Each variant needs exactly ONE exit method:

1. **Stop & Reverse**: only valid for bidirectional strategies that are kept together (not split). Not valid for unidirectional variants.
2. **Source specifies a concrete exit**: use it as-is (e.g., "exit after 20 bars", "RSI > 90")
3. **No valid exit**: use `num_bars` exit with `_TODO` as the value

### 1.4 Propose Variants

- Combine purified, direction-split strategies with market and timeframe options
- Use `recommended_markets` and `recommended_timeframes` from the strategy data
- Exclude any market in `avoid_markets` or timeframe in `avoid_timeframes`
- If no markets or timeframes recommended, use `_TODO`
- **Maximum 5 variants per original strategy** (long/short split counts toward the limit)

### Output from Step 1

A YAML list of variant objects, each with: `variant_name`, `parent_strategy`, `direction`, `symbol`, `timeframe`, `entry_rules`, `exit_rules`, `indicators_needed`, `notes`.

## Step 2: Strategy Translator

Read `.claude/skills/strategy-translator/SKILL.md` for the full skill interface.

Pass the variant list from Step 1 to the strategy-translator skill. The translator converts EACH variant into a single IBKR JSON draft file. This is a mechanical, literal translation -- no creative decisions.

### Key translation rules

Before translating, read these reference files (in the skill's directory):
1. `docs/STRATEGY_FILE_REFERENCE.md` -- primary source of truth for fields, indicators, conditions
2. `.claude/skills/strategy-translator/examples/*.json` -- real strategies as format reference
3. `.claude/skills/strategy-translator/translation-rules.md` -- mapping rules
4. `.claude/skills/strategy-translator/schema.json` -- JSON schema for validation

### Translation process per variant

1. Map `indicators_needed` to the `ind_list` format
2. Map `entry_rules` to `long_conds` or `short_conds` depending on `direction`
3. Map `exit_rules` to `exit_conds`
4. Fill instrument fields from `symbol` and `timeframe`
5. Leave SL/TP as defaults (all `false`, empty params)
6. Mark unknown values with `"_TODO"` -- never guess

### strat_code assignment

Get the next available code from the DB:

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import get_all_drafts

with sync_session_ctx() as session:
    existing = get_all_drafts(session)
    max_code = max((d.strat_code for d in existing), default=9000)
    next_code = max_code + 1
```

Each variant gets a unique `strat_code` starting from `next_code`.

### Save drafts to DB

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import upsert_draft

with sync_session_ctx() as session:
    upsert_draft(session, strat_code=next_code, strat_name="<variant_name>", data=draft_json)
```

### Output from Step 2

A list of `strat_code` values for the newly created drafts.

## Step 3: TODO Auto-Resolution

Read `.claude/skills/todo-review/SKILL.md` for the full skill interface.

Pass the list of `strat_code` values from Step 2 to the todo-review skill. This step auto-fills resolvable `_TODO` fields before they reach the user.

### Resolution tiers

1. **Tier 1 -- Instrument Lookup**: queries `GET /api/instruments/{symbol}` to fill `exchange`, `multiplier`, `minTick`, `currency`, `secType`
2. **Tier 2 -- Sensible Defaults**: applies defaults for `rolling_days` (5), `currency` ("USD"), `secType` ("FUT"), `trading_hours` (null)
3. **Tier 3 -- Never Auto-Fill**: indicator parameters, condition thresholds, `max_timePeriod`, `max_shift`, `control_params` -- these are left as `_TODO` for human review

### API configuration

- API base: `http://localhost:8000`
- API key: read `DASHBOARD_API_KEY` from the `.env` file at the project root
- Header: `X-API-Key: <value>`

### Process per draft

1. Fetch the draft: `GET /api/strategies/drafts/{strat_code}`
2. Scan the JSON recursively for `_TODO` fields
3. Query the instruments API if `symbol` is not `_TODO`
4. Apply Tier 1 resolutions (instrument data)
5. Apply Tier 2 defaults
6. Patch each resolved field: `PATCH /api/strategies/drafts/{strat_code}/fill-todo` with `{"path": "<field_path>", "value": <value>}`
7. Re-fetch to verify updated `todo_count`

### Skip conditions

NONE -- always run this step. Every draft benefits from auto-resolution regardless of how it was produced.

Fields that cannot be auto-resolved are flagged but do not block the output.

## Output

```yaml
status: OK | ERROR
drafts:
  - strat_code: 9001
    strat_name: "<variant_name>"
    parent_strategy: "<parent strategy name>"
    todo_count_before: 12
    todo_count_after: 7
    filled_fields:
      - field: "exchange"
        value: "CME"
        source: "instruments"
      - field: "rolling_days"
        value: 5
        source: "default"
    remaining_todos:
      - field: "ind_list.4 hours[0].params.timePeriod_1"
        reason: "indicator parameter - needs optimization"
total_drafts: <N>
total_todos_resolved: <N>
total_todos_remaining: <N>
```

## Error Handling

- If Step 1 (variants) produces no variants: return `status: ERROR` with detail
- If Step 2 (translator) fails on a variant: skip it, report the error, continue with remaining variants
- If Step 3 (todo-review) fails on a draft: report the error for that draft, continue with remaining drafts. Drafts are already saved in the DB from Step 2, so todo-review failure is non-fatal.
- DATABASE_URL must be set -- the translator requires DB access for strat_code assignment and draft storage

## Rules

- Skills are invoked in strict sequence: variants -> translator -> todo-review
- Every variant produces exactly one JSON draft
- Every draft gets a unique `strat_code`
- Pure strategies only: no SL/TP in the output (removed in Step 1)
- Unknown values are marked `_TODO` -- never invented
- This agent does not fetch videos, create notebooks, track sessions, or save to the strategies table
