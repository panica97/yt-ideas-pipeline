# One-Click Full Backtest Pipeline — Phase 13

**Status:** Planned
**Started:** —
**SDD Change:** backtest-pipeline
**Parent Phase:** Phase 13 from Master Plan

---

## Goal

A single "Pipeline" mode tab in BacktestPanel that launches a complete analysis chain in one click: Backtest → (Monte Carlo + Monkey Test + Stress Test) in parallel. No new tables — uses a `pipeline_group` UUID on existing `backtest_jobs` to link the 4 jobs. API orchestrates child job creation when the initial backtest completes. Results shown in a dedicated Pipeline Report drawer.

## Architecture

```
Frontend (Pipeline tab)
    |
    POST /api/backtests  (mode="complete", pipeline_group=UUID, pipeline_config={mc,monkey,stress params})
    |
    v
API creates 1 backtest job with pipeline_group + stores pipeline_config
    |
    Worker picks up job, runs backtest
    |
    POST /api/backtests/{id}/results
    |
    v
API service detects pipeline_group → auto-creates 3 jobs:
    - mode="montecarlo"  (same pipeline_group, params from pipeline_config)
    - mode="monkey"      (same pipeline_group, params from pipeline_config)
    - mode="stress"      (same pipeline_group, params from pipeline_config)
    |
    Worker picks up 3 jobs in parallel (existing fair-sharing)
    |
    When all 3 report results → pipeline_group is "completed"
    If any fails → pipeline_group is "failed"
```

## Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Data model: add `pipeline_group` (UUID) and `pipeline_config` (JSONB) columns to `backtest_jobs` + Alembic migration | quick fix | — | Planned |
| 2 | API: pipeline orchestration in backtest service — on results submission, detect `pipeline_group` + `pipeline_config` and auto-create 3 child jobs | /sdd-new | — | Planned |
| 3 | API: convenience endpoint `GET /api/backtests/pipeline/{group_id}` returning all 4 jobs | quick fix | — | Planned |
| 4 | API: pipeline status derivation — all completed → completed, any failed → failed, else running | quick fix | — | Planned |
| 5 | Frontend: "Pipeline" mode tab (6th button) with unified form — shared params + collapsible MC/Monkey/Stress param sections | /sdd-new | — | Planned |
| 6 | Frontend: pipeline status row in job history — compact inline `Pipeline: Backtest ✓ · MC ⟳ · Monkey ✓ · Stress ⟳` grouped by `pipeline_group` | /sdd-new | — | Planned |
| 7 | Frontend: Pipeline Report drawer — scrollable single view with summary + sections reusing existing MC/Monkey/Stress result components | /sdd-new | — | Planned |

## Design Decisions

| Date | Decision | Why | Impact |
|------|----------|-----|--------|
| 2026-04-03 | No new table — `pipeline_group` UUID on `backtest_jobs` | Keep it lean, reuse existing infrastructure | No schema complexity, pipeline status derived from child jobs |
| 2026-04-03 | API-side orchestration (not worker) | Keep worker dumb, centralize logic in service layer | Worker stays generic, pipeline logic in one place |
| 2026-04-03 | Fail entire pipeline if any step fails | Individual tests already validated separately | Simpler error model, no partial success handling |
| 2026-04-03 | Pipeline tab as 6th mode (option A) | Single form collects all params at once | One-click UX, no multi-step wizard or pre-config needed |
| 2026-04-03 | Compact inline status (option C) | Fits existing layout without new component | Minimal UI disruption |
| 2026-04-03 | Dedicated Pipeline Report drawer (option B) | All 4 results in one scrollable view | Better overview than clicking 4 individual reports |

## Error Handling

- Initial backtest fails → pipeline fails, no child jobs created
- Any of the 3 parallel jobs fail → entire pipeline marked as failed
- User sees which step failed in the status row
- No auto-retry — user investigates and re-runs the whole pipeline

## What We're NOT Building

- No new database table
- No pipeline queue or scheduler — reuses existing worker polling
- No partial success handling
- No retry mechanism
- No pipeline history/comparison view (future phase if needed)

## SDD Progress

_No SDD phases started yet._

## Notes

- Pipeline config stored as JSONB on the first (complete backtest) job only
- Child jobs inherit symbol, timeframe, dates from parent
- Pipeline status is derived by querying all jobs with same pipeline_group
- Existing fair-sharing in worker handles parallel execution of the 3 child jobs
- Frontend groups pipeline jobs by pipeline_group UUID for display
- **Pending verdict change (stress test):** The stress test robustness verdict will migrate from absolute-threshold mode (6 criteria checking strategy quality) to baseline-comparison mode (each variation compared against original parameters using `return_drawdown_ratio` and `max_drawdown_pct`, stable if within ±50% of baseline, verdict: Robust >=80% / Moderate >=50% / Fragile <50%). This is independent of the pipeline feature but will affect how the Pipeline Report displays stress test results. See `docs/documentation/backtesting.md` section 7.6 for full details.
