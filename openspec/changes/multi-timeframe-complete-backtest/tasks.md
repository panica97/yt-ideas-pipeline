# Tasks: Multi-Timeframe Complete Backtest

## Phase 1: Backend Foundation

- [x] 1.1 Create Alembic migration `api/alembic/versions/011_add_backtest_mode_debug.py` — add `mode` (String(20), server_default="simple", nullable=False) and `debug` (Boolean, server_default="false", nullable=False) columns to `backtest_jobs` table. Include downgrade that drops both columns.
- [x] 1.2 Add `mode` and `debug` columns to the `BacktestJob` SQLAlchemy model in `tools/db/models.py` — `mode = Column(String(20), default="simple")`, `debug = Column(Boolean, default=False)`.
- [x] 1.3 Update `BacktestCreateRequest` in `api/models/schemas/backtest.py` — add `mode: str = "simple"` and `debug: bool = False` fields. Add `BacktestMode` literal type (`"simple" | "complete"`).
- [x] 1.4 Update `BacktestJobResponse` and `BacktestJobSummary` in `api/models/schemas/backtest.py` — add `mode: str` field so the frontend can distinguish job types.
- [x] 1.5 Update `backtest_service.py` — pass `mode` and `debug` from the request body through to `BacktestJob` creation.
- [x] 1.6 Add `worker_debug: bool` to worker config in `worker/config.py` — read from `WORKER_DEBUG` env var (truthy values: `"1"`, `"true"`, `"yes"`).
- [ ] 1.7 Verify: run `alembic upgrade head` against dev DB, confirm columns exist with correct defaults. Check that existing simple backtests still create and return successfully.

## Phase 2: Bridge Remapping & Validation

- [x] 2.1 Add `TIMEFRAME_SUFFIX` dict to `worker/bridge.py` — maps 8 timeframe labels ("1 min", "5 min", "15 min", "30 min", "1 hour", "4 hours", "8 hours", "1 day") to engine suffixes ("1m", "5m", "15m", "30m", "1H", "4H", "8H", "1D").
- [x] 2.2 Implement `remap_timeframe(draft_data: dict, target_timeframe: str) -> dict` in `worker/bridge.py`. Must deep-copy input, remap `process_freq`, `ind_list` keys, `indCode` values, `cond` strings in long_conds/short_conds/exit_conds, `stop_loss_init`/`take_profit_init` indicator_params (tf + col), and `control_params.primary_timeframe`. Only replace source suffix, not other timeframe suffixes. Return unchanged copy if source == target. Raise `ValueError` for unknown timeframes.
- [x] 2.3 Implement `validate_remapped_json(data: dict) -> list[str]` in `worker/bridge.py`. Layer 1 (schema): check `process_freq` is non-empty string matching a known suffix, `ind_list` is non-empty dict, each entry has `indCode`, `max_shift` is positive int. Layer 2 (consistency): all `indCode` suffixes match `process_freq`, all `cond` indicator references exist in `ind_list` keys, stop_loss/take_profit `tf` matches `process_freq`. Return list of error strings (empty = valid).
- [ ] 2.4 Verify: write a quick test script or manual test — remap a sample draft JSON from "1 day" to "5 min", inspect output. Validate a correct remap passes, validate an intentionally broken remap fails with descriptive errors.

## Phase 3: Worker Complete Mode

- [x] 3.1 Update `run_engine()` in `worker/engine.py` — accept `save: bool = False` parameter. When `save=True`, add `--save` flag to the subprocess command. After engine completes, locate `trades.parquet` in the output directory and return its path in the result dict as `_parquet_path`.
- [x] 3.2 Update `execute_backtest_job()` in `worker/executor.py` — check `job.get("mode", "simple")`. For `mode == "complete"`: call `remap_timeframe()` if job timeframe differs from draft process_freq, call `validate_remapped_json()`, pass `save=True` to `run_engine()`.
- [x] 3.3 Add parquet reading to `worker/executor.py` — after engine completes in complete mode, read `trades.parquet` using polars (`pl.read_parquet`). Convert datetime columns to ISO 8601 strings. Replace NaN/Inf with None. Convert to list of dicts.
- [x] 3.4 Implement debug file save in `worker/executor.py` — when `job.get("debug")` is True OR `config.worker_debug` is True, save remapped JSON to `data/backtests/debug/{strat_code}_{timeframe}_{timestamp}.json`. Create directory if missing. Wrap in try/except — log warning on failure, never block the backtest.
- [x] 3.5 Update `_report_success()` call in `worker/executor.py` — pass trades list to the API for complete mode, empty list `[]` for simple mode. Ensure the POST body includes `{"metrics": {...}, "trades": [...]}`.
- [x] 3.6 Add cleanup for `trades.parquet` in executor — delete parquet file after reading, in the same finally block as the existing temp JSON cleanup.
- [ ] 3.7 Verify: run a complete-mode backtest manually against a real draft. Confirm engine produces `trades.parquet`, worker reads it, trades appear in API response. Test debug mode saves JSON file. Test simple mode is unchanged.

