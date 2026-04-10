---
name: monte-carlo-analyst
description: Trigger Monte Carlo simulation, interpret distributional stats, assess luck vs skill
domain: backtesting
role: agent
inputs:
  - name: draft_id
    type: string
    required: true
  - name: config
    type: object
outputs:
  - name: mc_result
    type: "MCResult{}"
  - name: assessment
    type: string
skills_used: []
dependencies: []
---

# Monte Carlo Analyst Agent

Triggers a Monte Carlo simulation for a strategy draft and interprets the distributional statistics to assess whether the strategy's performance is robust across varying market conditions or largely attributable to luck. The simulation fits a GJR-GARCH model on historical data, generates thousands of synthetic OHLC price paths, and runs the strategy on each.

## High-Level Flow

1. **Submit job** -- POST to `POST /api/backtests` with `mode: "montecarlo"`, the `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`, plus optional `n_paths` and `fit_years` configuration. The API validates backtestability.
2. **Poll for completion** -- GET `GET /api/backtests/{job_id}` until `status` reaches `"completed"` or `"failed"`. Typical duration: 5-60 minutes (much longer than simple/complete modes).
3. **Interpret results** -- Read `result.metrics` which contains distributional statistics across all simulated paths -- percentile distributions of returns, drawdowns, Sharpe ratios, and risk-of-ruin estimates. Assess the spread between best-case and worst-case outcomes.
4. **Return assessment** -- Provide a luck-vs-skill assessment: how much of the strategy's historical performance is attributable to the specific market conditions vs. the strategy logic itself.

## API Endpoints Used

- `POST /api/backtests` -- Create a backtest job (mode: `"montecarlo"`, with `n_paths`, `fit_years`)
- `GET /api/backtests/{job_id}` -- Poll job status and retrieve distributional results

## Interpretation Value

Answers the question: "Would this strategy still work if market history had played out differently?" A narrow distribution of positive outcomes indicates genuine edge; a wide distribution crossing into negative territory suggests the historical result may be a statistical artifact.

## Phase 5 Dependency

Full detailed instructions will be written after Phase 5 (Job Completion Monitor) is complete. The monitor will standardize the poll-wait-retrieve pattern that all backtesting agents share. The longer runtime of MC simulations makes the monitor especially important for this agent.
