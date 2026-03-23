---
name: strategy-translator
description: Translate strategy variant descriptions into IBKR JSON draft files. Literal translation only — no creative decisions, no variant generation. Called by the research agent after strategy-variants.
---

# Strategy Translator

Takes a list of strategy variants (produced by strategy-variants) and translates each one into a single IBKR JSON draft file. This is a mechanical translation — the creative decisions (which markets, timeframes, exit methods, direction splits) have already been made upstream.

One variant in, one JSON draft out. No creativity, no invention.

## Input

- `variants`: list of variant objects from strategy-variants, each containing:
  - `variant_name`, `parent_strategy`, `direction`, `symbol`, `timeframe`
  - `entry_rules` — concrete entry conditions as text
  - `exit_rules` — concrete exit conditions as text
  - `indicators_needed` — list of indicators with params
  - `notes` — context (source, removed SL/TP, rationale)

## Reference Files

Read in this order before translating:
1. `docs/STRATEGY_FILE_REFERENCE.md` — **primary source of truth** for every field, indicator, condition type, and shift behavior
2. `examples/*.json` (in this skill's directory) — real strategies as format reference
3. `translation-rules.md` (in this skill's directory) — mapping rules and accumulated feedback
4. `schema.json` (in this skill's directory) — JSON schema for validation

## Translation Process

For EACH variant:

1. Read the variant's `entry_rules`, `exit_rules`, and `indicators_needed`
2. Map `indicators_needed` to the `ind_list` format (see STRATEGY_FILE_REFERENCE.md section 4)
3. Map `entry_rules` to `long_conds` or `short_conds` depending on `direction`
   - If direction is `"long"`: populate `long_conds`, leave `short_conds` empty
   - If direction is `"short"`: populate `short_conds`, leave `long_conds` empty
4. Map `exit_rules` to `exit_conds`
5. Fill instrument fields from `symbol` and `timeframe`
6. Leave SL/TP as defaults (all `false`, empty params)
7. Set `_notes` as an object from the variant's `notes`
8. Mark unknown values with `"_TODO"` — never guess

## Critical Rules for Conditions

These come from the trading engine spec. Getting them wrong produces invalid strategies.

**Entry vs Exit logic**:
- `long_conds` and `short_conds`: ALL conditions ANDed. Do NOT use `group` field.
- `exit_conds`: use `group` for OR between groups (AND within same group). Use `"mode": "force"` for immediate exit conditions.

**Shifts**:
- `shift_1` = LEFT operand, `shift_2` = RIGHT operand
- Shift values must be >= 1. Shift 0 does not exist.
- shift 1 = most recent completed bar, shift 2 = bar before that, etc.

**The `cond` string must be unambiguous**:
- Same indicator at different shifts: `"LOW_6H < LOW_6H"` with `shift_1` and `shift_2` differentiating them. Never put shift notation like `(N)` inside the `cond` string.
- Cross operators use `above` / `bellow` (engine spelling)

**Multi-output indicators** (MACD, STOCH, BBANDS, KELTNER, ICHIMOKU):
- `indCode` MUST start with `"MULT_"` followed by a suffix

**Pure strategies only**:
- Do NOT generate `stop_loss_init`, `take_profit_init`, or `stop_loss_mgmt` — leave as defaults
- Do NOT create SL/TP indicators — only indicators needed by conditions

## strat_code Assignment

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

## Save Drafts

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import upsert_draft

with sync_session_ctx() as session:
    upsert_draft(session, strat_code=next_code, strat_name="<variant_name>", data=draft_json)
```

## Output Format

```yaml
drafts_created:
  - strat_code: 9001
    strat_name: "<variant_name>"
    parent_strategy: "<parent strategy name>"
    todo_count: <N>
total_drafts: <N>
```

## Error Handling

- DATABASE_URL not set: report the error, cannot proceed
- Connection error: report the error
- Variant too vague to translate: skip and report
- Unknown indicator type: use `"_TODO"` for the indicator params, note in `_notes`
