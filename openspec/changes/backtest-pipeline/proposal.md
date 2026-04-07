# Proposal: One-Click Full Backtest Pipeline

## Intent

Enable users to launch a complete analysis chain (Backtest → Monte Carlo + Monkey Test + Stress Test in parallel) with a single button click from the frontend. Currently each test must be configured and launched individually, requiring 4 separate actions with redundant parameter entry.

## Scope

### In Scope
- Add `pipeline_group` (UUID) and `pipeline_config` (JSONB) columns to `backtest_jobs` table + Alembic migration
- API-side orchestration: on backtest results submission, detect pipeline_group and auto-create 3 child jobs (MC, Monkey, Stress)
- Convenience endpoint `GET /api/backtests/pipeline/{group_id}` returning all 4 jobs
- Pipeline status derivation (all completed → completed, any failed → failed, else running)
- Frontend "Pipeline" mode tab (6th button) with unified form — shared params + collapsible MC/Monkey/Stress param sections
- Frontend pipeline status row in job history — compact inline grouped by pipeline_group
- Frontend Pipeline Report drawer — scrollable single view with summary + sections reusing existing result components

### Out of Scope
- New database table for pipelines
- Pipeline queue or scheduler (reuses existing worker polling)
- Partial success handling (fail = whole pipeline fails)
- Auto-retry mechanism
- Pipeline history/comparison view

## Approach

Lean approach: add two nullable columns to existing `backtest_jobs` table. Frontend creates the first job (mode="complete") with a pipeline_group UUID and pipeline_config JSONB containing MC/Monkey/Stress params. When the worker reports results for this job, the API service layer detects the pipeline_group, reads pipeline_config, and auto-creates 3 child jobs with the same pipeline_group. Worker picks them up via existing polling. Frontend groups and displays pipeline jobs by pipeline_group UUID.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tools/db/models.py` | Modified | Add pipeline_group and pipeline_config columns to BacktestJob |
| `api/alembic/versions/` | New | Migration for new columns |
| `api/models/schemas/backtest.py` | Modified | Add pipeline fields to request/response schemas |
| `api/services/backtest_service.py` | Modified | Pipeline orchestration logic on results submission |
| `api/routers/backtests.py` | Modified | New pipeline endpoint, accept pipeline fields |
| `frontend/src/types/backtest.ts` | Modified | Add pipeline types |
| `frontend/src/services/backtests.ts` | Modified | Add pipeline API calls |
| `frontend/src/components/strategies/BacktestPanel.tsx` | Modified | Pipeline mode tab + form + status row |
| `frontend/src/components/strategies/BacktestReportDrawer.tsx` | Modified | Pipeline Report view |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| pipeline_config JSONB schema drift | Low | Validate config structure in API before creating child jobs |
| Worker overload from 3 simultaneous jobs | Low | Existing fair-sharing caps per-job slots |
| Frontend polling overhead for 4 jobs | Low | Already polls every 3s; pipeline jobs grouped in same query |
| Migration on production data | Low | Nullable columns, no data transformation needed |

## Rollback Plan

1. Revert Alembic migration (drop two nullable columns)
2. Remove pipeline endpoint and orchestration logic from API
3. Remove Pipeline tab from frontend
4. All existing backtest functionality unchanged (pipeline_group defaults to null)

## Dependencies

- Existing backtest infrastructure (Phase 8-12)
- All 4 modes (complete, montecarlo, monkey, stress) working independently

## Success Criteria

- [ ] Single "Pipeline" button creates 1 backtest job with pipeline_group UUID
- [ ] On backtest completion, API auto-creates 3 child jobs (MC, Monkey, Stress) with same pipeline_group
- [ ] All 3 child jobs run in parallel via existing worker
- [ ] Frontend shows compact pipeline status row grouping all 4 jobs
- [ ] Pipeline Report drawer shows all 4 results in one scrollable view
- [ ] If any job fails, entire pipeline is marked as failed
- [ ] Existing individual backtest modes still work unchanged (pipeline_group = null)
