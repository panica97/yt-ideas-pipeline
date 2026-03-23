## Exploration: Backtest UI Cleanup (Phase 10.4)

### Current State

The backtest UI lives in `frontend/src/components/strategies/BacktestPanel.tsx`. When the panel opens for a backtestable strategy, it immediately shows a launch form with four fields: Symbol, Timeframe (dropdown), Start Date, End Date. Below the form is a "Run Backtest" button and a job history list.

**Timeframe flow analysis:**
- The frontend has a `TIMEFRAME_OPTIONS` array (`['1m','5m','15m','30m','1h','4h','1d']`) and a `<select>` dropdown (lines 15, 418-427).
- The selected timeframe is sent in `CreateBacktestParams.timeframe` to `POST /api/backtests`.
- The backend schema `BacktestCreateRequest` accepts `timeframe` with default `"1h"` and stores it in the `backtest_jobs.timeframe` DB column.
- **However, the worker engine (`worker/engine.py` lines 85-95) does NOT pass timeframe to the engine CLI.** The engine reads `primary_timeframe` directly from the strategy JSON file (exported by `worker/bridge.py`).
- The timeframe in the job record is only used for display in the job history list (`JobItem` shows `job.timeframe`).
- This confirms the selector is misleading: changing it has zero effect on the actual backtest execution.

**No mode selector exists today.** The panel goes straight to the form -- there is no concept of "Simple" vs "Complete" backtest modes.

### Affected Areas

- `frontend/src/components/strategies/BacktestPanel.tsx` -- Remove timeframe selector from form, add mode selector UI
- `frontend/src/types/backtest.ts` -- `CreateBacktestParams.timeframe` is already optional; no change needed
- `api/models/schemas/backtest.py` -- `BacktestCreateRequest.timeframe` has a default; backward-compatible
- `tools/db/models.py` -- `BacktestJob.timeframe` column (`nullable=False`); keep as-is, auto-populate
- `api/services/backtest_service.py` -- Creates `BacktestJob` with `timeframe=body.timeframe`; no engine impact

### Approaches

1. **Minimal Frontend-Only Change** -- Remove the timeframe `<select>` from the form, hardcode `timeframe` to a sensible default (e.g. "1h"). Add a mode selector (two buttons) above the form.
   - Pros: No backend changes, no migration, zero risk to existing data
   - Cons: DB still stores a dummy timeframe value; job history shows misleading timeframe
   - Effort: Low

2. **Frontend Change + Backend Cleanup** -- Same as #1, but also make `BacktestJob.timeframe` nullable in DB and stop sending it.
   - Pros: Cleaner data model
   - Cons: Requires Alembic migration for a cosmetic improvement
   - Effort: Medium

3. **Frontend Change + Auto-Read Timeframe from Strategy** -- Remove selector, auto-populate timeframe from the strategy's `primary_timeframe` field so the job record reflects the real timeframe used by the engine.
   - Pros: Job history shows accurate timeframe, no backend changes or migrations, clean UX
   - Cons: Requires passing `primary_timeframe` to BacktestPanel (minor wiring)
   - Effort: Low-Medium

### Recommendation

**Approach 3 (Frontend Change + Auto-Read Timeframe from Strategy).** This gives the cleanest result:
- Remove the misleading dropdown
- Auto-populate timeframe from `primary_timeframe` in the strategy data so the job record is accurate
- Add the mode selector (Simple/Complete buttons) as a gating step before showing the form
- No backend changes or migrations needed

For the mode selector: two buttons at the top of the panel. "Simple Backtest" enables the current form. "Complete Backtest" shows a disabled placeholder with a "Coming Soon" label. State tracked via a simple `useState`.

### Risks

- **Job history display**: Existing jobs have user-selected timeframe values that may not match the engine's actual timeframe. Pre-existing inaccuracy; no action needed.
- **primary_timeframe availability**: Need to verify the parent component passes enough draft data. The `BacktestSection` component already reads `cp.primary_timeframe`, so the data is available in the draft view context.

### Ready for Proposal

Yes -- scope is clear, approach is low-risk, all affected files identified. Proceed to `/sdd-propose` with Approach 3.
