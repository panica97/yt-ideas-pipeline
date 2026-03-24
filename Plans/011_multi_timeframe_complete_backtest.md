# Multi-Timeframe Complete Backtest — Phase 11

**Status:** Planned
**Started:** —
**SDD Change:** multi-timeframe-complete-backtest
**Parent Phase:** Phase 11 from Master Plan

---

## Goal

Add a "Complete Backtest" mode that returns individual trades (enabling equity curve visualization) and supports running strategies on alternate timeframes by dynamically remapping the draft JSON. This activates the currently disabled "Complete Backtest" button added in Phase 10.4.

Two backtest modes will coexist in the draft panel:
- **Simple** (existing): Locked to draft's `process_freq`. Metrics-only. Results inline.
- **Complete** (new): Timeframe dropdown (defaults to draft's `process_freq`, changeable). Returns full trades + extended metrics. Results in full-screen drawer.

No engine code modifications needed — timeframe remapping happens entirely in the bridge.

## Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 11.1 | **Spike — verify engine trade output**: Check if `--metrics-json` includes trades in `results['trades']` or if a different engine invocation is needed. Document findings. | spike | — | Planned |
| 11.2 | **Backend foundation**: DB migration adding `mode` (String, default "simple") and `debug` (Boolean, default false) columns to backtest_jobs. Update `BacktestCreateRequest` schema to include `mode` and `debug` fields. Add worker config for `WORKER_DEBUG` env var. | /sdd-new | — | Planned |
| 11.3 | **Bridge timeframe remapping**: Implement `remap_timeframe()` function in bridge.py — remaps `process_freq`, `ind_list` keys, `indCode` suffixes, `cond` strings, and `max_shift`. Implement suffix mapping table. Add `validate_remapped_json()` with schema validation (Layer 1) and consistency checks (Layer 2). | /sdd-new | — | Planned |
| 11.4 | **Worker complete mode**: Mode-aware execution in worker — simple mode unchanged, complete mode captures trades from engine output. Debug file save to `data/backtests/debug/{strat_code}_{timeframe}_{timestamp}.json` when debug is enabled (global or per-job). | /sdd-new | — | Planned |
| 11.5 | **Frontend complete backtest UI**: Enable timeframe dropdown (defaults to draft's `process_freq`), activate "Complete Backtest" button, send `mode: "complete"` + selected `timeframe` + optional `debug` in request. Update types and service layer. | /sdd-new | — | Planned |
| 11.6 | **Frontend report drawer**: New `BacktestReportDrawer.tsx` — full-screen drawer with extended metrics (8 cards: Return/DD, Win Rate, Max DD %, Sharpe, Total Trades, Profit Factor, Sortino, Avg Win/Loss), equity curve chart (recharts), scrollable trades table. Slides in from right, ~80% width. | /sdd-new | — | Planned |

### Dependency Order

```
11.1 (Spike) ──→ 11.2 (Backend) ──→ 11.3 (Bridge) ──→ 11.4 (Worker) ──→ 11.5 (Frontend UI) ──→ 11.6 (Report Drawer)
```

The spike (11.1) comes first because its findings may change how 11.4 (Worker) captures trades. Backend (11.2) is next because bridge and worker depend on the `mode` field. Bridge (11.3) before worker (11.4) because the worker calls bridge functions. Frontend (11.5, 11.6) last since they depend on API contract.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `worker/bridge.py` | Modified | Add `remap_timeframe()`, `validate_remapped_json()`, debug save |
| `worker/executor.py` | Modified | Check job `mode`, ensure trades captured for complete |
| `worker/engine.py` | Modified | May need alternate invocation for complete mode |
| `api/schemas/backtest.py` | Modified | Add `mode` and `debug` fields to BacktestCreateRequest |
| `tools/db/models.py` | Modified | Add `mode` and `debug` columns to BacktestJob |
| `api/alembic/` | New | Migration for `mode` and `debug` columns |
| `frontend/.../BacktestPanel.tsx` | Modified | Complete mode UI: timeframe dropdown, button, View Report link |
| `frontend/.../BacktestReportDrawer.tsx` | New | Full-screen drawer component |
| `frontend/src/types/backtest.ts` | Modified | Update types for mode, extended metrics, trades |
| `frontend/src/services/backtests.ts` | Modified | Pass `mode` in create request |

## Suffix Mapping Table

| Timeframe | Suffix |
|-----------|--------|
| 1 min | 1m |
| 5 min | 5m |
| 15 min | 15m |
| 30 min | 30m |
| 1 hour | 1H |
| 4 hours | 4H |
| 8 hours | 8H |
| 1 day | 1D |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Engine `--metrics-json` may not include trades | Medium | Spike (11.1) verifies this first; use different invocation if needed |
| indCode suffix remapping misses edge cases | Medium | Build comprehensive test cases; use suffix mapping table |
| Large trades array for long backtests | Low | Paginate trades table in drawer; limit to most recent N trades |

## Success Criteria

- [ ] "Complete Backtest" button is functional (no longer "Coming Soon")
- [ ] User can select alternate timeframe — bridge remaps JSON correctly
- [ ] Complete backtest returns individual trades stored in DB
- [ ] Full-screen drawer shows extended metrics, equity curve, and trades table
- [ ] Simple backtest continues to work unchanged
- [ ] Remapped JSON passes schema + consistency validation before engine runs
- [ ] Debug mode saves temp JSON to `data/backtests/debug/` for inspection

## Decisions Log

| Date | Decision | Why | Impact |
|------|----------|-----|--------|
| — | — | — | — |

## SDD Progress

[Updated by SDD phases as they run]

## Notes

- Design document approved 2026-03-24 by Pablo + Claude
- This phase activates the "Complete Backtest" placeholder added in Phase 10.4
- No engine code modifications — remapping is entirely in the bridge layer
- Out of scope: multi-timeframe selection (run several at once), side-by-side comparison, parameter sweep
