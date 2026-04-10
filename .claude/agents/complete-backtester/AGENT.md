---
name: complete-backtester
description: Full backtest with trade log analysis and equity curve interpretation
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
  - name: trades
    type: "Trade[]"
skills_used: []
dependencies: []
---

# Complete Backtester Agent

Triggers a full production backtest for a strategy draft, producing both aggregate metrics and trade-level data. Unlike the simple backtest, the complete mode enables timeframe remapping, persists individual trades as parquet output, and generates a sortable trade log. This is the definitive evaluation mode used before considering live deployment.

## High-Level Flow

1. **Submit job** -- POST to `POST /api/backtests` with `mode: "complete"`, the `draft_strat_code`, `symbol`, `timeframe`, `start_date`, and `end_date`. The API validates backtestability (strategy validated, zero TODOs).
2. **Poll for completion** -- GET `GET /api/backtests/{job_id}` until `status` reaches `"completed"` or `"failed"`. Typical duration: 10-60 seconds.
3. **Interpret results** -- Read both `result.metrics` (aggregate performance) and `result.trades` (individual trade records) from the completed job. Analyze the equity curve progression, trade distribution, drawdown periods, and overall metrics.
4. **Return verdict** -- Provide a comprehensive assessment including metrics summary, trade log analysis, equity curve observations, and an overall production-readiness evaluation.

## API Endpoints Used

- `POST /api/backtests` -- Create a backtest job (mode: `"complete"`)
- `GET /api/backtests/{job_id}` -- Poll job status and retrieve results (metrics + trades)

## Interpretation Value

Goes beyond the simple backtest by adding trade-level insight -- identifies clustering of losses, drawdown recovery patterns, equity curve smoothness, and trade duration analysis that aggregate metrics alone cannot reveal.

## Phase 5 Dependency

Full detailed instructions will be written after Phase 5 (Job Completion Monitor) is complete. The monitor will standardize the poll-wait-retrieve pattern that all backtesting agents share.
