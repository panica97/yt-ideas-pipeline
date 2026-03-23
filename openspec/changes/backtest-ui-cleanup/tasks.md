# Tasks: Backtest UI Cleanup

## Phase 1: Props & Wiring (DraftViewer)

- [x] 1.1 Add `primaryTimeframe?: string` to `BacktestPanelProps` interface in `frontend/src/components/strategies/BacktestPanel.tsx`
- [x] 1.2 In `frontend/src/components/strategies/DraftViewer.tsx`, pass `primaryTimeframe={parsed?.control_params?.primary_timeframe}` to the `<BacktestPanel>` component (line ~214-218)

## Phase 2: Remove Timeframe Dropdown (BacktestPanel)

- [x] 2.1 Remove the `TIMEFRAME_OPTIONS` constant (line 15) from `BacktestPanel.tsx`
- [x] 2.2 Remove the `timeframe` state variable (`useState('1h')`) from the `BacktestPanel` component (line 323)
- [x] 2.3 Remove the timeframe `<select>` block (lines 417-428) from the form grid
- [x] 2.4 Change the form grid from `grid-cols-2 sm:grid-cols-4` to `grid-cols-3` (line 406) since there are now 3 fields: Symbol, Start Date, End Date
- [x] 2.5 Update `handleSubmit` to use `primaryTimeframe ?? '1h'` instead of the removed `timeframe` state when calling `createMutation.mutate()` (line 382)

## Phase 3: Mode Selector (BacktestPanel)

- [x] 3.1 Add `backtestMode` state: `useState<'simple' | 'complete'>('simple')` in the `BacktestPanel` component
- [x] 3.2 Render two mode buttons ("Simple Backtest" and "Complete Backtest") above the form grid, inside the `<div className="space-y-2">` trigger form section. "Simple Backtest" is active/selected, "Complete Backtest" is visually disabled with a "Coming Soon" badge
- [x] 3.3 Style the mode buttons: active button uses `bg-accent text-surface-0`, inactive/disabled button uses `bg-surface-2 text-text-muted cursor-not-allowed opacity-60` with a small "Coming Soon" `<span>` badge

## Phase 4: Verification

- [x] 4.1 Run `npm run build` (or `npx tsc --noEmit`) in `frontend/` to verify zero TypeScript errors
- [ ] 4.2 Visual check: open the dashboard, navigate to a strategy with backtest panel, confirm timeframe dropdown is gone and mode selector renders correctly
- [ ] 4.3 Functional check: run a backtest and verify the job record stores the strategy's `primary_timeframe` (not a hardcoded value) by checking the job history display
