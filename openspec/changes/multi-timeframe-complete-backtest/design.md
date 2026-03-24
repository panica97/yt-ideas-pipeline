# Design: Multi-Timeframe Complete Backtest

## Technical Approach

Activate the disabled "Complete Backtest" mode by adding timeframe remapping in the bridge layer, `--save` flag support in the engine runner, parquet trade extraction in the executor, and a full-screen report drawer in the frontend. Simple mode remains completely untouched -- all new logic is gated behind `mode == "complete"`.

The approach maps directly to the proposal: bridge remaps the JSON before engine invocation, worker reads `trades.parquet` after engine completes, and the existing `complete_job` API endpoint already accepts a trades array.

## Architecture Decisions

### Decision: Use polars for parquet reading

**Choice**: Use polars (`pl.read_parquet`) to read `trades.parquet`.
**Alternatives considered**: pandas (`pd.read_parquet`), pyarrow direct.
**Rationale**: polars is already a worker dependency (used by the engine's ibkr-core). It is faster than pandas for simple read operations and has zero-copy parquet reading. The worker doesn't need pandas' full API -- just read and convert to dicts.

### Decision: Remap entirely in the bridge layer (no engine changes)

**Choice**: All timeframe remapping happens in `bridge.py` via string/dict manipulation before the JSON is written to disk.
**Alternatives considered**: Adding a `--timeframe` flag to the engine; creating a separate remapping service.
**Rationale**: The engine treats the JSON as a fixed specification. Remapping at the bridge level means zero engine modifications and the remapped JSON can be saved for debugging. This was validated in the spike (11.1).

### Decision: Two-layer validation for remapped JSON

**Choice**: Layer 1 (schema) validates structure (required keys, types). Layer 2 (consistency) validates that all `indCode` suffixes match the target `process_freq` and all `cond` string references resolve to valid indicator names.
**Alternatives considered**: Single-pass validation; relying on engine errors.
**Rationale**: The engine's error messages for malformed JSON are cryptic. Catching issues pre-flight with clear error messages saves debugging time. Two layers keep validation logic modular.

### Decision: Debug save controlled by per-job flag and global env var

**Choice**: `WORKER_DEBUG` env var enables debug globally. Per-job `debug: true` enables it for a single run. Either triggers saving the remapped JSON to `data/backtests/debug/`.
**Alternatives considered**: Always save; log-level based; separate debug endpoint.
**Rationale**: Debug files are only useful during development. Per-job flag lets the frontend toggle it without restarting the worker. Global env var is useful for operators.

### Decision: Simplified trade object for frontend

**Choice**: Map the ~24 parquet columns to 9 fields: `entry_date`, `exit_date`, `side`, `entry_fill_price`, `exit_fill_price`, `pnl`, `exit_reason`, `bars_held`, `cumulative_pnl`.
**Alternatives considered**: Sending all 24 columns; making columns configurable.
**Rationale**: The frontend only needs these 9 fields for the report drawer (equity curve uses `cumulative_pnl`, table shows the rest). Sending fewer fields reduces payload size. Additional columns can be added later if needed.

### Decision: Full-screen drawer (not modal, not page)

**Choice**: New `BacktestReportDrawer.tsx` slides in from the right (~80% viewport width) over the current page.
**Alternatives considered**: Dedicated route/page; modal dialog; inline expansion.
**Rationale**: A drawer preserves context (user can see the draft panel behind it), provides enough space for metrics + chart + table, and follows the established pattern of overlaying detail views. A modal would be too constrained; a full page would lose context.

## Data Flow

### Complete Mode Flow

```
Frontend                  API                    Worker                    Engine
   |                       |                       |                        |
   |-- POST /backtests --> |                       |                        |
   |   mode:"complete"     |                       |                        |
   |   timeframe:"5 min"   |                       |                        |
   |   debug: false        |                       |                        |
   |                       |-- job (pending) ----> |                        |
   |                       |                       |                        |
   |                       |                       |-- export_draft ------> |
   |                       |                       |                        |
   |                       |                       |-- remap_timeframe() -->|
   |                       |                       |   (5m suffix swap)     |
   |                       |                       |                        |
   |                       |                       |-- validate_remap() --> |
   |                       |                       |                        |
   |                       |                       |-- (debug? save JSON)   |
   |                       |                       |                        |
   |                       |                       |-- run_engine --------->|
   |                       |                       |   --save               |
   |                       |                       |   --metrics-json       |
   |                       |                       |                        |
   |                       |                       |<--- metrics JSON ------|
   |                       |                       |<--- trades.parquet ----|
   |                       |                       |                        |
   |                       |                       |-- read parquet ------> |
   |                       |                       |   (polars -> dicts)    |
   |                       |                       |                        |
   |                       |<- POST /results ------|                        |
   |                       |   metrics + trades    |                        |
   |                       |                       |                        |
   |<-- poll result -------|                       |                        |
   |   (metrics + trades)  |                       |                        |
   |                       |                       |                        |
   |-- open drawer ------->|                       |                        |
```

### Simple Mode Flow (unchanged)

```
Frontend --> API --> Worker --> Engine (--metrics-json only) --> metrics --> API --> Frontend
```

### Bridge Remapping Detail

```
Source JSON (process_freq: "1 day")        Target JSON (process_freq: "5 min")
  ind_list:                                  ind_list:
    "1 day":                                   "5 min":
      - indCode: "RSI_14_1D"       -->           - indCode: "RSI_14_5m"
      - indCode: "BB_20_2_1D"      -->           - indCode: "BB_20_2_5m"
  long_conds:                                long_conds:
    - cond: "RSI_14_1D > 50"       -->         - cond: "RSI_14_5m > 50"
  max_shift: [1, "1 day"]          -->       max_shift: [1, "5 min"]
  stop_loss_init.indicator_params:           stop_loss_init.indicator_params:
    tf: "1 day"                    -->         tf: "5 min"
    col: "ATR_20_1D_SL"           -->         col: "ATR_20_5m_SL"
  control_params:                            control_params:
    primary_timeframe: "1 day"     -->         primary_timeframe: "5 min"
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `worker/bridge.py` | Modify | Add `remap_timeframe()`, `validate_remapped_json()`, suffix mapping dict, debug JSON save logic |
| `worker/executor.py` | Modify | Mode-aware execution: check `job.get("mode")`, add `--save` flag for complete mode, read `trades.parquet` via polars, pass trades to `_report_success` |
| `worker/engine.py` | Modify | Accept `save` parameter, add `--save` flag to subprocess command, return parquet path alongside metrics |
| `worker/config.py` | Modify | Add `self.worker_debug: bool` from `WORKER_DEBUG` env var |
| `api/models/schemas/backtest.py` | Modify | Add `mode` (default "simple"), `debug` (default False) to `BacktestCreateRequest`; add `mode` to `BacktestJobResponse` and `BacktestJobSummary` |
| `tools/db/models.py` | Modify | Add `mode` (String, default "simple") and `debug` (Boolean, default False) columns to `BacktestJob` |
| `api/alembic/versions/011_add_backtest_mode_debug.py` | Create | Migration: add `mode` and `debug` columns to `backtest_jobs` |
| `api/services/backtest_service.py` | Modify | Pass `mode` and `debug` through to `BacktestJob` creation |
| `api/routers/backtests.py` | No change | Existing endpoints already forward `body` to service; `BacktestCreateRequest` schema change is sufficient |
| `frontend/src/types/backtest.ts` | Modify | Add `mode` to types, add `BacktestTradeComplete` interface, extend `CreateBacktestParams` with `mode`, `debug` |
| `frontend/src/services/backtests.ts` | Modify | Pass new fields in create request (already handled by type change) |
| `frontend/src/components/strategies/BacktestPanel.tsx` | Modify | Enable complete mode button, add timeframe dropdown, pass `mode`/`timeframe`/`debug` in submit, add "View Report" link for complete jobs |
| `frontend/src/components/strategies/BacktestReportDrawer.tsx` | Create | Full-screen drawer: 8 metric cards, equity curve (recharts), scrollable trades table |

## Interfaces / Contracts

### Bridge: `remap_timeframe()`

```python
# worker/bridge.py

# Canonical suffix mapping -- maps process_freq values to indCode suffixes
TIMEFRAME_SUFFIX: dict[str, str] = {
    "1 min": "1m",
    "5 min": "5m",
    "15 min": "15m",
    "30 min": "30m",
    "1 hour": "1H",
    "4 hours": "4H",
    "8 hours": "8H",
    "1 day": "1D",
}

def remap_timeframe(data: dict, target_tf: str) -> dict:
    """Remap a strategy JSON from its current process_freq to target_tf.

    Parameters
    ----------
    data : dict
        Deep copy of the draft JSON data.
    target_tf : str
        Target timeframe key (e.g. "5 min", "1 hour").

    Returns
    -------
    dict
        Remapped strategy JSON (mutated copy).

    Raises
    ------
    ValueError
        If source or target timeframe is not in TIMEFRAME_SUFFIX.

    Algorithm:
    1. Read source_tf from data["process_freq"]
    2. If source_tf == target_tf, return data unchanged
    3. Resolve old_suffix = TIMEFRAME_SUFFIX[source_tf]  (e.g. "1D")
    4. Resolve new_suffix = TIMEFRAME_SUFFIX[target_tf]  (e.g. "5m")
    5. Remap data["process_freq"] = target_tf
    6. Remap ind_list: rename key source_tf -> target_tf
       For each indicator, replace old_suffix with new_suffix in indCode
    7. Remap long_conds, short_conds, exit_conds:
       For each cond, string-replace old_suffix with new_suffix in "cond" field
    8. Remap max_shift: replace source_tf with target_tf in max_shift[1]
    9. Remap stop_loss_init/take_profit_init:
       - indicator_params.tf: source_tf -> target_tf
       - indicator_params.col: old_suffix -> new_suffix
    10. Remap control_params.primary_timeframe: source_tf -> target_tf
    """
```

### Bridge: `validate_remapped_json()`

```python
def validate_remapped_json(data: dict) -> list[str]:
    """Validate a remapped strategy JSON for correctness.

    Returns
    -------
    list[str]
        List of error messages. Empty list means valid.

    Layer 1 - Schema validation:
    - Required top-level keys exist: process_freq, ind_list, long_conds, short_conds
    - ind_list has exactly one key matching process_freq
    - Each indicator has "indicator" and "params.indCode"

    Layer 2 - Consistency validation:
    - All indCode values end with the expected suffix for process_freq
    - All cond strings reference indCodes that exist in ind_list
    - max_shift[1] matches process_freq
    - stop_loss/take_profit indicator_params.tf matches process_freq
    """
```

### Engine: updated `run_engine()` signature

```python
def run_engine(
    job: dict, strategies_path: str, config: Config, *, save: bool = False
) -> dict:
    """Run the backtest engine subprocess.

    When save=True, adds --save flag. The engine writes trades.parquet
    to the same directory as the strategy JSON file.

    Returns
    -------
    dict
        Parsed metrics dict from engine output.
        When save=True, includes "_parquet_path" key with the path to trades.parquet.
    """
```

### Executor: updated `execute_backtest_job()` flow

```python
def execute_backtest_job(job: dict, config: Config) -> None:
    """Execute a backtest job.

    For complete mode:
    1. Export draft, remap timeframe if needed, validate, debug save
    2. Run engine with --save --metrics-json
    3. Read trades.parquet with polars
    4. Simplify trade records to 9 fields
    5. Report metrics + trades to API
    """
```

### Simplified trade dict (parquet -> API)

```python
# Each trade dict sent to the API
{
    "entry_date": "2024-01-15 09:30:00",   # str
    "exit_date": "2024-01-15 14:00:00",    # str
    "side": "long",                         # str: "long" | "short"
    "entry_fill_price": 17850.25,          # float
    "exit_fill_price": 17920.50,           # float
    "pnl": 351.25,                         # float
    "exit_reason": "tp",                   # str: "tp" | "sl" | "trailing" | "exit_cond" | ...
    "bars_held": 45,                       # int
    "cumulative_pnl": 1205.75,            # float
}
```

### DB Migration: `011_add_backtest_mode_debug.py`

```python
# api/alembic/versions/011_add_backtest_mode_debug.py

def upgrade():
    op.add_column("backtest_jobs", sa.Column("mode", sa.String(20), server_default="simple", nullable=False))
    op.add_column("backtest_jobs", sa.Column("debug", sa.Boolean(), server_default="false", nullable=False))

def downgrade():
    op.drop_column("backtest_jobs", "debug")
    op.drop_column("backtest_jobs", "mode")
```

### Backend schema updates

```python
# api/models/schemas/backtest.py

class BacktestCreateRequest(BaseModel):
    draft_strat_code: int
    symbol: str
    timeframe: str = "1h"
    start_date: str
    end_date: str
    mode: str = "simple"       # NEW: "simple" | "complete"
    debug: bool = False        # NEW: save remapped JSON for inspection
```

### Frontend types

```typescript
// frontend/src/types/backtest.ts

export type BacktestMode = 'simple' | 'complete';

export interface BacktestTradeComplete {
  entry_date: string;
  exit_date: string;
  side: 'long' | 'short';
  entry_fill_price: number;
  exit_fill_price: number;
  pnl: number;
  exit_reason: string;
  bars_held: number;
  cumulative_pnl: number;
}

export interface CreateBacktestParams {
  draft_strat_code: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  mode?: BacktestMode;     // NEW
  debug?: boolean;         // NEW
}

// BacktestJobSummary and BacktestJob: add mode: BacktestMode
```

### Frontend: BacktestReportDrawer component

```typescript
// frontend/src/components/strategies/BacktestReportDrawer.tsx

interface BacktestReportDrawerProps {
  jobId: number;
  open: boolean;
  onClose: () => void;
}

// Structure:
// - Overlay backdrop (click to close)
// - Slide-in panel from right, ~80% viewport width
// - Header: strategy name, timeframe, date range, close button
// - Body (scrollable):
//   - 8 metric cards in 4x2 grid:
//     Return/DD, Win Rate, Max DD %, Sharpe,
//     Total Trades, Profit Factor, Sortino, Avg Win/Loss
//   - Equity curve chart (recharts LineChart, uses cumulative_pnl from trades)
//   - Trades table (scrollable, all 9 fields)
```

### BacktestPanel.tsx changes

```
Existing:                           New:
+---------------------------+      +---------------------------+
| [Simple] [Complete(disabled)]    | [Simple] [Complete]       |
|                           |      |                           |
| Symbol  Start  End        |      | Symbol  Start  End        |
|                           |      | [Timeframe v] (complete)  |
| [Run Backtest]            |      | [Run Backtest]            |
+---------------------------+      +---------------------------+

When mode is "complete":
- Show timeframe dropdown (defaults to draft's primaryTimeframe)
- Available options: 1m, 5m, 15m, 30m, 1H, 4H, 8H, 1D
- Submit sends mode: "complete", timeframe: selected

In job history, for completed "complete" jobs:
- Show "View Report" link instead of inline expand
- Clicking opens BacktestReportDrawer
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `remap_timeframe()` with various source/target TF pairs | pytest: 1D->5m, 1H->15m, same TF (no-op), invalid TF |
| Unit | `validate_remapped_json()` catches missing keys, suffix mismatches, orphan cond refs | pytest: provide intentionally broken JSONs |
| Unit | Trade simplification (24 cols -> 9 fields) | pytest: mock parquet DataFrame, verify output dict |
| Integration | Complete mode end-to-end (bridge -> engine -> parquet -> API) | Manual: run worker against a real draft with `--save` |
| E2E | Frontend complete backtest flow | Manual: select complete mode, pick timeframe, run, verify drawer |

## Migration / Rollout

1. **DB migration** (11.2): Run `alembic upgrade head`. The new `mode` and `debug` columns have server defaults (`"simple"` and `false`), so existing rows are unaffected. Downgrade drops both columns.

2. **Worker deployment** (11.3-11.4): Deploy updated worker. It reads `mode` from the job dict. Existing jobs have `mode="simple"` and follow the unchanged code path.

3. **Frontend deployment** (11.5-11.6): Deploy updated frontend. The "Complete Backtest" button becomes active. Users can start using the new mode immediately.

No feature flags needed -- simple mode is the default, complete mode is opt-in via the UI button.

## Open Questions

- None. The spike (11.1) resolved the key uncertainty (engine `--save` flag behavior). All implementation details are specified.
