# Worker Complete Mode Specification

## Purpose

Defines the behavior of the worker's "complete" backtest mode. In complete mode, the engine is invoked with `--save --metrics-json` together, producing both metrics output (stdout markers) and a `trades.parquet` file on disk. The worker reads the parquet file, extracts individual trades, and posts them to the API alongside metrics.

## Requirements

### Requirement: Mode-Aware Engine Invocation

The system MUST support two execution modes in the worker:

- **Simple mode** (existing): Engine invoked with `--metrics-json` only. Returns aggregated metrics. No trades file produced.
- **Complete mode** (new): Engine invoked with `--save --metrics-json` together. Returns aggregated metrics AND writes `trades.parquet` to the engine's output directory.

The mode is determined by the `mode` field in the backtest job dict. If `mode` is absent or `"simple"`, the system MUST use simple mode. If `mode` is `"complete"`, the system MUST use complete mode.

#### Scenario: Simple mode invocation (unchanged)

- GIVEN a backtest job with `mode: "simple"` (or `mode` absent)
- WHEN the executor runs the engine
- THEN the engine command includes `--metrics-json` but NOT `--save`
- AND the behavior is identical to the current implementation

#### Scenario: Complete mode invocation

- GIVEN a backtest job with `mode: "complete"`
- WHEN the executor runs the engine
- THEN the engine command includes both `--save` and `--metrics-json`
- AND the `--save` flag causes the engine to write `trades.parquet` to its output directory

### Requirement: Trades Parquet Reading

After the engine completes in complete mode, the system MUST read `trades.parquet` from the engine's output directory using pandas or pyarrow.

The system MUST convert the parquet DataFrame to a list of dicts (one dict per trade).

The system MUST handle the case where `trades.parquet` does not exist (e.g., engine ran but produced no trades) by returning an empty trades list and logging a warning.

#### Scenario: trades.parquet exists with trades

- GIVEN the engine completed successfully in complete mode
- AND `trades.parquet` exists in the output directory with 150 rows
- WHEN the worker reads the parquet file
- THEN it produces a list of 150 trade dicts
- AND each dict contains the trade fields from the parquet columns

#### Scenario: trades.parquet missing (no trades produced)

- GIVEN the engine completed successfully in complete mode
- AND `trades.parquet` does NOT exist in the output directory
- WHEN the worker attempts to read trades
- THEN it returns an empty list `[]`
- AND logs a warning "trades.parquet not found; returning empty trades list"
- AND the job is NOT marked as failed (metrics are still valid)

#### Scenario: trades.parquet is empty

- GIVEN `trades.parquet` exists but contains 0 rows
- WHEN the worker reads the parquet file
- THEN it returns an empty list `[]`

### Requirement: Expected Trade Fields

The system MUST expect up to 24 fields per trade record from the parquet file. The key fields that MUST be present are:

| Field | Type | Description |
|-------|------|-------------|
| `entry_date` | string (datetime) | Trade entry timestamp |
| `exit_date` | string (datetime) | Trade exit timestamp |
| `direction` | string | "long" or "short" |
| `entry_price` | float | Price at entry |
| `exit_price` | float | Price at exit |
| `pnl` | float | Profit/loss for this trade |
| `cumulative_pnl` | float | Running total PnL after this trade |
| `exit_reason` | string | Why the trade was closed (e.g., "sl", "tp", "signal") |
| `bars_held` | int | Number of bars the trade was open |

Additional fields MAY be present (SL price, TP price, commission, slippage, etc.) and MUST be passed through to the API without filtering.

The system MUST convert datetime columns to ISO 8601 string format. The system MUST convert any NaN/Inf float values to `null`.

#### Scenario: All expected fields present

- GIVEN a trades.parquet with columns including all 9 key fields plus additional fields
- WHEN the worker converts to list of dicts
- THEN each dict contains all key fields with correct types
- AND additional fields are preserved as-is

#### Scenario: Datetime conversion

