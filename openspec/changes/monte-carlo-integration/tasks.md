# Tasks: Monte Carlo Integration

## Phase 1: Internalize MC Package

### 1.1 Copy `packages/montecarlo/` from ops-worker-v0.1.0 into IRT
Source: `C:/Users/Pablo Nieto/codigos/ops-worker-v0.1.0/packages/montecarlo/`
- [x] Create `packages/montecarlo/` directory structure
- [x] Copy all files preserving directory layout
- [x] Update `.gitignore` if needed for `packages/montecarlo/__pycache__/` (already covered by `packages/**/__pycache__/`)

### 1.2 Verify MC runner can be invoked
- [x] Run `python packages/montecarlo/runner/main_mc.py --help` — confirm it prints usage
- [x] Install any missing dependencies into IRT `.venv` (all imports resolved)

---

## Phase 2: Backend Foundation

### 2.1 Add "montecarlo" to BacktestMode literal
- [x] Update `BacktestMode` in `api/models/schemas/backtest.py` to include `"montecarlo"`

### 2.2 Add n_paths and fit_years to BacktestCreateRequest
- [x] Add `n_paths: Optional[int] = None` to `BacktestCreateRequest`
- [x] Add `fit_years: Optional[int] = None` to `BacktestCreateRequest`

### 2.3 Add n_paths and fit_years columns to BacktestJob model + alembic migration
- [x] Add `n_paths = Column(Integer, nullable=True)` to BacktestJob model
- [x] Add `fit_years = Column(Integer, nullable=True)` to BacktestJob model
- [x] Create alembic migration for the two new columns

### 2.4 Update backtest_service.py to pass n_paths/fit_years through
- [x] Pass `n_paths` and `fit_years` from request to BacktestJob creation
- [x] Include `n_paths` and `fit_years` in job response serialization

---

## Phase 3: Worker MC Mode

### 3.1 Add MC subprocess invocation to worker/executor.py
- [x] Build command: `python packages/montecarlo/runner/main_mc.py --mode path_based --strategy {path} --n-paths {n} --fit-years {y} --metrics-json --save`
- [x] Use same subprocess pattern as backtest-engine invocation
- [x] Parse `###METRICS_JSON_START###` / `###METRICS_JSON_END###` from stdout

### 3.2 Add _decompose_job for "montecarlo" mode in orchestrator.py
- [x] Create single WorkUnit for MC job (no parallelization — MC runner handles its own paths)
- [x] Set longer timeout (e.g., 600s vs 120s for regular backtests)

### 3.3 Handle MC results parsing
- [x] Extract summary JSON from subprocess output
- [x] Post MC results to API as `BacktestResult.metrics` JSONB

### 3.4 Apply timeframe remapping before MC run
- [x] If job timeframe differs from draft's `process_freq`, invoke `bridge.py` remap
- [x] Pass remapped strategy JSON path to MC runner

---

## Phase 4: Frontend MC UI

### 4.1 Add "Monte Carlo" mode button to BacktestPanel
- [x] Third button in mode selector: Simple | Complete | Monte Carlo
- [x] Visual distinction for MC mode (e.g., different icon or color accent)

### 4.2 Add MC config form
- [x] Timeframe dropdown (defaults to draft's `process_freq`, changeable)
- [x] Number of paths input (default: 1000)
- [x] Fit years input (default: 10)
- [x] "Run Monte Carlo" button
- [x] Form only visible when MC mode is selected

### 4.3 Pass mode + MC params in createBacktest request
- [x] Include `mode: "montecarlo"` in request body
- [x] Include `n_paths` and `fit_years` in request body
- [x] Include selected `timeframe` in request body

### 4.4 Update types for MC mode and MC result structure
- [x] Add `"montecarlo"` to BacktestMode type union
- [x] Define `MonteCarloResult` type with percentile bands, summary stats, distribution data
- [x] Extend `BacktestResult` type to include MC fields

---

## Phase 5: Frontend MC Report

### 5.1 Add MC detection in report drawer
- [x] When `mode === "montecarlo"`, render MC-specific content instead of standard report
- [x] Reuse drawer shell (open/close, header, loading state)

### 5.2 Equity curve fan chart
- [x] Recharts `AreaChart` with P5/P25/P50/P75/P95 bands
- [x] Baseline equity curve overlay as solid line
- [x] Color gradient from outer bands (light) to median (dark)

### 5.3 Summary metrics cards
- [x] Median PnL card
- [x] Median Max Drawdown card
- [x] Probability of Loss card
- [x] VaR 95% card

### 5.4 Overfitting assessment card
- [x] "Baseline at Xth percentile" text
- [x] Color indicator: green (>40th), yellow (20-40th), red (<20th)

### 5.5 PnL distribution histogram
- [x] Recharts `BarChart` showing PnL distribution across paths
- [x] Baseline PnL marked with vertical line
- [x] Color zones (loss region red, profit region green)

### 5.6 Percentile table
- [x] All metrics at P5 / P25 / P50 / P75 / P95
- [x] Columns: metric name, P5, P25, P50, P75, P95

### 5.7 Risk metrics table
- [x] Probability of loss
- [x] Probability of 20% / 30% / 50% drawdown
- [x] VaR (95%)
- [x] CVaR (95%)

---

## Phase 5b: Comprehensive MC Visualization Upgrade

### 5b.1 Strategy Scorecard table
- [x] Replace basic percentile table with scorecard: Actual, Rank, P5-P95 columns
- [x] Color-coded rank column (green/amber/red based on percentile position)
- [x] Rows: PnL, Max DD%, Sharpe, Win Rate, Profit Factor, Avg Trade PnL

### 5b.2 Distribution histograms (2x2 grid)
- [x] PnL Distribution (green), Max DD (red), Sharpe (indigo), Avg PnL/Trade (teal)
- [x] Each with median reference line
- [x] Responsive 2-col on large screens, 1-col on small

### 5b.3 Win Rate vs Profit Factor scatter plot
- [x] ScatterChart with each MC path as a dot
- [x] Reference lines at win_rate=50% and profit_factor=1.0

### 5b.4 Enhanced equity fan chart with sampled paths
- [x] Up to 20 sampled paths as very low opacity background lines
- [x] Keep existing P5-P95 percentile bands

### 5b.5 Drawdown cone
- [x] Fan chart for drawdown_curve_percentiles (P5/P25/P50/P75/P95)
- [x] Red/coral color scheme, inverted Y-axis

### 5b.6 Price paths chart
- [x] Historical close as bold red line
- [x] Up to 30 sampled_close_paths as semi-transparent blue lines

### 5b.7 Confidence intervals table
- [x] Show return_95_ci, sharpe_95_ci, drawdown_95_ci
- [x] Simple 2-column layout

---

## Phase 6: Verification

### 6.1 Build check
- [ ] TypeScript build passes (`npm run build` in frontend/)
- [ ] Python syntax check on modified files

### 6.2 Run MC on draft 9009
- [ ] Trigger MC backtest from UI
- [ ] Verify results appear in report drawer with all visualizations

### 6.3 Test MC with timeframe override
- [ ] Select a timeframe different from draft's `process_freq`
- [ ] Verify remapping works and MC completes successfully
