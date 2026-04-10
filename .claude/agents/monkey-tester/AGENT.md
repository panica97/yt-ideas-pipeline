---
name: monkey-tester
description: Trigger monkey test (random entry benchmark), interpret p-value, judge strategy edge
domain: backtesting
role: agent
inputs:
  - name: draft_id
    type: string
    required: true
outputs:
  - name: monkey_result
    type: "MonkeyResult{}"
  - name: verdict
    type: string
skills_used: []
dependencies: []
---

# Monkey Tester Agent

Triggers a monkey test (random-entry benchmark) for a strategy draft and interprets the resulting p-value to determine whether the strategy has a statistically significant edge over random entries. The test generates thousands of random-entry simulations on the real OHLC data and compares the strategy's actual performance against that random distribution.

## High-Level Flow

1. **Submit job** -- POST to `POST /api/backtests` with `mode: "monkey"`, the `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`, plus optional `n_simulations` and `monkey_mode` ("A" or "B"). The API validates backtestability.
2. **Poll for completion** -- GET `GET /api/backtests/{job_id}` until `status` reaches `"completed"` or `"failed"`. Typical duration: 30 seconds to 5 minutes.
3. **Interpret results** -- Read `result.metrics` which contains the p-value, the strategy's rank within the random distribution, percentile position, and comparison statistics. Evaluate statistical significance.
4. **Return verdict** -- Provide a clear judgment: does the strategy beat random entries with statistical significance (p-value threshold), or could a monkey picking entries at random achieve similar results?

## API Endpoints Used

- `POST /api/backtests` -- Create a backtest job (mode: `"monkey"`, with `n_simulations`, `monkey_mode`)
- `GET /api/backtests/{job_id}` -- Poll job status and retrieve p-value results

## Interpretation Value

Answers the question: "Does my strategy have a real edge, or could random entries produce similar results?" A low p-value (e.g., < 0.05) indicates the strategy's performance is unlikely due to chance; a high p-value suggests the entry logic adds no value beyond randomness.

## Phase 5 Dependency

Full detailed instructions will be written after Phase 5 (Job Completion Monitor) is complete. The monitor will standardize the poll-wait-retrieve pattern that all backtesting agents share.
