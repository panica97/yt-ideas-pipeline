---
name: todo-review
description: "Auto-fill _TODO fields in IBKR JSON draft files. Resolves instrument details (exchange, multiplier, minTick, currency, secType) from the Instruments database and applies sensible defaults. Use when drafts have _TODO fields that can be automatically resolved."
---

# Todo Review

Automatically resolves `_TODO` fields in IBKR JSON drafts that have deterministic answers. Reduces manual work so that only genuinely ambiguous TODOs reach the user via todo-fill.

## Configuration

- **API base:** `http://localhost:8000`
- **API key:** read `DASHBOARD_API_KEY` from the `.env` file at the project root
- **Header:** `X-API-Key: <value>`

## What You Receive

- A list of `strat_code` integers or file paths pointing to IBKR JSON draft files
- These correspond to draft records in the database, each containing an IBKR JSON `data` blob with potential `_TODO` values

## What You Return

A report per draft processed:
- Which `_TODO` fields were resolved and their new values (with source: instruments or default)
- Which `_TODO` fields remain and why
- Before/after `todo_count`

## Resolution Rules

### Tier 1: Instrument Lookup (by symbol)

Extract the `symbol` field from the draft JSON. Query the instruments API:

```
GET http://localhost:8000/api/instruments/{symbol}
Header: X-API-Key: <DASHBOARD_API_KEY>
```

Response schema:
```json
{
  "id": 1,
  "symbol": "MNQ",
  "sec_type": "FUT",
  "exchange": "CME",
  "currency": "USD",
  "multiplier": 2.0,
  "min_tick": 0.25,
  "description": "Micro E-mini Nasdaq-100"
}
```

**Auto-fill mapping** (only replace fields that are currently `"_TODO"`):

| Draft field   | API response field |
|---------------|--------------------|
| `exchange`    | `exchange`         |
| `multiplier`  | `multiplier`       |
| `minTick`     | `min_tick`         |
| `currency`    | `currency`         |
| `secType`     | `sec_type`         |

If the symbol is **not found** in the Instruments table (404 response), leave these fields as `_TODO` and note it in the report as "symbol not in instruments DB".

If the `symbol` field itself is `"_TODO"`, skip instrument lookup entirely -- there is nothing to query.

### Tier 2: Sensible Defaults

Apply these defaults for fields that are still `"_TODO"` after Tier 1:

| Field            | Default value | Rationale                                  |
|------------------|---------------|--------------------------------------------|
| `rolling_days`   | `5`           | Standard for futures contracts              |
| `currency`       | `"USD"`       | Most common currency for IBKR instruments   |
| `secType`        | `"FUT"`       | Only if strategy context indicates futures   |
| `trading_hours`  | `null`        | No time restriction by default              |

### Tier 3: Never Auto-Fill (leave as _TODO)

These fields require human judgment or optimization. **Never** auto-fill them:

- Indicator parameters (`timePeriod_1`, lookback periods, etc.) -- these need optimization
- Condition thresholds (RSI levels, multipliers in conditions) -- strategy-specific
- `max_timePeriod` -- depends on final indicator values (todo-fill calculates this automatically)
- `max_shift` -- depends on final condition shifts
- Anything referenced in `_notes` where the author describes testing ranges or uncertainty
- `control_params` fields (start_date, end_date, slippage, commissions) -- backtest-specific

## Steps

### 1. Fetch drafts

For each `strat_code` received, fetch the full draft:

```
GET http://localhost:8000/api/strategies/drafts/{strat_code}
Header: X-API-Key: <DASHBOARD_API_KEY>
```

### 2. Scan for _TODO fields

Recursively scan the draft's `data` JSON for any field with value `"_TODO"`. Build a list of `(path, field_name)` pairs.

### 3. Extract symbol and query instruments

If `data.symbol` is not `"_TODO"`, query the instruments API for that symbol.

### 4. Apply Tier 1 resolutions

For each instrument-resolvable field that is currently `"_TODO"`, replace it with the value from the instruments API response.

### 5. Apply Tier 2 defaults

For fields listed in the Tier 2 table that are still `"_TODO"`, apply the default value.

### 6. Patch each resolved field

For each field that was resolved, call:

```
PATCH http://localhost:8000/api/strategies/drafts/{strat_code}/fill-todo
Header: X-API-Key: <DASHBOARD_API_KEY>
Content-Type: application/json
Body: {"path": "<field_path>", "value": <resolved_value>}
```

### 7. Recount remaining TODOs

After all patches, fetch the draft again to verify the updated `todo_count`.

### 8. Generate summary report

For each draft processed, report:

```
Draft {strat_code} ({strat_name}):
  Filled:
    - exchange -> "CME" (source: instruments)
    - multiplier -> 2 (source: instruments)
    - rolling_days -> 5 (source: default)
  Remaining:
    - ind_list.4 hours[0].params.timePeriod_1 -> needs optimization
    - control_params.start_date -> backtest-specific
  todo_count: 12 -> 7
```

## Return to Orchestrator

```yaml
status: "complete"
drafts_processed: N
todos_resolved: N
todos_remaining: N
per_draft:
  - strat_code: 9001
    strat_name: "RSI_Divergence_SAR_360m"
    filled:
      - field: "exchange"
        value: "CME"
        source: "instruments"
      - field: "multiplier"
        value: 2
        source: "instruments"
      - field: "rolling_days"
        value: 5
        source: "default"
    remaining:
      - field: "ind_list.4 hours[0].params.timePeriod_1"
        reason: "indicator parameter - needs optimization"
    todo_count_before: 12
    todo_count_after: 7
```

## HTTP Calls

Use Bash with `curl` for all HTTP calls to the local API.

## Rules

- Language: English
- Never invent values. Only use data from the instruments API or the defined defaults.
- Numeric values from the API are sent as numbers (int or float as appropriate).
- String values are sent as strings.
- If a PATCH fails, report the error for that field/draft and continue with the rest.
- Do NOT overwrite fields that already have a non-`_TODO` value.
- Do NOT touch Tier 3 fields under any circumstances.
- Group drafts by symbol to minimize redundant instrument API calls (one lookup per unique symbol).

## Error Handling

- API not accessible: report and terminate
- `.env` missing `DASHBOARD_API_KEY`: report that the key is missing and terminate
- Instrument not found (404): leave instrument fields as `_TODO`, note in report, continue
- PATCH error (4xx/5xx): report the affected field and draft, continue with remaining
- Draft has no `symbol` or symbol is `_TODO`: skip instrument lookup, apply only Tier 2 defaults
