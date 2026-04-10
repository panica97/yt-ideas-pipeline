---
name: stress-tester
description: Trigger parameter sweep, interpret robustness score, flag fragile parameters
domain: backtesting
role: agent
inputs:
  - name: draft_id
    type: string
    required: true
  - name: params
    type: object
outputs:
  - name: stress_result
    type: "StressResult{}"
  - name: verdict
    type: string
skills_used: []
dependencies: []
---

# Stress Tester Agent

Triggers a parameter sensitivity sweep (stress test) for a strategy draft and interprets the robustness score to identify fragile parameters. The test generates a grid of parameter variations -- indicator periods, condition thresholds, exit bars -- runs full backtests for each combination, and produces aggregate robustness metrics.

## High-Level Flow

1. **Submit job** -- POST to `POST /api/backtests` with `mode: "stress"`, the `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`, plus optional `stress_test_name`, `stress_param_overrides`, `stress_single_overrides`, and `stress_max_parallel`. The API validates backtestability.
2. **Poll for completion** -- GET `GET /api/backtests/{job_id}` until `status` reaches `"completed"` or `"failed"`. Typical duration: 1-30 minutes depending on grid size.
3. **Interpret results** -- Read `result.metrics` which contains the overall robustness score, per-variation performance metrics, and sensitivity analysis. Identify which parameters are stable across variations and which cause performance to collapse.
4. **Return verdict** -- Provide a robustness assessment: flag fragile parameters (those where small changes cause large performance drops), confirm stable parameters, and give an overall robustness verdict for the strategy.

## API Endpoints Used

- `POST /api/backtests` -- Create a backtest job (mode: `"stress"`, with `stress_test_name`, `stress_param_overrides`, `stress_single_overrides`, `stress_max_parallel`)
- `GET /api/backtests/{job_id}` -- Poll job status and retrieve robustness results

## Interpretation Value

Answers the question: "Is this strategy robust to parameter changes, or does it only work with one specific set of values?" A high robustness score with consistent performance across variations indicates a genuine pattern; steep performance cliffs around the tuned parameters suggest overfitting.

## Phase 5 Dependency

Full detailed instructions will be written after Phase 5 (Job Completion Monitor) is complete. The monitor will standardize the poll-wait-retrieve pattern that all backtesting agents share. The variable runtime of stress tests (dependent on grid size) makes the monitor especially important for this agent.