- GIVEN a trades.parquet with `entry_date` as a pandas Timestamp
- WHEN the worker converts to list of dicts
- THEN `entry_date` is an ISO 8601 string (e.g., `"2024-01-15T09:30:00"`)

#### Scenario: NaN values sanitized

- GIVEN a trade record with `pnl: NaN`
- WHEN the worker converts to list of dicts
- THEN `pnl` is `null` in the output dict

### Requirement: Debug Mode

The system MUST support a debug mode that saves the remapped draft JSON to disk for manual inspection before engine execution.

Debug mode is activated when:
- The job dict has `debug: true`, OR
- The `WORKER_DEBUG` environment variable is set to a truthy value (`"1"`, `"true"`, `"yes"`)

When debug mode is active, the system MUST save the remapped JSON to `data/backtests/debug/{strat_code}_{timeframe}_{timestamp}.json`, where `timestamp` is in `YYYYMMDD_HHMMSS` format.

The `data/backtests/debug/` directory MUST be created automatically if it does not exist.

Debug file saving MUST NOT block or fail the backtest execution. If saving fails, the system MUST log a warning and continue.

#### Scenario: Debug enabled via job flag

- GIVEN a backtest job with `debug: true` and `mode: "complete"`
- WHEN the executor prepares the engine invocation
- THEN the remapped JSON is saved to `data/backtests/debug/12345_5m_20260324_143022.json`
- AND the backtest proceeds normally

#### Scenario: Debug enabled via environment variable

- GIVEN `WORKER_DEBUG=1` in the environment
- AND a backtest job with `debug` not set
- WHEN the executor prepares the engine invocation
- THEN the remapped JSON is saved to the debug directory

#### Scenario: Debug save failure does not break backtest

- GIVEN debug mode is active
- AND the `data/backtests/debug/` directory cannot be created (e.g., permissions)
- WHEN the debug save fails
- THEN a warning is logged
- AND the backtest continues normally

### Requirement: Posting Trades to API

In complete mode, the system MUST post the trades list alongside metrics to the API via the existing `_report_success()` function.

The `trades` parameter MUST be the list of trade dicts read from parquet. In simple mode, the `trades` parameter MUST be an empty list `[]` (preserving current behavior).

#### Scenario: Complete mode posts trades

- GIVEN a complete mode backtest that produced 150 trades
- WHEN `_report_success()` is called
- THEN the POST body includes `{"metrics": {...}, "trades": [... 150 trade dicts ...]}`

#### Scenario: Simple mode posts empty trades

- GIVEN a simple mode backtest
- WHEN `_report_success()` is called
- THEN the POST body includes `{"metrics": {...}, "trades": []}`

### Requirement: Bridge Integration in Complete Mode

In complete mode, the executor MUST call `remap_timeframe()` on the draft data before writing the temp JSON file. The remapped data (not the original draft data) MUST be written to the temp file for engine consumption.

In simple mode, the executor MUST NOT call `remap_timeframe()` (preserving current behavior).

#### Scenario: Complete mode applies remapping before engine

- GIVEN a complete mode job with `timeframe: "5m"` and a draft with `process_freq: "1H"`
- WHEN the executor runs
- THEN `remap_timeframe(draft_data, "5m")` is called
- AND `validate_remapped_json()` is called on the result
- AND the remapped JSON is written to the temp file
- AND the engine is invoked with `--save --metrics-json`

#### Scenario: Simple mode skips remapping

- GIVEN a simple mode job
- WHEN the executor runs
- THEN `remap_timeframe()` is NOT called
- AND the original draft data is written to the temp file (current behavior)

### Requirement: Temp File Cleanup

The system MUST clean up the `trades.parquet` file after reading it, in addition to the existing strategy JSON temp file cleanup.

#### Scenario: Parquet file cleaned up after successful read

- GIVEN a complete mode backtest that produced `trades.parquet`
- WHEN the executor finishes (success or failure)
- THEN `trades.parquet` is deleted from the output directory
- AND the strategy JSON temp file is also deleted (existing behavior)
