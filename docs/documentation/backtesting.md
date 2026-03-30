# Backtesting System Documentation

Complete reference for the IRT backtesting system. This document covers the four test modes -- Simple Backtest, Complete Backtest, Monte Carlo Simulation, and Monkey Test -- from API request through engine execution to frontend visualization.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Comparison Table](#2-comparison-table)
3. [Simple Backtest](#3-simple-backtest)
4. [Complete Backtest](#4-complete-backtest)
5. [Monte Carlo Simulation](#5-monte-carlo-simulation)
6. [Monkey Test](#6-monkey-test)
7. [Data Flow Diagrams](#7-data-flow-diagrams)
8. [API Endpoints](#8-api-endpoints)
9. [Configuration](#9-configuration)

---

## 1. Overview

### What is the Backtesting System

The IRT backtesting system evaluates trading strategy drafts against historical market data. It takes a validated strategy draft (with zero pending TODOs), runs it through a high-performance bar-by-bar backtest engine, and produces detailed performance metrics. Four test modes provide increasing levels of statistical rigor:

- **Simple Backtest** -- Quick, single-timeframe performance check. Runs the strategy on one timeframe and returns metrics only (no trade-level data persisted). Best for rapid iteration during strategy development.

- **Complete Backtest** -- Full production backtest with timeframe remapping, trade-level parquet output, and a sortable trade log. Best for final evaluation before live deployment.

- **Monte Carlo Simulation** -- Statistical stress test. Fits a GJR-GARCH model on historical data, generates thousands of synthetic OHLC price paths, runs the strategy on each, and produces distributional statistics. Best for answering "would this strategy survive under different market conditions?"

- **Monkey Test** -- Statistical edge validation. Generates thousands of random-entry simulations on the real OHLC data and compares the strategy's performance against the random distribution. Best for answering "does my strategy have a real edge, or could a monkey picking random entries do just as well?"

### Architecture

The system uses a job queue architecture with three layers:

1. **API Layer** -- FastAPI endpoints create and manage backtest jobs in PostgreSQL.
2. **Worker Layer** -- A multi-slot orchestrator polls for pending jobs, decomposes them into work units, and dispatches them to executor threads.
3. **Engine Layer** -- Subprocess calls to the backtest engine (or Monte Carlo runner) that process the data and return metrics via stdout markers.

### Prerequisites

A draft must meet two conditions before it can be backtested:

- The parent strategy must have `status = "validated"`
- The draft must have `todo_count = 0` (no unresolved TODOs)

If either condition fails, the API returns HTTP 422.

---

## 2. Comparison Table

| Aspect                  | Simple Backtest          | Complete Backtest         | Monte Carlo Simulation        | Monkey Test                          |
|-------------------------|--------------------------|---------------------------|-------------------------------|--------------------------------------|
| **Mode identifier**     | `simple`                 | `complete`                | `montecarlo`                  | `monkey`                             |
| **What it tests**       | Strategy on 1 timeframe  | Strategy on 1 timeframe   | Strategy on N synthetic paths | Strategy vs N random-entry simulations |
| **Timeframe remapping** | No                       | Yes                       | Yes                           | Yes                                  |
| **Engine flags**        | `--metrics-json`         | `--save --metrics-json`   | MC runner CLI                 | Monkey runner CLI                    |
| **Trade-level output**  | No (metrics only)        | Yes (trades.parquet)      | No                            | No (distributions)                   |
| **Output format**       | Single metrics dict      | Metrics + trades list     | Distributional statistics     | p-value + distribution + percentile  |
| **Typical duration**    | 5-30 seconds             | 10-60 seconds             | 5-60 minutes                  | 30s-5 minutes                        |
| **Subprocess timeout**  | 300s (job_timeout)       | 300s (job_timeout)        | 7200s (2 hours)               | 3600s (1 hour)                       |
| **Frontend view**       | Metrics grid + equity    | Metrics + equity + trades | Scorecard + histograms + risk | p-value badge + histogram + comparison table |
| **Use case**            | Quick iteration          | Final evaluation          | Statistical robustness check  | Edge validation                      |

---

## 3. Simple Backtest

### 3.1 What It Does

A Simple Backtest runs the strategy against historical data for a single timeframe and date range. It returns aggregate performance metrics but does not persist individual trades. This is the fastest mode, designed for rapid iteration when tuning strategy parameters.

### 3.2 Parameters

| Parameter          | Type     | Default    | Description                                          |
|--------------------|----------|------------|------------------------------------------------------|
| `draft_strat_code` | `int`    | required   | The draft strategy code to backtest                  |
| `symbol`           | `string` | required   | Trading instrument (e.g., `@ES`, `@NQ`)              |
| `timeframe`        | `string` | `"1h"`     | Primary timeframe for the backtest                   |
| `start_date`       | `string` | required   | Start date in `YYYY-MM-DD` format                    |
| `end_date`         | `string` | required   | End date in `YYYY-MM-DD` format                      |
| `mode`             | `string` | `"simple"` | Must be `"simple"`                                   |
| `debug`            | `bool`   | `false`    | Save remapped JSON for debugging (no effect in simple mode) |

### 3.3 How It Works Internally

#### Executor Flow

1. **Export draft** -- The bridge module fetches the draft JSON from the API and writes it to a temp file in `/tmp/irt-backtests/{strat_code}.json`.
2. **Run engine** -- The executor invokes the backtest engine as a subprocess with `--metrics-json` flag (no `--save`).
3. **Parse output** -- The engine emits metrics between `###METRICS_JSON_START###` and `###METRICS_JSON_END###` markers in stdout. The worker extracts and parses this JSON.
4. **Report results** -- Metrics are posted back to the API. No trades are included.
5. **Cleanup** -- The temp strategy file is deleted.

#### Engine Pipeline Stages

The backtest engine (`BT_Manager`) processes the job through these stages:

```
Stage _01  DataPreprocessor     Load 1-min CSV, resample to strategy timeframes
Stage _02  STRATEGY_BACKTEST    Load strategy rules (entry/exit conditions, indicators)
Stage _03  PriceUtils           Extract scalar/OHLC values, round prices to tick size
Stage _03b WarmupUtils          Compute lookback depth, skip warmup bars
Stage _04  TradingHoursValidator Enforce trading session restrictions (if enabled)
Stage _05  SLTPManager          Configure SL, TP, breakeven, trailing stop levels
Stage _06  PositionManager      Track open positions, manage entries/exits, record trades
Stage _07  ExitSimulator        Simulate intra-bar exits (SL/TP hit detection)
Stage _08  MetricsCalculator    Compute all performance metrics from trade list
Stage _09  PositionSizer        Calculate position size per trade (fixed/RPO/half-Kelly)
Stage _10  BT_Manager           Main loop: bar-by-bar iteration with vectorized signals
Stage _16  VectorizedSignals    Pre-compile entry signals for sparse iteration
```

**Main Loop Logic (Stage _10):**

```
for each bar from warmup_end to total_bars:
    if position is open:
        check exit conditions (SL, TP, num_bars, exit signals, bar end)
    elif entry_mask[bar] is set:
        if all entry conditions met:
            enter position at bar open price
    # else: skip (no position, no signal)
```

The engine uses a two-phase optimization:
- **Phase 1**: Pre-computes indicators on the full time series once (avoids per-bar recalculation).
- **Phase 3**: Compiles vectorized boolean masks for entry signals, allowing the main loop to skip bars where no entry is possible.

### 3.4 Output Metrics

The engine's `MetricsCalculator` produces the following metrics:

**Core Performance:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `total_trades`           | Total number of completed trades                                 |
| `winning_trades`         | Number of trades with positive PnL                               |
| `losing_trades`          | Number of trades with strictly negative PnL                      |
| `breakeven_trades`       | Number of trades with PnL exactly 0                              |
| `win_rate`               | Percentage of winning trades: `(wins / total) * 100`             |
| `total_pnl`             | Sum of all trade PnLs (net of slippage and commissions)          |
| `total_gross_pnl`       | Sum of all trade gross PnLs (before slippage and commissions)    |
| `total_slippage`        | Total slippage cost across all trades                            |
| `total_commission`      | Total commission cost across all trades                          |

**Risk-Adjusted Returns:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `profit_factor`          | `abs(sum(wins) / sum(losses))` -- ratio of gross profit to gross loss |
| `max_drawdown`           | Maximum peak-to-trough decline in cumulative PnL (dollars)       |
| `max_drawdown_pct`       | Max drawdown as percentage of average entry value                |
| `return_drawdown_ratio`  | `abs(total_pnl / max_drawdown)` -- return per unit of risk       |
| `sharpe_ratio`           | Per-trade Sharpe: `(mean_return / std_return) * sqrt(trades/yr)` |
| `sharpe_ratio_daily`     | Daily-return Sharpe: annualized via `sqrt(252)`                  |
| `sortino_ratio`          | Like Sharpe but uses downside deviation only                     |
| `sqn`                    | System Quality Number: `sqrt(N) * mean_pnl / std_pnl`           |

**Trade Statistics:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `avg_win`                | Average PnL of winning trades (dollars)                          |
| `avg_win_pct`            | Average win as percentage of entry value                         |
| `avg_loss`               | Average PnL of losing trades (dollars, negative)                 |
| `avg_loss_pct`           | Average loss as percentage of entry value                        |
| `ppr`                    | Profit Per Risk / avg profit per operation: `total_pnl / N`      |
| `avg_initial_risk`       | Average initial SL distance in dollars                           |
| `rr_percent`             | `(ppr / avg_initial_risk) * 100` -- return per risk %            |

**Streak Analysis:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `max_winning_streak`     | Longest consecutive winning trade sequence                       |
| `avg_winning_streak`     | Average winning streak length                                    |
| `max_losing_streak`      | Longest consecutive losing trade sequence                        |
| `avg_losing_streak`      | Average losing streak length                                     |

**Position Sizing:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `kelly_fraction`         | Kelly Criterion optimal bet fraction                             |
| `half_kelly`             | Half-Kelly (conservative Kelly)                                  |
| `avg_position_size`      | Mean contracts per trade                                         |
| `min_position_size`      | Minimum contracts used in any trade                              |
| `max_position_size`      | Maximum contracts used in any trade                              |
| `total_contracts_traded` | Sum of all position sizes                                        |

**Time Metrics:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `avg_trades_year`        | Annualized trade frequency                                      |
| `avg_bars_active`        | Mean bars held per trade                                         |
| `annualized_return`      | Total PnL divided by years in backtest                           |
| `annualized_return_pct`  | Annualized return as percentage of entry value                   |

**Exit Analysis:**

| Metric                   | Description                                                      |
|--------------------------|------------------------------------------------------------------|
| `sl_exits`               | Trades closed by initial stop loss                               |
| `sl_be_exits`            | Trades closed by breakeven stop                                  |
| `sl_tsl_exits`           | Trades closed by trailing stop loss                              |
| `tp_exits`               | Trades closed by take profit                                     |
| `num_bars_exits`         | Trades closed by maximum bars limit                              |
| `exit_condition_exits`   | Trades closed by strategy exit condition signals                 |
| `backtest_end_exits`     | Trades forced closed at end of backtest period                   |
| `be_triggered_count`     | Number of times breakeven stop was activated                     |
| `tsl_activated_count`    | Number of times trailing stop was activated                      |

**Equity Metrics (when `initial_equity` is set):**

| Metric                      | Description                                         |
|-----------------------------|-----------------------------------------------------|
| `initial_equity`            | Starting account balance                            |
| `final_equity`              | Ending account balance                              |
| `total_return`              | Absolute dollar return                              |
| `total_return_pct`          | Percentage return on initial equity                  |
| `max_drawdown_equity`       | Peak-to-trough drawdown in dollar terms             |
| `max_drawdown_equity_pct`   | Peak-to-trough drawdown as % of initial equity      |

### 3.5 Frontend Visualization

For Simple and Complete backtests, the `BacktestReportDrawer` displays:

1. **Metrics Grid** -- A 5-column card grid showing:
   - Return / DD ratio
   - Win Rate
   - Max DD %
   - Sharpe Ratio
   - Total Trades
   - Profit Factor
   - Sortino Ratio
   - Avg Win / Loss ratio
   - Max Consecutive Losses
   - Avg Duration (bars)

2. **Equity Curve** -- A line chart plotting cumulative PnL over time (derived from trade exit dates). Green when final PnL is positive, red when negative.

3. **Trades Table** (Complete mode only) -- Not shown for Simple backtests since no trades are persisted.

### 3.6 Use Cases

- Quickly testing a new strategy idea before committing to a full backtest
- Iterating on indicator parameters (test multiple variants rapidly)
- Screening strategies: run Simple on a batch to shortlist candidates
- Debugging entry/exit logic (with `verbose` enabled in the engine)

---

## 4. Complete Backtest

### 4.1 What It Does

A Complete Backtest adds two critical features on top of Simple:

1. **Timeframe Remapping** -- The bridge rewrites the strategy's indicator and condition references to use the target timeframe. This allows backtesting a strategy designed for one timeframe (e.g., 4 hours) on a different one (e.g., 1 hour).

2. **Trade-Level Persistence** -- The engine writes all individual trades to a `trades.parquet` file. The worker reads this file (via Polars or Pandas) and posts the simplified trade list alongside the metrics to the API.

### 4.2 Parameters

| Parameter          | Type     | Default      | Description                                          |
|--------------------|----------|--------------|------------------------------------------------------|
| `draft_strat_code` | `int`    | required     | The draft strategy code to backtest                  |
| `symbol`           | `string` | required     | Trading instrument (e.g., `@ES`, `@NQ`)              |
| `timeframe`        | `string` | `"1h"`       | Target timeframe for remapping                       |
| `start_date`       | `string` | required     | Start date in `YYYY-MM-DD` format                    |
| `end_date`         | `string` | required     | End date in `YYYY-MM-DD` format                      |
| `mode`             | `string` | `"complete"` | Must be `"complete"`                                 |
| `debug`            | `bool`   | `false`      | Save remapped JSON to `data/backtests/debug/`        |

### 4.3 How It Differs from Simple

```
Simple:    export draft -> run engine (--metrics-json) -> report metrics
Complete:  export draft -> remap timeframe -> validate -> run engine (--save --metrics-json)
           -> read trades.parquet -> report metrics + trades
```

Key differences:

| Aspect                | Simple                      | Complete                              |
|-----------------------|-----------------------------|---------------------------------------|
| Timeframe remapping   | Not applied                 | Applied (bridge rewrites JSON)        |
| Engine `--save` flag  | Not set                     | Set (writes trades.parquet)           |
| Trade data returned   | Empty list or inline legacy | Full trade list from parquet          |
| Debug JSON saved      | Never                       | When `debug=true` or `WORKER_DEBUG`   |
| Parquet cleanup       | N/A                         | Cleaned up after reading              |

### 4.4 Engine Pipeline Details

The pipeline is identical to Simple (same `BT_Manager.run()` flow), with one difference: the `--save` flag causes `BacktestReporter` to write output files to `logs_backtest/{strat_code}_{NNN}/`:

- `trades.parquet` -- All trades with full details
- Console summary output (human-readable)

The worker then locates the most recently modified `trades.parquet` under the `logs_backtest/` directory tree and reads it.

### 4.5 Trade Data Structure

Each trade in the parquet output is simplified to 9 fields:

| Field              | Type     | Description                           |
|--------------------|----------|---------------------------------------|
| `entry_date`       | ISO 8601 | When the position was opened          |
| `exit_date`        | ISO 8601 | When the position was closed          |
| `side`             | string   | `"long"` or `"short"`                 |
| `entry_fill_price` | float    | Actual entry price (after slippage)   |
| `exit_fill_price`  | float    | Actual exit price (after slippage)    |
| `pnl`              | float    | Net profit/loss for this trade        |
| `exit_reason`      | string   | Why the trade was closed (see below)  |
| `bars_held`        | int      | Number of bars the position was open  |
| `cumulative_pnl`   | float    | Running total PnL after this trade    |

**Exit Reasons:**
- `SL` -- Initial stop loss hit
- `SL_BE` -- Breakeven stop hit
- `SL_TSL` -- Trailing stop loss hit
- `TP` -- Take profit hit
- `num_bars` -- Maximum bars limit reached
- `exit_condition` -- Strategy exit signal triggered
- `backtest_end` -- Forced close at end of backtest period
- `margin_call` -- Position closed due to insufficient margin

### 4.6 Output Metrics

Complete mode returns the same full metrics dictionary as Simple (see Section 3.4), plus the `trades` array described above.

### 4.7 Frontend Visualization

The Complete backtest report drawer shows three sections:

1. **Metrics Grid** -- Same 10 metric cards as Simple mode.

2. **Equity Curve** -- Line chart of cumulative PnL over time, constructed from the trade exit dates and cumulative PnL values.

3. **Trades Table** -- A full sortable table with columns:
   - `#` (row number)
   - Entry Date, Exit Date
   - Direction (Long/Short, color-coded)
   - Entry Price, Exit Price
   - PnL (green for wins, red for losses)
   - Cumulative PnL
   - Exit Reason
   - Bars Held

   The table supports sorting by any column (click header to toggle asc/desc) and scrolls vertically with a sticky header when the trade list exceeds the visible area.

### 4.8 Use Cases

- Final evaluation of a strategy before live deployment
- Analyzing individual trade behavior and patterns
- Reviewing exit reason distribution (e.g., "too many SL exits")
- Sharing backtest results with detailed trade evidence
- Comparing performance across different timeframes via remapping

---

## 5. Monte Carlo Simulation

### 5.1 What It Does

Monte Carlo simulation answers the question: **"If market conditions were statistically similar but different, how would this strategy perform?"**

Instead of testing on a single historical price path (which may have been unusually favorable or unfavorable), the MC mode:

1. Fits a sophisticated statistical model (GJR-GARCH with regime switching) on historical data.
2. Generates thousands of synthetic OHLC price paths that share the same statistical properties as the real market.
3. Runs the full backtest engine on every synthetic path.
4. Aggregates the results into distributional statistics: percentiles, confidence intervals, and risk metrics.

This reveals whether the strategy's historical performance is a reliable indicator of future results, or merely a lucky artifact of the specific price path observed.

### 5.2 Parameters

| Parameter          | Type     | Default        | Description                                              |
|--------------------|----------|----------------|----------------------------------------------------------|
| `draft_strat_code` | `int`    | required       | The draft strategy code to backtest                      |
| `symbol`           | `string` | required       | Trading instrument (e.g., `@ES`, `@NQ`)                  |
| `timeframe`        | `string` | `"1h"`         | Target timeframe for remapping                           |
| `start_date`       | `string` | required       | Start date for the baseline backtest window              |
| `end_date`         | `string` | required       | End date for the baseline backtest window                |
| `mode`             | `string` | `"montecarlo"` | Must be `"montecarlo"`                                   |
| `n_paths`          | `int`    | `1000`         | Number of synthetic price paths to generate and backtest |
| `fit_years`        | `int`   | `10`           | Years of historical data for model fitting (0 = all)     |
| `debug`            | `bool`   | `false`        | Save remapped JSON for debugging                         |

**Derived parameters (computed internally):**

| Parameter    | Computation                                          | Description                        |
|--------------|------------------------------------------------------|------------------------------------|
| `sim_bars`   | `int(calendar_days * 252 / 365)` from date range    | Trading days per synthetic path    |
| `n_periods`  | `sim_bars * bars_per_day` for the base timeframe     | Total base-TF bars per path        |
| `batch_size` | `min(500, max(4, n_paths // 4))`                     | Paths per generation batch         |

### 5.3 The Full MC Workflow Step-by-Step

#### Step 1: Data Loading and Fitting Window

```
Worker receives job -> export draft -> remap timeframe -> validate

MC Runner starts:
  1. Load strategy definitions via ibkr_core StratOBJ
  2. Identify strategy symbol and required timeframes
  3. Compute fit_start_date = now() - fit_years * 365 days
  4. Load ALL 1-min historical data via DataPreprocessor
  5. Resample to all strategy timeframes within fitting window
```

The fitting window (controlled by `fit_years`, default 10) determines how much historical data is used to fit the GARCH model. More data generally produces more stable parameter estimates but may include obsolete market regimes.

#### Step 2: Model Fitting (GJR-GARCH + Regime + OHLC)

The `SyntheticOHLCGenerator.fit()` method fits three interconnected models:

**a) GJR-GARCH(1,1) with Skewed Student-t Innovations**

The core volatility model captures:
- **Volatility clustering** -- Periods of high/low volatility tend to persist
- **Leverage effect** -- Negative returns increase volatility more than positive returns (the "gamma" / asymmetry term)
- **Fat tails** -- Market returns have heavier tails than a normal distribution (modeled via Student-t degrees of freedom)
- **Skewness** -- Returns are asymmetric, typically left-skewed for equities (Hansen's lambda parameter)

Variance equation:
```
sigma^2_t = omega + alpha * eps^2_{t-1} + gamma * eps^2_{t-1} * I(eps_{t-1} < 0) + beta * sigma^2_{t-1}
```

Innovation distribution:
```
z_t ~ SkewedStudentT(nu, lambda)    [Hansen 1994]
```

**Jump diffusion component (Merton-style):**
```
J_t ~ Bernoulli(jump_prob) * Normal(jump_mean, jump_std)
r_t = mu + sigma_t * z_t + J_t
```

Parameters are estimated via Maximum Likelihood Estimation (MLE) with 5 random restarts. Variance targeting pins the unconditional variance to the sample variance for numerical stability.

Optional features:
- AR(1) mean dynamics (if Ljung-Box test detects autocorrelation in returns)
- Kurtosis calibration (adjusts nu post-fit to match empirical kurtosis)

**b) Regime Switching (Gaussian HMM)**

A 2-state (or optionally 3-state) Hidden Markov Model classifies the market into regimes:

| State    | Label      | Characteristics                    |
|----------|------------|------------------------------------|
| State 0  | Normal     | Lower volatility, typical behavior |
| State 1  | Stressed   | Higher volatility, potential crisis |
| State 2  | Calm       | Very low volatility (3-state only) |

The model is fitted via EM algorithm with:
- Dirichlet persistence prior (favors state self-transitions)
- Minimum-duration label smoothing (prevents rapid regime flipping)
- BIC-based automatic state count selection (2 vs 3 states)
- Minimum 500 observations required to activate regime switching

During simulation, the transition matrix governs regime changes, and each regime has its own GARCH parameters for conditional volatility.

**c) OHLC Structure Model**

Since the backtest engine needs OHLC candles (not just returns), a separate model captures intra-bar structure:

- **Gap model** -- Mixture of 2 Normals (base + fat-tailed jump component) for overnight/session gaps
- **Range model** -- Gamma distribution for candle range (high - low), with linear correlation to absolute return
- **Body position** -- Separate Beta distributions for bullish and bearish candles (where the close sits within the range)
- **Wick structure** -- Beta distribution for upper wick proportion

Optionally, separate OHLC parameters are fitted per regime (regime-conditional OHLC).

#### Step 3: Baseline Backtest

Before generating synthetic paths, the MC runner executes a single backtest on the real historical data for the specified date range:

```
Baseline backtest:
  - Uses historical data filtered to [start_date, end_date]
  - Runs BT_Manager with full strategy logic
  - Records: total_pnl, trade_count, avg_trade_pnl, final_equity
  - Serves as the "actual" reference for comparison
```

The baseline duration also determines the per-path timeout for synthetic runs: `max(60s, baseline_duration * 10)`.

#### Step 4: Synthetic Path Generation

The generator produces synthetic OHLC data in batches:

```
For each batch (batch_size paths):
  For each path:
    1. Sample initial regime from steady-state distribution
    2. For each bar (n_periods total):
       a. Sample regime transition via Markov chain
       b. Generate GARCH volatility (sigma_t) conditioned on regime
       c. Apply intraday vol seasonality (if sub-daily timeframe)
       d. Sample innovation z_t from SkewedStudentT(nu, lambda)
       e. Sample jump J_t from jump diffusion process
       f. Compute log-return: r_t = mu + sigma_t * z_t + J_t
       g. Convert return to close price: C_t = C_{t-1} * exp(r_t)
       h. Generate OHLC structure using OHLCStructureModel:
          - Sample gap, range, body position, wick
          - Construct O, H, L from C and structure params
       i. Assign synthetic volume (constant default)
    3. Assemble base-timeframe DataFrame (date, O, H, L, C, V)
    4. Aggregate to all strategy timeframes
  Yield batch of n multi-timeframe DataFrames
```

Key properties of generated paths:
- Same starting price as historical data
- Same statistical distribution of returns (fat tails, skewness, volatility clustering)
- Same regime dynamics (calm/stressed market proportions)
- Same intra-bar candle structure (range, body position, wicks)
- Different specific price sequence (different random seed per path)

#### Step 5: Parallel Backtesting of Synthetic Paths

Each synthetic path is backtested using true multiprocessing (not threading):

```
ProcessPoolExecutor (cpu_count - 1 workers):
  For each path in batch:
    Submit to worker process:
      1. _init_worker() -- import BT_Manager (once per process)
      2. _run_path_worker() -- create BT_Manager with preloaded_data=synthetic_path
      3. Run backtest: BT_Manager.run()
      4. Return: { status, trades, metrics, equity_history, total_pnl }
```

Worker processes are initialized once (BT_Manager import cached), then reused across all paths. Each path backtest uses the exact same strategy logic as the baseline, but with synthetic price data substituted for historical data.

Failed paths (errors, timeouts, 0 trades) are counted but excluded from statistics.

#### Step 6: Aggregation and Statistics

The `MonteCarloAggregator` collects results from all successful paths and computes:

**Per-metric percentile distributions:**

For each key metric (total_pnl, max_drawdown_pct, sharpe_ratio, win_rate, profit_factor, total_trades, avg_trade_pnl, sortino_ratio, return_drawdown_ratio), the aggregator computes:

| Statistic   | Description                                     |
|-------------|--------------------------------------------------|
| `mean`      | Arithmetic mean across all paths                 |
| `std`       | Standard deviation across paths                  |
| `median`    | 50th percentile                                  |
| `p5`        | 5th percentile (worst-case boundary)             |
| `p10`       | 10th percentile                                  |
| `p25`       | 25th percentile                                  |
| `p75`       | 75th percentile                                  |
| `p90`       | 90th percentile                                  |
| `p95`       | 95th percentile (best-case boundary)             |
| `min`       | Worst path                                       |
| `max`       | Best path                                        |
| `skewness`  | Distribution skew                                |
| `kurtosis`  | Distribution tail weight                         |

**Risk metrics:**

| Metric               | Description                                            |
|-----------------------|--------------------------------------------------------|
| `prob_negative_return`| Fraction of paths with total_pnl < 0                  |
| `var_95`              | Value at Risk (5th percentile of PnL distribution)    |
| `cvar_95`             | Conditional VaR (mean of worst 5% of paths)           |
| `prob_dd_10`          | Probability of max drawdown exceeding 10%             |
| `prob_dd_20`          | Probability of max drawdown exceeding 20%             |
| `prob_dd_30`          | Probability of max drawdown exceeding 30%             |
| `prob_dd_50`          | Probability of max drawdown exceeding 50%             |
| `ulcer_index`         | Mean Ulcer Index across all equity curves              |

**Confidence intervals (10,000 bootstrap samples):**

| Interval          | Description                                         |
|-------------------|-----------------------------------------------------|
| `return_95_ci`    | 95% CI for the mean total PnL                       |
| `sharpe_95_ci`    | 95% CI for the mean Sharpe Ratio                    |
| `drawdown_95_ci`  | 95% CI for the mean max drawdown %                  |

**Equity curve percentiles:**

Percentile bands (P5, P25, P50, P75, P95) computed across all equity curves at each time step. Used for the drawdown cone visualization.

**Sampled paths:**

Up to 50 randomly sampled equity curves and 30 sampled close price paths, provided for fan chart overlay visualization.

#### Step 7: Comparison to Baseline

The aggregator determines where the baseline backtest falls within the Monte Carlo distribution:

| Comparison Metric    | Calculation                                                   |
|----------------------|---------------------------------------------------------------|
| `return_percentile`  | % of MC paths with total_pnl <= baseline total_pnl            |
| `drawdown_percentile`| % of MC paths with max_drawdown <= baseline max_drawdown      |
| `sharpe_percentile`  | % of MC paths with sharpe <= baseline sharpe                  |

**Assessment logic:**

| Return Percentile | Assessment | Overfitting Risk | Interpretation                              |
|-------------------|------------|------------------|---------------------------------------------|
| > 90%             | `lucky`    | `high`           | Baseline outperformed 90%+ of synthetic paths. Results may be overfit to the specific historical path. |
| 10% - 90%         | `typical`  | `low` to `medium`| Baseline performance is consistent with what the strategy would achieve under similar conditions. |
| < 10%             | `unlucky`  | `low`            | Baseline underperformed most synthetic paths. The strategy may be more robust than historical results suggest. |

### 5.4 Output Metrics Structure

The MC mode returns a `statistics` dictionary with a nested structure. The top-level keys are:

```json
{
  "n_paths": 1000,
  "n_completed": 950,
  "n_failed": 50,
  "failure_rate": 0.05,

  "total_pnl":            { "mean", "std", "median", "p5"..."p95", "min", "max", "skewness", "kurtosis" },
  "max_drawdown_pct":     { ... same structure ... },
  "sharpe_ratio":         { ... },
  "win_rate":             { ... },
  "profit_factor":        { ... },
  "total_trades":         { ... },
  "avg_trade_pnl":        { ... },
  "sortino_ratio":        { ... },
  "return_drawdown_ratio":{ ... },

  "raw_metrics": {
    "total_pnl": [array of per-path values],
    "max_drawdown_pct": [...],
    "sharpe_ratio": [...],
    "win_rate": [...],
    "profit_factor": [...],
    "total_trades": [...],
    "avg_trade_pnl": [...],
    "return_drawdown_ratio": [...]
  },

  "risk_metrics": {
    "prob_negative_return": 0.12,
    "var_95": -5000.0,
    "cvar_95": -8000.0,
    "prob_dd_10": 0.45,
    "prob_dd_20": 0.15,
    "prob_dd_30": 0.03,
    "prob_dd_50": 0.001,
    "ulcer_index": 0.08
  },

  "confidence_intervals": {
    "return_95_ci": [-1200.0, 4500.0],
    "sharpe_95_ci": [-0.5, 1.2],
    "drawdown_95_ci": [8.0, 22.0]
  },

  "equity_curve_percentiles": {
    "p5":  [array of equity values at each time step],
    "p25": [...],
    "p50": [...],
    "p75": [...],
    "p95": [...]
  },

  "drawdown_curve_percentiles": { "p5": [...], ... "p95": [...] },
  "sampled_paths": [[path1_equity], [path2_equity], ...],
  "sampled_close_paths": [[path1_close], [path2_close], ...],
  "historical_close": [array of historical close prices]
}
```

### 5.5 Frontend Visualization

When `mode === "montecarlo"`, the report drawer renders a completely different view with the `MonteCarloReport` component. The sections displayed are:

**1. Simulation Summary Banner**

A colored banner (green or amber based on failure rate) showing:
- Paths Requested
- Paths Completed
- Failure Rate (as percentage)

**2. Key Stats Cards (2x2 grid)**

| Card               | Source                            | Color Logic                       |
|--------------------|-----------------------------------|-----------------------------------|
| Median Ret/DD      | Return/DD ratio median            | Green if >= 1, red if < 1         |
| Median Max DD      | max_drawdown_pct median           | Always red                        |
| Probability of Loss| risk_metrics.prob_negative_return  | Green < 30%, amber 30-50%, red > 50% |
| VaR 95%            | risk_metrics.var_95               | Always red (worst-case metric)    |

**3. Strategy Scorecard Table**

A table comparing the baseline performance against the MC distribution for three key metrics:

| Column    | Description                                        |
|-----------|----------------------------------------------------|
| Metric    | Return/DD, Max DD %, Sharpe                        |
| Actual    | Baseline (median) value                            |
| Z-Score   | Standard deviations from mean: `(actual - mean) / std` |
| Rank      | Percentile rank within the MC distribution         |
| P5 - P95  | Distribution percentile values                     |

Color coding:
- Z-Score: green if |z| <= 1, red if |z| > 1
- Rank: green if effective percentile >= 60, amber >= 40, red < 40

**4. Distribution Histograms (2-column grid)**

Two histograms with 20 bins each:

- **Return/DD Distribution** -- Green bars. Shows how the return-to-drawdown ratio is distributed across all MC paths.
- **Max Drawdown Distribution** -- Red bars. Shows the distribution of maximum drawdown percentages.

Each histogram includes vertical reference lines:
- **P5** -- Red dashed line (5th percentile)
- **P50** -- Amber dashed line (50th percentile / median)
- **P95** -- Green dashed line (95th percentile)
- **Actual** -- Blue solid line (baseline value)

**5. Risk Metrics Table**

A two-column table displaying:
- Probability of negative return
- Probability of >10% drawdown
- Probability of >20% drawdown
- Probability of >30% drawdown
- Probability of >50% drawdown
- VaR 95% (in dollars)
- CVaR 95% (in dollars)

Color coding: green for low-risk values, amber for moderate, red for high-risk.

**6. Confidence Intervals Table**

Displays the 95% bootstrap confidence intervals for:
- Return 95% CI (dollar range)
- Sharpe 95% CI (ratio range)
- Max DD 95% CI (percentage range)

### 5.6 Interpreting Results

**For traders evaluating a strategy:**

| What to Look At          | Good Sign                              | Warning Sign                          |
|--------------------------|----------------------------------------|---------------------------------------|
| Probability of Loss      | < 20% (strategy is robust)             | > 50% (strategy may be unreliable)    |
| Median Ret/DD            | > 1.0 (returns exceed drawdown)        | < 0.5 (poor risk-adjusted returns)    |
| VaR 95%                  | Small relative to equity               | Large loss could be catastrophic      |
| CVaR 95%                 | Not much worse than VaR                | Much worse = fat tail risk            |
| Sharpe P5                | > 0 (profitable even in worst 5%)      | < 0 (can easily become unprofitable)  |
| Prob DD > 20%            | < 10%                                  | > 30% (likely to face deep drawdowns) |
| Failure Rate             | < 5%                                   | > 20% (model or strategy issues)      |
| Return Percentile (comp) | 10-90% (baseline is typical)           | > 90% (possible overfitting)          |

**Interpreting the Z-Score:**

The Z-score indicates how many standard deviations the baseline result is from the MC mean. A large |Z| suggests the historical result is unusual relative to what the model predicts:

- |Z| < 1.0 -- Baseline is within one standard deviation. Normal, expected behavior.
- 1.0 < |Z| < 2.0 -- Baseline is somewhat unusual. Worth investigating.
- |Z| > 2.0 -- Baseline is statistically unusual. Possible overfitting to the specific historical path.

### 5.7 Use Cases

- **Overfitting detection** -- If the baseline return ranks above P90, the strategy may be overfit to the specific historical data.
- **Risk budgeting** -- Use the drawdown distribution to set appropriate position sizes and stop levels.
- **Strategy comparison** -- Run MC on multiple strategies and compare their probability-of-loss and Sharpe distributions.
- **Confidence in deployment** -- A strategy with a narrow, positive PnL distribution is more reliable than one with high variance.
- **Tail risk assessment** -- CVaR and drawdown probabilities quantify worst-case scenarios beyond simple max drawdown.

---

## 6. Monkey Test

### 6.1 What It Does

The Monkey Test answers: **"Could a monkey generating random trades have achieved equal or better results than my strategy?"** It's based on Random Benchmark Testing (Woodriff / Hedge Fund Market Wizards) and distribution of metrics under the null hypothesis (Bailey, López de Prado 2014).

Instead of testing on synthetic price paths (like Monte Carlo), the Monkey Test keeps real prices but randomizes entries. It generates N simulations of random trades that match the strategy's structural parameters (number of trades, holding periods, direction) but with random entry timing. If the strategy can't beat these random simulations, it has no demonstrable edge.

### 6.2 Parameters

| Parameter          | Type     | Default    | Description                                          |
|--------------------|----------|------------|------------------------------------------------------|
| `draft_strat_code` | `int`    | required   | The draft strategy code to backtest                  |
| `symbol`           | `string` | required   | Trading instrument                                   |
| `timeframe`        | `string` | `"1h"`     | Target timeframe for remapping                       |
| `start_date`       | `string` | required   | Start date for the backtest window                   |
| `end_date`         | `string` | required   | End date for the backtest window                     |
| `mode`             | `string` | `"monkey"` | Must be `"monkey"`                                   |
| `n_simulations`    | `int`    | `1000`     | Number of random simulations (1000/2500/5000)        |
| `monkey_mode`      | `string` | `"A"`      | `"A"` (empirical distribution) or `"B"` (always max bars) |
| `debug`            | `bool`   | `false`    | Save remapped JSON for debugging                     |

### 6.3 The Monkey Definition

The monkey is a synthetic strategy structurally identical to the real strategy in every way except signal logic.

**Parameters inherited from real strategy:**

| Parameter              | Description                            | Why preserved                        |
|------------------------|----------------------------------------|--------------------------------------|
| `n_trades`             | Total number of trades                 | Fair comparison -- same market exposure |
| `direction`            | Long or Short                          | Same directional constraint          |
| `max_bars`             | Maximum bars a trade can last          | Same temporal horizon                |
| `holding_distribution` | Empirical distribution of trade durations | Preserves temporal signature      |
| `period`               | Date range of original backtest        | Same market conditions               |

**Holding period modes:**

- **Mode A (Empirical Distribution)** -- For each monkey trade, duration is sampled with replacement from the real distribution of trade durations. This is the primary/fairest mode: it tests only whether entry timing adds value, keeping everything else equal.

- **Mode B (Always Max Bars)** -- All monkey trades last exactly `max_bars` bars. This is the hardest benchmark: if the strategy beats this mode, the exit logic also adds value beyond simply holding to maximum. Useful for isolating exit signal contribution.

### 6.4 Random Entry Generation

```
1. Load full OHLC bar universe for the period (at selected timeframe)
2. Exclude last max_bars bars (so all trades can complete)
3. For each simulation:
   a. Shuffle entry candidates
   b. Pick entries one by one, enforcing no overlap
      (one open trade at a time, matching real strategy behavior)
   c. Assign holding period per Mode A or B
   d. If overlap prevents placing all n_trades,
      place maximum feasible and emit warning
4. Compute P&L per trade: (close[exit] - close[entry]) * direction
5. Build equity curve, compute metrics
```

### 6.5 The Full Workflow Step-by-Step

```
Worker receives job -> export draft -> remap timeframe -> validate

Monkey Runner starts:
  1. Load strategy via ibkr_core StratOBJ
  2. Run BT_Manager once ("complete" mode) to get real trades
  3. Extract from trades: n_trades, holding_distribution, max_bars, direction
  4. Load OHLC close prices from bt.full_data
  5. For each simulation i = 1..N:
     a. Generate random entries (section 6.4)
     b. Compute per-trade P&L from close prices
     c. Build equity curve
     d. Calculate metrics: Net Profit, Max Drawdown, Return/DD, Win Rate, Profit Factor
     e. Store result
     f. Report progress every 100 simulations
  6. Aggregate results:
     - Distribution of each metric across N simulations
     - Percentile of real strategy within distribution
     - p-value = proportion of monkeys >= real strategy's Return/DD
     - Histogram bins for visualization
  7. Output JSON via ###METRICS_JSON_START### marker
```

### 6.6 Metrics and Output

**Primary metric: Return/Drawdown** (Net Profit / Max Drawdown)

**Per-simulation metrics:**

| Metric        | Formula                                          |
|---------------|--------------------------------------------------|
| Net Profit    | Sum of all trade P&Ls                            |
| Max Drawdown  | Maximum peak-to-trough of equity curve           |
| Return/DD     | Net Profit / Max Drawdown                        |
| Win Rate      | Count(PnL > 0) / Total trades                   |
| Profit Factor | Sum(winning trades) / abs(Sum(losing trades))    |

**Aggregated output:**

| Field                | Description                                      |
|----------------------|--------------------------------------------------|
| `mode`               | "A" or "B"                                       |
| `n_simulations`      | Number of simulations run                        |
| `n_trades_requested` | Original trade count from strategy               |
| `n_trades_actual`    | Actual trades placed (may be reduced)            |
| `real_strategy`      | Real strategy metrics (5 values)                 |
| `distribution`       | Array of N values per metric                     |
| `percentile`         | % of random sims the strategy beats              |
| `p_value`            | Proportion of sims with Return/DD >= real        |
| `warnings`           | List of warning messages                         |

### 6.7 Interpreting Results

**p-value thresholds:**

| p-value     | Interpretation                                                  |
|-------------|-----------------------------------------------------------------|
| < 0.01      | Very strong edge -- fewer than 1% of monkeys beat you           |
| 0.01 -- 0.05 | Solid edge -- beats 95-99% of random simulations              |
| 0.05 -- 0.10 | Weak edge -- grey zone, requires further analysis             |
| > 0.10      | No evidence of edge -- strategy does not statistically beat random |

**Caveats even if the test passes:**
- Temporal overfitting: edge existed in that period but not others (complement with walk-forward)
- Selection bias: if many strategies tested, some pass by luck (apply Bonferroni correction)
- Market regime: random strategies also struggle in volatile environments

**Practical rule:** A strategy should pass the Monkey Test in at least two distinct time periods before being considered a serious candidate.

### 6.8 Frontend Visualization

The Monkey Test report (`MonkeyTestReport.tsx`) renders inside `BacktestReportDrawer` when mode is `monkey`:

- **P-value Badge** -- Large color-coded badge (green/emerald/amber/red per thresholds) with p-value number, interpretation label, and percentile text
- **Return/DD Histogram** -- Recharts BarChart showing distribution of Return/DD across all simulations. Bars below real strategy value are gray; bars at/above are highlighted. Green ReferenceLine marks the real strategy's value.
- **Summary Table** -- Side-by-side comparison: Real Strategy vs Monkey Median (P50) for all 5 metrics, with rank (percentile) per metric
- **Simulation Info** -- Mode description, simulation count, trades requested/actual
- **Warnings** -- Yellow alert box if n_trades was reduced due to overlap constraints

---

## 7. Data Flow Diagrams

### 7.1 Simple Backtest

```
  User (Frontend)                  API                    Worker                  Engine
  ===============                  ===                    ======                  ======

  POST /api/backtests              Create job
  { mode: "simple",  ---------->  (status: pending)
    strat_code, symbol,            Store in DB
    timeframe, dates }                 |
                                       |
                              Worker polls /pending
                                       |
                                  Claim job  <------  GET /pending
                                (status: running)     PATCH /{id}/claim
                                       |
                                       v
                                  export_draft()
                                  Write temp JSON
                                       |
                                       v
                                  subprocess.run()  -------->  BT_Manager.run()
                                  [--metrics-json]             |
                                       |                       |  1. Load CSV data
                                       |                       |  2. Resample to TFs
                                       |                       |  3. Pre-compute indicators
                                       |                       |  4. Vectorize entry signals
                                       |                       |  5. Bar-by-bar loop
                                       |                       |  6. Calculate metrics
                                       |                       |
                                  Parse stdout  <-----------  ###METRICS_JSON###
                                  markers                     { metrics dict }
                                       |
                                       v
                                  POST /{id}/results
                                  { metrics, trades: [] }
                                       |
                                  (status: completed)
                                       |
  GET /api/backtests/{id}  <----  Return job + result
  Display metrics grid
```

### 7.2 Complete Backtest

```
  User (Frontend)                  API                    Worker                  Engine
  ===============                  ===                    ======                  ======

  POST /api/backtests              Create job
  { mode: "complete", --------->  (status: pending)
    strat_code, symbol,                |
    timeframe, dates }                 |
                              Worker polls /pending
                                       |
                                  Claim job
                                (status: running)
                                       |
                                       v
                                  export_draft()
                                  Write temp JSON
                                       |
                                       v
                                  remap_timeframe()
                                  Rewrite indicator refs
                                  to target timeframe
                                       |
                                       v
                                  validate_remapped_json()
                                  Check for errors
                                       |
                                  (optional) save debug JSON
                                       |
                                       v
                                  subprocess.run()  -------->  BT_Manager.run()
                                  [--save --metrics-json]      |
                                       |                       |  Same pipeline as Simple
                                       |                       |  + writes trades.parquet
                                       |                       |
                                  Parse stdout  <-----------  ###METRICS_JSON###
                                  markers                     + trades.parquet file
                                       |
                                       v
                                  _find_parquet()
                                  _read_parquet_trades()
                                  Simplify to 9 fields
                                       |
                                       v
                                  POST /{id}/results
                                  { metrics, trades: [...] }
                                       |
                                  Cleanup parquet file
                                  (status: completed)
                                       |
  GET /api/backtests/{id}  <----  Return job + result
  Display metrics + equity
  + trades table
```

### 7.3 Monte Carlo Simulation

```
  User (Frontend)                  API                    Worker               MC Runner
  ===============                  ===                    ======               =========

  POST /api/backtests              Create job
  { mode: "montecarlo", ------->  (status: pending)
    strat_code, symbol,                |
    timeframe, dates,                  |
    n_paths, fit_years }               |
                              Worker polls /pending
                                       |
                                  Claim job
                                (status: running)
                                       |
                                       v
                                  export_draft()
                                  remap_timeframe()
                                  validate()
                                       |
                                       v
                                  run_montecarlo()  -------->  main_mc.py
                                  subprocess (2h timeout)      |
                                       |                       |
                                       |              1. Load StratOBJ + hist data
                                       |              2. Fit GARCH + Regime + OHLC
                                       |              3. Run baseline backtest
                                       |              4. Generate synthetic paths
                                       |                 (batches of ~250)
                                       |              5. Parallel backtest each path
                                       |                 (ProcessPoolExecutor)
                                       |              6. Aggregate statistics
                                       |                 (percentiles, risk, CI)
                                       |              7. Compare baseline vs MC
                                       |                       |
                                  Parse stdout  <-----------  ###METRICS_JSON###
                                  markers                     { statistics dict }
                                       |
                                       v
                                  POST /{id}/results
                                  { metrics: stats, trades: [] }
                                       |
                                  (status: completed)
                                       |
  GET /api/backtests/{id}  <----  Return job + result
  Display MC report:
  - Simulation summary
  - Key stats cards
  - Strategy scorecard
  - Distribution histograms
  - Risk metrics table
  - Confidence intervals
```

### 7.4 Monkey Test

```
  User (Frontend)                  API                    Worker                  Monkey Runner
  ===============                  ===                    ======                  =============

  POST /api/backtests              Create job
  { mode: "monkey",  ---------->  (status: pending)
    strat_code, symbol,            Store in DB
    timeframe, dates,                  |
    n_simulations, monkey_mode }       |
                              Worker polls /pending
                                       |
                                  Claim job  <------  GET /pending
                                (status: running)     PATCH /{id}/claim
                                       |
                                       v
                                  export_draft()
                                  remap_timeframe()
                                  validate_remapped_json()
                                       |
                                       v
                                  subprocess.run()  -------->  1. Load strategy (StratOBJ)
                                  monkey_engine.py             2. Run BT_Manager (complete)
                                       |                       3. Extract trade params
                                       |                       4. Load OHLC closes
                                       |                       5. Run N simulations:
                                       |                          - Random entries
                                       |                          - P&L from closes
                                       |                          - Compute metrics
                                       |                       6. Aggregate results
                                  Parse stdout  <-----------  ###METRICS_JSON###
                                  markers                     { monkey results }
                                       |
                                       v
                                  POST /{id}/results
                                  { metrics: { monkey: {...} },
                                    trades: [] }
                                       |
                                  (status: completed)
                                       |
  GET /api/backtests/{id}  <----  Return job + result
  Display p-value badge
  + histogram + summary
```

---

## 8. API Endpoints

All endpoints are under the `/api/backtests` prefix and require API key authentication via the `X-API-Key` header.

### 8.1 User-Facing Endpoints

#### Create Backtest Job

```
POST /api/backtests
```

**Request Body:**

```json
{
  "draft_strat_code": 1001,
  "symbol": "@ES",
  "timeframe": "1h",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "mode": "simple",
  "n_paths": null,
  "fit_years": null,
  "n_simulations": null,
  "monkey_mode": null,
  "debug": false
}
```

**Response (201):** `BacktestJobResponse`

**Validations:**
- Draft must exist (404 if not found)
- Strategy status must be `validated` and draft `todo_count` must be 0 (422 if not)
- `start_date` must be before `end_date` (422 if not)

#### List Backtest Jobs

```
GET /api/backtests?draft_strat_code=1001&status=completed
```

**Query Parameters:**
- `draft_strat_code` (optional) -- Filter by draft
- `status` (optional) -- Filter by status (`pending`, `running`, `completed`, `failed`)

**Response (200):** `BacktestListResponse` with `total` count and `jobs` array (ordered by `created_at` DESC).

#### Get Backtest Job

```
GET /api/backtests/{job_id}
```

**Response (200):** `BacktestJobResponse` with nested `result` (if completed).

#### Delete Backtest Job

```
DELETE /api/backtests/{job_id}
```

**Response (204):** No content.

**Constraints:**
- Cannot delete a `running` job (409 Conflict)

### 8.2 Worker-Internal Endpoints

These endpoints are used by the worker process to manage job lifecycle. They share the same API key authentication.

#### Get Pending Job

```
GET /api/backtests/pending
```

**Response:** `BacktestJobResponse` (oldest pending job) or `204 No Content` if none.

#### Claim Job

```
PATCH /api/backtests/{job_id}/claim
```

Atomically transitions a `pending` job to `running` with `started_at` timestamp. Uses `SELECT ... FOR UPDATE SKIP LOCKED` for safe concurrent claims.

**Response (200):** Updated `BacktestJobResponse`.

#### Report Results

```
POST /api/backtests/{job_id}/results
```

**Request Body:**

```json
{
  "metrics": { ... },
  "trades": [ ... ]
}
```

Transitions a `running` job to `completed`, stores metrics and trades in `BacktestResult`.

#### Report Failure

```
PATCH /api/backtests/{job_id}/fail
```

**Request Body:**

```json
{
  "error_message": "Engine exited with code 1: ..."
}
```

Transitions a `running` job to `failed`, stores truncated error message (max 2000 chars).

### 8.3 Response Schema

```
BacktestJobResponse:
  id:                int
  draft_strat_code:  int
  symbol:            string
  timeframe:         string
  start_date:        string
  end_date:          string
  status:            "pending" | "running" | "completed" | "failed"
  mode:              "simple" | "complete" | "montecarlo" | "monkey"
  n_paths:           int | null
  fit_years:         int | null
  n_simulations:     int | null
  monkey_mode:       string | null
  error_message:     string | null
  created_at:        datetime
  started_at:        datetime | null
  completed_at:      datetime | null
  result:            BacktestResultResponse | null

BacktestResultResponse:
  id:         int
  metrics:    dict    (structure depends on mode)
  trades:     list    (empty for simple/montecarlo/monkey, populated for complete)
  created_at: datetime
```

---

## 9. Configuration

### 9.1 Worker Configuration

Worker configuration is loaded from environment variables (or `.env` file in the `worker/` directory):

| Variable                | Default                                  | Description                              |
|-------------------------|------------------------------------------|------------------------------------------|
| `IRT_API_URL`           | `http://localhost:8000`                  | API base URL for job polling             |
| `IRT_API_KEY`           | `""`                                     | API key for authentication               |
| `WORKER_POLL_INTERVAL`  | `5`                                      | Seconds between polling cycles           |
| `WORKER_JOB_TIMEOUT`    | `300`                                    | Timeout (seconds) for simple/complete    |
| `WORKER_NUM_SLOTS`      | `3`                                      | Max concurrent work units                |
| `HIST_DATA_PATH`        | `""`                                     | Path to historical data CSV directory    |
| `ENGINE_PATH`           | `""`                                     | Path to `backtest-engine/main.py`        |
| `MC_RUNNER_PATH`        | `packages/montecarlo/runner/main_mc.py`  | Path to Monte Carlo runner entry point   |
| `WORKER_DEBUG`          | `false`                                  | Enable debug JSON saving globally        |

### 9.2 Monte Carlo Configuration

Monte Carlo constants are centralized in `packages/montecarlo/config.py` (`MonteCarloConfig` class):

**GARCH Model:**

| Constant                         | Default | Description                                    |
|----------------------------------|---------|------------------------------------------------|
| `GARCH_MAX_ITER`                 | 500     | Max MLE iterations                             |
| `GARCH_MAX_PERSISTENCE`          | 0.9999  | Max alpha + beta + gamma/2                     |
| `GARCH_N_RESTARTS`               | 5       | Random restarts for MLE                        |
| `GARCH_NU_LOWER_BOUND`           | 4.01    | Min degrees of freedom (ensures finite kurtosis)|
| `GARCH_VARIANCE_TARGETING`       | True    | Pin unconditional var to sample var            |
| `GARCH_KURTOSIS_CALIBRATION`     | True    | Post-fit nu adjustment to match kurtosis       |
| `GARCH_AR1_ENABLED`              | True    | Fit AR(1) if autocorrelation detected          |

**Regime Switching:**

| Constant                          | Default | Description                                   |
|-----------------------------------|---------|-----------------------------------------------|
| `MIN_REGIME_OBSERVATIONS`         | 500     | Min data points for regime detection           |
| `REGIME_VOL_SCALE`                | 1.5     | Stressed regime vol multiplier                 |
| `MIN_REGIME_PERSISTENCE`          | 0.70    | Min P(stay in normal)                          |
| `MIN_REGIME_PERSISTENCE_STRESSED` | 0.50    | Min P(stay in stressed)                        |
| `MIN_REGIME_DURATION_HOURS`       | 48      | Min segment duration (~2 trading days)         |
| `MAX_REGIME_STATES`               | 3       | Max HMM states to test                         |
| `AUTO_SELECT_REGIME_STATES`       | True    | Use BIC for state count                        |

**Jump Diffusion:**

| Constant           | Default | Description                                        |
|--------------------|---------|----------------------------------------------------|
| `JUMP_THRESHOLD`   | 3.0     | Std devs to classify residual as jump              |

**Simulation:**

| Constant              | Default | Description                                      |
|-----------------------|---------|--------------------------------------------------|
| `DEFAULT_N_PATHS`     | 1000    | Default number of MC paths                       |
| `MAX_N_PATHS`         | 10000   | Maximum allowed paths                            |
| `DEFAULT_SIM_BARS`    | 252     | Default simulation length (trading days)         |
| `DEFAULT_FIT_YEARS`   | 10      | Default fitting window (years)                   |
| `DEFAULT_BATCH_SIZE`  | 500     | Max paths per batch                              |

**Validation:**

| Constant                    | Default | Description                                   |
|-----------------------------|---------|-----------------------------------------------|
| `MIN_HISTORICAL_CANDLES`    | 250     | Minimum candles required                      |
| `KS_TEST_THRESHOLD`         | 0.05    | KS test p-value threshold                     |
| `KS_PRACTICAL_THRESHOLD`    | 0.10    | Max KS statistic for "similar"                |
| `VALIDATION_TEST_PATHS`     | 100     | Paths for model fit quality check             |

**Failure Thresholds:**

| Constant                     | Default | Description                                  |
|------------------------------|---------|----------------------------------------------|
| `MAX_FAILURE_RATE`           | 0.20    | Warn if > 20% of paths fail                  |
| `MIN_SUCCESSFUL_PATHS_RATIO` | 0.50    | Minimum ratio of successful paths required   |

### 9.3 Monkey Test Configuration

| Constant                | Default | Description                              |
|-------------------------|---------|------------------------------------------|
| `DEFAULT_N_SIMULATIONS` | 1000    | Default simulation count                 |
| `DEFAULT_MODE`          | `"A"`   | Default holding period mode              |
| `MONKEY_TIMEOUT`        | 3600    | Subprocess timeout (seconds)             |
| `PROGRESS_EVERY`        | 100     | Report progress every N simulations      |
| `HISTOGRAM_BINS`        | 30      | Number of bins for distribution histogram|

### 9.4 Backtest Engine Constants

Exit reason constants defined in `_00_constants.py`:

| Constant          | Value              | Description                    |
|-------------------|--------------------|--------------------------------|
| `ExitReason.SL`   | `"SL"`             | Stop loss                      |
| `ExitReason.SL_BE`| `"SL_BE"`          | Breakeven stop                 |
| `ExitReason.SL_TSL`| `"SL_TSL"`        | Trailing stop loss             |
| `ExitReason.TP`   | `"TP"`             | Take profit                    |
| `ExitReason.NUM_BARS`| `"num_bars"`    | Max bars limit                 |
| `ExitReason.EXIT_CONDITION`| `"exit_condition"` | Strategy exit signal    |
| `ExitReason.BACKTEST_END`| `"backtest_end"` | Forced close at period end |
| `ExitReason.MARGIN_CALL`| `"margin_call"` | Insufficient margin         |

### 9.5 Position Sizing Modes

The backtest engine supports three position sizing modes, configured via the strategy draft:

| Mode          | Description                                                       |
|---------------|-------------------------------------------------------------------|
| `fixed`       | Constant number of contracts per trade (`fixed_volume`, default 1)|
| `rpo`         | Risk Per Operation: sizes position so risk = `risk_per_operation * equity` |
| `half_kelly`  | Half-Kelly criterion: dynamically adjusts based on win rate and payoff ratio |

All modes respect the optional `max_volume` cap. Modes `rpo` and `half_kelly` require `initial_equity` to be set.

### 9.6 Supported Timeframes

The engine supports the following timeframes for resampling from 1-minute data:

| Label       | Polars Duration | Notes                                    |
|-------------|-----------------|------------------------------------------|
| `1 min`     | `1m`            | Base resolution                          |
| `2 mins`    | `2m`            |                                          |
| `3 mins`    | `3m`            |                                          |
| `5 mins`    | `5m`            |                                          |
| `10 mins`   | `10m`           |                                          |
| `15 mins`   | `15m`           |                                          |
| `20 mins`   | `20m`           |                                          |
| `30 mins`   | `30m`           |                                          |
| `1 hour`    | `1h`            |                                          |
| `2 hours`   | `2h`            | Aggregated from 1H (aligned to 00:00 CT) |
| `3 hours`   | `3h`            |                                          |
| `4 hours`   | `4h`            | Aggregated from 1H (aligned to 00:00 CT) |
| `8 hours`   | `8h`            | Aggregated from 1H (aligned to 00:00 CT) |
| `1 day`     | `1d`            |                                          |
| `1 week`    | `1w`            |                                          |
| `1 month`   | `1mo`           |                                          |

Multi-hour timeframes (2H, 4H, 8H) are first resampled to 1H then aggregated with `offset='0h'` alignment to exchange time (US Central / CT). This avoids DST-related candle misalignment.
