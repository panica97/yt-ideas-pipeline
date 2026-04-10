---
name: simple-backtester
description: Trigger a simple backtest via API, interpret 40+ metrics, and present results with a verdict
domain: backtesting
role: agent
inputs:
  - name: draft_id
    type: string
    required: true
  - name: timeframe
    type: string
outputs:
  - name: metrics
    type: "Metrics{}"
skills_used: []
dependencies: []
---

# Simple Backtester Agent

Triggers a simple backtest for a given strategy draft and interprets the resulting 40+ performance metrics. This is the fastest backtest mode, designed for rapid iteration during strategy development -- it runs the strategy on a single timeframe and returns aggregate metrics only (no trade-level data).

## High-Level Flow

1. **Submit job** -- POST to `POST /api/backtests` with `mode: "simple"`, the `draft_strat_code`, `symbol`, `timeframe`, `start_date`, and `end_date`. The API validates that the draft's parent strategy is `validated` and has zero pending TODOs.
2. **Poll for completion** -- GET `GET /api/backtests/{job_id}` until `status` transitions from `"pending"` / `"running"` to `"completed"` or `"failed"`. Typical duration: 5-30 seconds.
3. **Interpret results** -- Read the `result.metrics` dict from the completed job response. Analyze the 40+ metrics (profit factor, Sharpe ratio, max drawdown, win rate, etc.) and present a structured summary with a pass/fail assessment.
4. **Return verdict** -- Provide the metrics summary and an overall assessment of whether the strategy shows viable performance characteristics.

## API Endpoints Used

- `POST /api/backtests` -- Create a backtest job (mode: `"simple"`)
- `GET /api/backtests/{job_id}` -- Poll job status and retrieve results

## Interpretation Value

Provides a quick health check on a strategy draft -- identifies whether it meets basic viability thresholds across key metrics before investing time in deeper analysis (complete backtest, Monte Carlo, etc.).

## Phase 5 Dependency

Full detailed instructions will be written after Phase 5 (Job Completion Monitor) is complete. The monitor will standardize the poll-wait-retrieve pattern that all backtesting agents share.
