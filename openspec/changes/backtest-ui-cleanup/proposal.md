# Proposal: Backtest UI Cleanup

## Intent

The backtest panel's timeframe dropdown is misleading — the engine ignores it entirely and reads `primary_timeframe` from the strategy JSON. Users selecting a timeframe get no effect on execution, only a wrong value stored in the job record. Additionally, the panel lacks a mode selector to distinguish the current "simple" backtest from a future "complete" multi-parameter sweep.

## Scope

### In Scope
- Remove the timeframe `<select>` dropdown from the backtest launch form
- Auto-populate the `timeframe` field sent to the API from the strategy's `primary_timeframe` so job records reflect the real engine timeframe
- Add a mode selector above the form with two buttons: "Simple Backtest" (active, triggers current flow) and "Complete Backtest" (disabled placeholder with "Coming Soon" label)
- Pass `primaryTimeframe` as a new prop to `BacktestPanel` from `DraftViewer`

### Out of Scope
- Backend/DB changes (no migrations, no schema changes)
- Implementing the "Complete Backtest" mode (future phase)
- Fixing historical job records that have incorrect timeframe values
- Changing the job history display (it will now show the correct timeframe for new jobs)

## Approach

**Frontend-only, Approach 3 from exploration (Auto-Read Timeframe from Strategy).**

1. Add `primaryTimeframe?: string` prop to `BacktestPanelProps`
2. In `DraftViewer.tsx`, pass `parsed?.core_parameters?.primary_timeframe` to `BacktestPanel`
3. Remove `TIMEFRAME_OPTIONS` constant and the timeframe `<select>` element
4. Remove the `timeframe` state variable; use the prop value (fallback `"1h"`) when calling `createBacktest`
5. Adjust the form grid from `grid-cols-2 sm:grid-cols-4` to `grid-cols-3` (Symbol, Start Date, End Date)
6. Add a `backtestMode` state (`'simple' | 'complete'`) defaulting to `'simple'`
7. Render two mode buttons above the form. "Complete Backtest" button is visually disabled with a "Coming Soon" tooltip/badge
8. Only show the form when mode is `'simple'` (for now, both show the same form, but the structure is ready)

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/components/strategies/BacktestPanel.tsx` | Modified | Remove timeframe dropdown, add mode selector, new prop |
| `frontend/src/components/strategies/DraftViewer.tsx` | Modified | Pass `primaryTimeframe` prop to BacktestPanel |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `primary_timeframe` missing from parsed data | Low | Fallback to `"1h"` (same as current default) |
| Job history shows inconsistent timeframes (old=user-selected, new=auto) | Low | Cosmetic only; no action needed |

## Rollback Plan

Revert the two changed files to their previous state. No backend or DB changes involved, so rollback is a simple git revert.

## Dependencies

- None. Pure frontend change with no external dependencies.

## Success Criteria

- [ ] Timeframe dropdown is no longer visible in the backtest form
- [ ] New backtest jobs are created with `timeframe` matching the strategy's `primary_timeframe`
- [ ] Mode selector (Simple / Complete) renders above the form
- [ ] "Complete Backtest" button is visually disabled with a "Coming Soon" indicator
- [ ] Existing backtest history continues to display correctly
- [ ] No TypeScript or build errors