## Phase 4: Frontend — Complete Backtest UI

- [x] 4.1 Update `frontend/src/types/backtest.ts` — add `BacktestMode` type (`'simple' | 'complete'`), add `BacktestTradeComplete` interface (9 fields: entry_date, exit_date, side, entry_fill_price, exit_fill_price, pnl, exit_reason, bars_held, cumulative_pnl). Add `mode?: BacktestMode` and `debug?: boolean` to `CreateBacktestParams`. Add `mode: BacktestMode` to `BacktestJobSummary` and `BacktestJob`.
- [x] 4.2 Update `frontend/src/services/backtests.ts` — pass `mode`, `timeframe`, and `debug` fields in the `createBacktest` request body.
- [x] 4.3 Update `frontend/src/components/strategies/BacktestPanel.tsx` — add `mode` state (default "simple"). Enable the "Complete Backtest" button (remove disabled/Coming Soon). When mode is "complete", show a timeframe dropdown (options: 1m, 5m, 15m, 30m, 1H, 4H, 8H, 1D; default to draft's primaryTimeframe). Pass `mode` and selected `timeframe` in the `createBacktest` call.
- [x] 4.4 Add "View Report" button in `BacktestPanel.tsx` — for completed jobs with `mode === "complete"`, show a "View Report" button instead of (or alongside) inline expand. Store `selectedReportJobId` state to control drawer open/close.
- [x] 4.5 Verify: TypeScript build passes (`npx tsc --noEmit`). Visually confirm the mode toggle, timeframe dropdown, and "View Report" button render correctly in the browser.

## Phase 5: Frontend — Report Drawer

- [x] 5.1 Create `frontend/src/components/strategies/BacktestReportDrawer.tsx` — scaffold the drawer component with props `{ jobId: number; open: boolean; onClose: () => void }`. Implement slide-in panel (~80% viewport width, from right), semi-transparent backdrop, close via X button / backdrop click / Escape key. Lock body scroll when open.
- [x] 5.2 Add drawer header — display strategy code, symbol, timeframe, date range, and close (X) button. Fetch job data via existing API if not passed as prop.
- [x] 5.3 Implement extended metrics grid (responsive 5x2 or 4+row layout) — 10 cards: Return/DD, Win Rate, Max DD %, Sharpe, Total Trades, Profit Factor, Sortino, Avg Win/Loss (computed from trades), Max Consecutive Losses (computed from trades), Avg Trade Duration (computed from trades `bars_held`). Color-code favorable (accent) vs unfavorable (danger). Show "N/A" for missing data.
- [x] 5.4 Implement equity curve chart — recharts LineChart using trades' `cumulative_pnl` vs `exit_date`. Sort by exit_date ascending. Format Y axis as currency. Tooltip with date and cumulative PnL on hover. Line color: accent if final PnL positive, danger if negative. Min height 300px. Show "No trades to display" if trades array is empty.
- [x] 5.5 Implement trades table — columns: #, Entry Date, Exit Date, Direction, Entry Price, Exit Price, PnL, Cumulative PnL, Exit Reason, Bars Held. Sticky header, scrollable body. Sortable columns (click to toggle asc/desc, default sort by Entry Date asc). Color-code Direction (accent=Long, danger=Short) and PnL columns (accent=positive, danger=negative).
- [x] 5.6 Wire drawer into `BacktestPanel.tsx` — render `<BacktestReportDrawer>` conditionally based on `selectedReportJobId` state. Pass `jobId`, `open`, and `onClose` props.
- [x] 5.7 Verify: TypeScript build passes. Open drawer from a completed complete-mode job. Confirm metrics cards, equity curve, and trades table render. Test close via X, backdrop, and Escape. Test sorting in the trades table.

## Phase 6: Verification

- [ ] 6.1 Full TypeScript build check — `npx tsc --noEmit` from `frontend/` directory. Zero errors.
- [ ] 6.2 Python import check — verify all modified Python files import cleanly (`python -c "from worker.bridge import remap_timeframe, validate_remapped_json, TIMEFRAME_SUFFIX"`).
- [ ] 6.3 End-to-end test: run a complete backtest on an existing draft with a different timeframe (e.g., draft on 1D, backtest on 5m). Verify bridge remaps correctly, engine runs, trades appear in the report drawer.
- [ ] 6.4 Regression test: run a simple backtest and confirm behavior is unchanged — same metrics, same inline display, no "View Report" link.
- [ ] 6.5 Debug mode test: run a complete backtest with `debug: true`, verify JSON file saved to `data/backtests/debug/` with correct naming convention.
- [ ] 6.6 Validation test: manually break a remapped JSON (e.g., wrong suffix on one indCode) and run through `validate_remapped_json()` — confirm descriptive error is returned and job fails gracefully.
