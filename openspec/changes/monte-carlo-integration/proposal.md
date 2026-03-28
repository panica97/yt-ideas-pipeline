# Proposal: Monte Carlo Integration

## Intent

The IRT backtest system currently supports Simple and Complete backtest modes. Phase 12.2 adds a third mode — Monte Carlo — that runs path-based simulations to assess strategy robustness, overfitting risk, and tail-risk metrics. This gives the user statistical confidence bounds around backtest results instead of relying on a single historical equity curve.

## Scope

### In Scope

- Copy `montecarlo/` package from ops-worker into `IRT/packages/`
- Add "montecarlo" mode to backend (API schema, DB model, worker executor)
- Worker invokes `main_mc.py` as subprocess (same pattern as backtest-engine)
- Timeframe remapping before MC run (reuse existing `bridge.py`)
- Frontend: third mode button in BacktestPanel with MC config form
- Frontend: MC-specific report content in the existing report drawer
- Report visualizations: fan chart, PnL histogram, percentile table, risk metrics table, overfitting card

### Out of Scope

- Modifying the montecarlo package internals (copied as-is)
- Non-path-based MC modes (bootstrap, noise injection) — future phases
- Portfolio-level MC (single-strategy only for now)
- New DB tables — MC results stored in existing `BacktestResult.metrics` JSONB
- Dockerization of the MC runner (deferred to Phase 14)

## Approach

1. **Internalize MC package** — Copy `montecarlo/` from ops-worker-v0.1.0 into `packages/montecarlo/`, same pattern as Phase 12.1 did for backtest-engine and ibkr-core.

2. **Subprocess pattern preserved** — Worker invokes `python packages/montecarlo/runner/main_mc.py --mode path_based --strategy X --n-paths N --fit-years Y --metrics-json --save`. Output parsed via `###METRICS_JSON_START###` / `###METRICS_JSON_END###` markers, same convention as backtest-engine.

3. **Minimal schema changes** — Add `"montecarlo"` to `BacktestMode` literal, add `n_paths` and `fit_years` optional fields to request/job models. One alembic migration for the two new columns on `BacktestJob`.

4. **Timeframe override** — If the user selects a timeframe different from the draft's `process_freq`, the worker remaps the strategy JSON via the existing `bridge.py` before invoking MC. Same logic already used for Simple/Complete modes.

5. **Report drawer reuse** — The existing report drawer component detects `mode === "montecarlo"` and renders MC-specific content instead of the standard backtest report. Uses recharts `AreaChart` for fan charts and `BarChart` for histograms.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `packages/montecarlo/` (new) | HIGH | Entire MC package copied from ops-worker |
| `api/models/schemas/backtest.py` | LOW | Add "montecarlo" to BacktestMode, add n_paths/fit_years fields |
| `api/models/backtest.py` | LOW | Add n_paths, fit_years columns to BacktestJob |
| `api/services/backtest_service.py` | LOW | Pass n_paths/fit_years through to job creation |
| `worker/executor.py` | MEDIUM | New MC subprocess invocation path |
| `worker/orchestrator.py` | LOW | New `_decompose_job` case for montecarlo mode |
| `frontend/src/components/BacktestPanel.tsx` | MEDIUM | Third mode button, MC config form |
| `frontend/src/components/BacktestReportDrawer.tsx` | HIGH | MC-specific report: fan chart, histogram, tables, cards |
| `frontend/src/types/` | LOW | MC mode and result type definitions |
| `alembic/` | LOW | Migration for n_paths, fit_years columns |

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| MC runner has undocumented deps | LOW | Test `--help` immediately after copy |
| Long MC runtimes (1000 paths) | MEDIUM | Longer timeout in orchestrator decompose; progress not shown (acceptable for v1) |
| Large JSONB payload for 1000-path results | LOW | MC runner outputs summary stats, not raw paths |
| Fan chart rendering performance | LOW | Only 5 percentile bands + baseline = 6 series, trivial for recharts |
