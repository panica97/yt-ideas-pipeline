# Proposal: Multi-Timeframe Complete Backtest

## Intent

The backtest system currently supports only "Simple" mode: locked to the draft's `process_freq`, returning aggregated metrics with no individual trade data. The "Complete Backtest" button added in Phase 10.4 is a disabled placeholder.

This change activates a full "Complete Backtest" mode that:
1. Returns individual trades (enabling equity curve visualization and detailed analysis).
2. Supports running strategies on alternate timeframes via dynamic JSON remapping in the bridge layer.
3. Presents results in a full-screen report drawer with extended metrics, equity curve chart, and scrollable trades table.

This unlocks the core analytical capability users need to evaluate strategy viability before live deployment.

## Scope

### In Scope
- **Backend foundation**: DB migration adding `mode` and `debug` columns to `backtest_jobs`; schema updates for `BacktestCreateRequest`.
- **Bridge timeframe remapping**: `remap_timeframe()` function that remaps `process_freq`, `ind_list` keys, `indCode` suffixes, `cond` strings, and `max_shift` in the draft JSON. Suffix mapping table (1m, 5m, 15m, 30m, 1H, 4H, 8H, 1D).
- **Remapping validation**: Two-layer validation -- schema validation (Layer 1) and consistency checks (Layer 2) via `validate_remapped_json()`.
- **Worker complete mode**: Mode-aware execution using `--save --metrics-json` flags together; read trades from `trades.parquet` written by the engine's `--save` flag. Debug file save to `data/backtests/debug/`.
- **Frontend complete backtest UI**: Enable timeframe dropdown (defaults to draft's `process_freq`), activate "Complete Backtest" button, send `mode: "complete"` + selected `timeframe` + optional `debug` flag.
- **Frontend report drawer**: New `BacktestReportDrawer.tsx` -- full-screen drawer (~80% width, slides from right) with 8 metric cards, equity curve (recharts), and scrollable trades table.

### Out of Scope
- Multi-timeframe selection (running several timeframes at once)
- Side-by-side comparison of backtest results
- Parameter sweep / optimization
- Engine code modifications (all remapping is bridge-side)
- Trade pagination API (deferred; initial implementation loads all trades)

## Approach

### Architecture

The engine already supports a `--save` flag that writes `trades.parquet` to disk. The spike (11.1) confirmed that `--metrics-json` does NOT include individual trades, only `trade_count`. The approach combines both flags:

1. **Complete mode invocation**: Worker calls the engine with `--save --metrics-json` together.
2. **Trade extraction**: After engine completes, worker reads `trades.parquet` using pandas/pyarrow. Each trade has ~24 fields (entry/exit prices, SL/TP, PnL, exit_reason, cumulative_pnl, bars_held, etc.).
3. **Bridge remapping**: Before engine invocation, `remap_timeframe()` transforms the draft JSON to target the selected timeframe. This is pure string/dict manipulation -- no engine changes needed.
4. **Validation**: Remapped JSON passes through `validate_remapped_json()` before engine execution. Two layers: schema structure (required keys exist, types correct) and consistency (indCode suffixes match process_freq, cond references valid indicators).
5. **Debug mode**: When enabled (per-job or global `WORKER_DEBUG` env var), saves the remapped JSON to `data/backtests/debug/{strat_code}_{timeframe}_{timestamp}.json` for inspection.
6. **Results storage**: Trades array stored in `backtest_results` alongside existing metrics. Frontend fetches complete results and renders in the report drawer.

### Sub-phase Execution Order

```
11.1 (Spike - DONE) -> 11.2 (Backend) -> 11.3 (Bridge) -> 11.4 (Worker) -> 11.5 (Frontend UI) -> 11.6 (Report Drawer)
```

Each sub-phase is independently testable and deployable.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `api/alembic/versions/` | New | Migration 008: add `mode` (String, default "simple") and `debug` (Boolean, default false) to `backtest_jobs` |
| `api/models/schemas/backtest.py` | Modified | Add `mode`, `debug`, `timeframe` fields to `BacktestCreateRequest`; add trades array and extended metrics to `BacktestResultResponse` and `BacktestJobResponse` |
| `api/services/backtest_service.py` | Modified | Pass `mode` and `debug` through to job creation |
| `api/routers/backtests.py` | Modified | Accept and forward new fields |
| `worker/bridge.py` | Modified | Add `remap_timeframe()`, suffix mapping table, `validate_remapped_json()` |
| `worker/executor.py` | Modified | Mode-aware execution: simple (unchanged) vs complete (`--save --metrics-json`, parquet reading) |
| `worker/engine.py` | Modified | Support `--save` flag in engine invocation; handle `trades.parquet` output path |
| `worker/config.py` | Modified | Add `WORKER_DEBUG` env var support |
| `frontend/src/components/strategies/BacktestPanel.tsx` | Modified | Enable timeframe dropdown, activate "Complete Backtest" button, pass `mode`/`timeframe`/`debug` |
| `frontend/src/components/strategies/BacktestReportDrawer.tsx` | New | Full-screen drawer with metric cards, equity curve, trades table |
| `frontend/src/types/backtest.ts` | Modified | Add types for complete mode: trades, extended metrics, mode enum |
| `frontend/src/services/backtests.ts` | Modified | Pass `mode`, `timeframe`, `debug` in create request |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `indCode` suffix remapping misses edge cases (e.g., nested references, custom indicators) | Medium | Build comprehensive suffix mapping table; validate remapped JSON before engine execution; debug mode for manual inspection |
| Parquet reading adds dependency (pandas/pyarrow) to worker | Low | Worker already uses pandas; pyarrow is a lightweight read-only dependency; pin version |
| Large trade arrays for long backtests (thousands of trades) | Low | Initial load is acceptable for typical backtests (<5000 trades); defer pagination to future phase if needed |
| Remapped JSON fails engine validation at runtime | Medium | Two-layer validation catches issues before engine invocation; debug mode saves JSON for inspection |
| Frontend drawer performance with large trades tables | Low | Use virtualized scrolling if needed; initial implementation with standard table is fine for <5000 rows |

## Rollback Plan

Each sub-phase is additive and backward-compatible:
1. **DB migration**: Reversible via Alembic downgrade (columns have defaults, existing data unaffected).
2. **Backend/Bridge/Worker**: Simple mode path is untouched. If complete mode breaks, disable the button in frontend (single prop change).
3. **Frontend**: The "Complete Backtest" button can be re-disabled by reverting the `disabled` prop to `true` in `BacktestPanel.tsx`.
4. **Nuclear option**: Revert the git commits for the affected sub-phase. Each sub-phase is a separate commit.

## Dependencies

- Engine `--save` flag must produce `trades.parquet` reliably (confirmed by spike 11.1).
- `pandas` / `pyarrow` available in worker container (already present).
- `recharts` available in frontend (already present from Phase 10.3 equity curve work).

## Success Criteria

- [ ] "Complete Backtest" button is functional (no longer disabled / "Coming Soon")
- [ ] User can select alternate timeframe from dropdown; bridge remaps JSON correctly
- [ ] Complete backtest returns individual trades stored in DB results
- [ ] Full-screen drawer displays 8 extended metric cards (Return/DD, Win Rate, Max DD %, Sharpe, Total Trades, Profit Factor, Sortino, Avg Win/Loss)
- [ ] Equity curve chart renders from cumulative PnL in trades data
- [ ] Scrollable trades table shows all trade fields
- [ ] Simple backtest continues to work unchanged (regression-free)
- [ ] Remapped JSON passes schema + consistency validation before engine runs
- [ ] Debug mode saves remapped JSON to `data/backtests/debug/` for inspection
