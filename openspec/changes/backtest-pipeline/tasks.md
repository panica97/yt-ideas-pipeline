# Tasks: One-Click Full Backtest Pipeline

**Change:** `backtest-pipeline`
**Created:** 2026-04-02
**Status:** pending

## Summary

| Phase | Description | Tasks | Estimated Sessions |
|-------|-------------|-------|--------------------|
| 1 | Data Model & Migration | 3 | 1 |
| 2 | API Backend | 6 | 1 |
| 3 | Frontend Types & Services | 2 | 1 |
| 4 | Frontend UI — Pipeline Tab | 3 | 1 |
| 5 | Frontend UI — Pipeline Status & Report | 3 | 1 |
| 6 | Verification | 3 | 1 |
| **Total** | | **20** | **~4-6** |

## Impact Radius

### Files Modified
| File | Phase | Change Summary |
|------|-------|----------------|
| `tools/db/models.py` | 1 | Add `pipeline_group` (UUID) and `pipeline_config` (JSONB) to BacktestJob (after line 224) |
| `api/models/schemas/backtest.py` | 1 | Add pipeline fields to BacktestCreateRequest, BacktestJobResponse, BacktestJobSummary; new PipelineStatusResponse |
| `api/services/backtest_service.py` | 2 | Modify create_job (line 59-76), complete_job (line 201-239), fail_job (line 242-272); add get_pipeline, _create_pipeline_children, _cancel_pipeline_siblings |
| `api/routers/backtests.py` | 2 | Add GET /pipeline/{group_id} endpoint (before line 49 /{job_id} route); add PipelineStatusResponse import |
| `frontend/src/types/backtest.ts` | 3 | Add PipelineConfig interface, PipelineStatusResponse, PipelineOverallStatus; extend BacktestMode, BacktestJob, BacktestJobSummary, CreateBacktestParams |
| `frontend/src/services/backtests.ts` | 3 | Add getPipelineStatus() function |
| `frontend/src/components/strategies/BacktestPanel.tsx` | 4-5 | 6th Pipeline mode button (after line 573-583), pipeline form section, pipeline status row grouping in job history |
| `frontend/src/components/strategies/BacktestReportDrawer.tsx` | 5 | Add optional pipelineGroupId prop (line 13), pipeline multi-section report mode |

### Files Created
| File | Phase |
|------|-------|
| `api/alembic/versions/017_add_pipeline_columns.py` | 1 |

### Not Touched
- Worker code (picks up jobs via existing `/pending` polling)
- `api/dependencies.py`
- Existing test modes (pipeline_group defaults to NULL)

---

## Phase 1: Data Model & Migration

**Goal:** Add pipeline_group and pipeline_config columns to the database and update all model/schema layers.
**Depends on:** Nothing (foundation phase).

### Task 1.1: Create Alembic migration for pipeline columns
- [x] **File:** `api/alembic/versions/017_add_pipeline_columns.py` (NEW)
- **What:** Create migration adding two nullable columns to `backtest_jobs`:
  - `pipeline_group` — `UUID(as_uuid=True)`, nullable
  - `pipeline_config` — `JSONB`, nullable
  - Partial index on `pipeline_group WHERE pipeline_group IS NOT NULL`
- **Pattern:** Follow `api/alembic/versions/016_add_stress_test_params_to_backtest_jobs.py` exactly
- **Revision chain:** revision="017", down_revision="016"
- **Downgrade:** Drop index, then drop both columns
- **Verify:** `alembic check` passes; migration applies cleanly on existing data with NULL defaults

### Task 1.2: Update SQLAlchemy model
- [x] **File:** `tools/db/models.py`
- **What:** Add to `BacktestJob` class, after `stress_max_parallel` (line 224):
  ```python
  pipeline_group: Mapped[Optional[_uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
  pipeline_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
  ```
- **Imports needed:** `import uuid as _uuid` at top; `UUID` from `sqlalchemy.dialects.postgresql` (add to existing import on line 17)
- **Verify:** Python syntax check passes; model matches migration columns

### Task 1.3: Update Pydantic schemas
- [x] **File:** `api/models/schemas/backtest.py`
- **What:**
  1. Add `import uuid as _uuid` at top
  2. Add to `BacktestCreateRequest` (after `stress_max_parallel`, line 35):
     ```python
     pipeline_group: Optional[_uuid.UUID] = None
     pipeline_config: Optional[dict] = None
     ```
  3. Add to `BacktestJobResponse` (after `stress_max_parallel`, line 85):
     ```python
     pipeline_group: _uuid.UUID | None = None
     pipeline_config: dict | None = None
     ```
  4. Add to `BacktestJobSummary` (after `stress_max_parallel`, line 111):
     ```python
     pipeline_group: _uuid.UUID | None = None
     ```
     (No pipeline_config in summary -- too large for list view)
  5. Add new `PipelineStatusResponse` model after `BacktestListResponse` (line 122):
     ```python
     PipelineStatus = Literal["pending", "running", "completed", "failed"]

     class PipelineStatusResponse(BaseModel):
         pipeline_group: _uuid.UUID
         status: PipelineStatus
         jobs: list[BacktestJobSummary]
         model_config = ConfigDict(from_attributes=True)
     ```
- **Verify:** Python syntax check passes; all schema fields match model columns

---

## Phase 2: API Backend

**Goal:** Implement pipeline orchestration, failure propagation, status derivation, and new endpoint.
**Depends on:** Phase 1 (model and schemas must exist).

### Task 2.1: Accept pipeline fields in create_job
- [x] **File:** `api/services/backtest_service.py`
- **What:** In `create_job()`, add to the `BacktestJob(...)` constructor (after line 74, after stress_max_parallel):
  ```python
  pipeline_group=getattr(body, "pipeline_group", None),
  pipeline_config=getattr(body, "pipeline_config", None),
  ```
- **Verify:** POST /api/backtests with pipeline_group and pipeline_config stores values in DB

### Task 2.2: Pipeline orchestration in complete_job
- [x] **File:** `api/services/backtest_service.py`
- **What:**
  1. After line 232 (`await db.flush()`), before the re-fetch, add:
     ```python
     if job.pipeline_group and job.pipeline_config:
         await _create_pipeline_children(db, job)
     ```
  2. Add new private function `_create_pipeline_children(db, parent)` that:
     - Reads `parent.pipeline_config` (dict with keys: montecarlo, monkey, stress)
     - Creates 3 BacktestJob children, each with:
       - Same `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`
       - Same `pipeline_group`
       - `pipeline_config=None`
       - Mode-specific fields mapped from config (see design.md section 5b)
     - Calls `db.flush()`
- **Import needed:** `import uuid as _uuid` (for type hint only)
- **Verify:** Complete a pipeline parent job -> 3 child jobs appear with status "pending" and correct params

### Task 2.3: Failure propagation in fail_job
- [x] **File:** `api/services/backtest_service.py`
- **What:**
  1. After line 265 (`await db.flush()`), before the re-fetch, add:
     ```python
     if job.pipeline_group:
         await _cancel_pipeline_siblings(db, job)
     ```
  2. Add new private function `_cancel_pipeline_siblings(db, failed_job)` that:
     - Queries siblings: same `pipeline_group`, different `id`, status in ("pending", "running")
     - Sets each sibling's status="failed", error_message="Pipeline cancelled: {mode} failed", completed_at=now
     - Calls `db.flush()`
- **Verify:** Fail one child job -> all pending/running siblings are cancelled

### Task 2.4: Pipeline status derivation helper
- [x] **File:** `api/services/backtest_service.py`
- **What:** Add new function `get_pipeline(db, group_id)` that:
  - Queries all BacktestJob where pipeline_group == group_id, ordered by created_at ASC
  - Joins BacktestResult via joinedload
  - Derives overall status: failed if any failed, completed if all completed, pending if all pending, else running
  - Returns dict: `{"pipeline_group": group_id, "status": overall, "jobs": jobs}`
- **Verify:** Function returns correct derived status for each combination

### Task 2.5: Pipeline status endpoint
- [x] **File:** `api/routers/backtests.py`
- **What:**
  1. Add import: `import uuid as _uuid` and `PipelineStatusResponse` from schemas
  2. Add endpoint BEFORE the `/{job_id}` route (before line 49) to avoid path conflicts:
     ```python
     @router.get("/pipeline/{group_id}", response_model=PipelineStatusResponse)
     async def get_pipeline_status(
         group_id: _uuid.UUID,
         db: AsyncSession = Depends(get_db),
     ):
         return await backtest_service.get_pipeline(db, group_id)
     ```
- **Route ordering:** Must come before `/{job_id}` so FastAPI doesn't try to parse "pipeline" as an integer
- **Verify:** GET /api/backtests/pipeline/{uuid} returns all jobs with derived status

### Task 2.6: Accept pipeline_group in POST /api/backtests response
- [x] **File:** `api/routers/backtests.py`
- **What:** No router changes needed (BacktestCreateRequest schema already updated in 1.3, BacktestJobResponse already updated in 1.3). This task is a verification-only check.
- **Verify:** POST /api/backtests with pipeline_group returns it in the response; GET /api/backtests list shows pipeline_group in summaries

---

## Phase 3: Frontend Types & Services

**Goal:** Add TypeScript types and API service functions for pipeline support.
**Depends on:** Phase 2 (API endpoints must exist).

### Task 3.1: Update frontend types
- [x] **File:** `frontend/src/types/backtest.ts`
- **What:**
  1. Add `PipelineConfig` interface (before BacktestJob, ~line 167):
     ```typescript
     export interface PipelineConfig {
       montecarlo: { n_paths: number; fit_years: number };
       monkey: { n_simulations: number; monkey_mode: string };
       stress: {
         stress_test_name?: string;
         stress_param_overrides?: Record<string, any>;
         stress_single_overrides?: Record<string, any>;
         stress_max_parallel?: number;
       };
     }
     ```
  2. Add `'pipeline'` to `BacktestMode` type (line 1) -- note: frontend-only UI mode, actual API mode sent is `'complete'`
  3. Add `pipeline_group?: string;` to `BacktestJob` interface (after stress_max_parallel, line 184)
  4. Add `pipeline_group?: string;` to `BacktestJobSummary` interface (after stress_max_parallel, line 208)
  5. Add `pipeline_group?: string;` and `pipeline_config?: PipelineConfig;` to `CreateBacktestParams` (after stress_max_parallel, line 234)
  6. Add new types at bottom:
     ```typescript
     export type PipelineOverallStatus = 'pending' | 'running' | 'completed' | 'failed';
     export interface PipelineStatusResponse {
       pipeline_group: string;
       status: PipelineOverallStatus;
       jobs: BacktestJobSummary[];
     }
     ```
- **Verify:** `npx tsc --noEmit` passes

### Task 3.2: Add pipeline API service function
- [x] **File:** `frontend/src/services/backtests.ts`
- **What:**
  1. Add `PipelineStatusResponse` to the import from `../types/backtest`
  2. Add function:
     ```typescript
     export async function getPipelineStatus(groupId: string): Promise<PipelineStatusResponse> {
       const { data } = await api.get<PipelineStatusResponse>(`/backtests/pipeline/${groupId}`);
       return data;
     }
     ```
- **Verify:** `npx tsc --noEmit` passes

---

## Phase 4: Frontend UI — Pipeline Tab

**Goal:** Add Pipeline as 6th mode button with unified form containing shared + collapsible mode-specific params.
**Depends on:** Phase 3 (types must exist).

### Task 4.1: Add Pipeline mode button
- [x] **File:** `frontend/src/components/strategies/BacktestPanel.tsx`
- **What:**
  1. Import `Layers` from `lucide-react` (icon for Pipeline button)
  2. After the Stress Test button (line ~583), add 6th Pipeline button:
     ```tsx
     <button
       onClick={() => setBacktestMode('pipeline')}
       className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
         backtestMode === 'pipeline'
           ? 'bg-gradient-to-r from-accent to-purple-600 text-white'
           : 'bg-surface-2 text-text-muted'
       }`}
     >
       <Layers size={12} />
       Pipeline
     </button>
     ```
  3. Update the `BacktestMode` import to include `'pipeline'`
  4. Update conditional logic that shows shared params (timeframe selector) to include `'pipeline'` alongside existing modes (line 620)
- **Verify:** Pipeline button renders, toggles active state, shows shared params (symbol, timeframe, dates)

### Task 4.2: Pipeline form with collapsible mode-specific sections
- [x] **File:** `frontend/src/components/strategies/BacktestPanel.tsx`
- **What:** When `backtestMode === 'pipeline'`, render:
  1. Shared params (already shown via 4.1)
  2. Collapsible "Monte Carlo" section reusing existing MC param inputs (n_paths, fit_years)
  3. Collapsible "Monkey Test" section reusing existing Monkey param inputs (n_simulations, monkey_mode)
  4. Collapsible "Stress Test" section reusing existing Stress param inputs (stress_test_name, param_overrides, single_overrides, max_parallel)
  5. Use `<details>/<summary>` or a simple toggle state for collapsible sections
  6. All sections expanded by default
- **Verify:** Pipeline form shows all param sections; each section is collapsible

### Task 4.3: Pipeline submit handler
- [x] **File:** `frontend/src/components/strategies/BacktestPanel.tsx`
- **What:** When `backtestMode === 'pipeline'`, the submit handler must:
  1. Generate UUID v4 via `crypto.randomUUID()`
  2. Build `pipeline_config` from current form state: `{ montecarlo: {n_paths, fit_years}, monkey: {n_simulations, monkey_mode}, stress: {stress_test_name, ...} }`
  3. Send POST with `mode: "complete"` (not "pipeline"), `pipeline_group: uuid`, `pipeline_config`
  4. Update the submit button text to "Run Pipeline" when in pipeline mode
- **Verify:** Clicking "Run Pipeline" creates a job with mode="complete", pipeline_group=UUID, pipeline_config populated

---

## Phase 5: Frontend UI — Pipeline Status & Report

**Goal:** Display pipeline jobs as grouped rows in history and provide a combined report drawer.
**Depends on:** Phase 4 (pipeline jobs must be creatable).

### Task 5.1: Pipeline status row in job history
- [x] **File:** `frontend/src/components/strategies/BacktestPanel.tsx`
- **What:**
  1. In the job history rendering section, group jobs by `pipeline_group` using `useMemo`:
     - Jobs with `pipeline_group` -> grouped into Map<string, BacktestJobSummary[]>
     - Jobs without `pipeline_group` -> individual list
  2. Render each pipeline group as a single compact `PipelineStatusRow`:
     - Format: "Pipeline: Backtest [icon] . MC [icon] . Monkey [icon] . Stress [icon]"
     - Icons: checkmark (completed), spinner (running), clock (pending), X (failed)
     - Show symbol, timeframe, date range, relative time
  3. Hide individual pipeline member jobs from the main list (they only appear in the grouped row)
- **Verify:** Pipeline jobs show as one compact row; non-pipeline jobs render normally

### Task 5.2: Pipeline Report drawer integration
- [x] **File:** `frontend/src/components/strategies/BacktestReportDrawer.tsx`
- **What:**
  1. Add optional `pipelineGroupId?: string` prop to `BacktestReportDrawerProps` (line 13)
  2. When `pipelineGroupId` is provided:
     - Fetch all pipeline jobs via `getPipelineStatus(pipelineGroupId)`
     - Render scrollable view with 4 sections: Backtest summary, MC report, Monkey report, Stress report
     - Each section reuses existing result components (MetricsGrid, MonkeyTestReport, StressTestReport, etc.)
     - Failed sections show error message instead of results
  3. Show overall pipeline status at top (derived from job statuses)
- **Verify:** Clicking a completed pipeline row opens drawer with all 4 result sections

### Task 5.3: Wire pipeline row click to report drawer
- [x] **File:** `frontend/src/components/strategies/BacktestPanel.tsx`
- **What:**
  1. When user clicks a pipeline status row, open BacktestReportDrawer with `pipelineGroupId` set
  2. Add state for tracking which pipeline group to display in the drawer
  3. Pass `pipelineGroupId` prop to BacktestReportDrawer
- **Verify:** End-to-end: click pipeline row -> drawer opens -> shows all results

---

## Phase 6: Verification

**Goal:** Ensure everything compiles, works, and matches specs.
**Depends on:** Phases 1-5 complete.

### Task 6.1: TypeScript compilation check
- [x] **Command:** `cd frontend && npx tsc --noEmit`
- **What:** Ensure all TypeScript types align, no import errors, no type mismatches
- **Fix:** Any type errors found

### Task 6.2: Python syntax and import check
- [x] **Command:** `python -c "from tools.db.models import BacktestJob; from api.models.schemas.backtest import PipelineStatusResponse; from api.services.backtest_service import get_pipeline; print('OK')"`
- **What:** Ensure all Python imports resolve, no syntax errors
- **Fix:** Any import or syntax errors found

### Task 6.3: Manual verification checklist
- [x] Create pipeline job via POST with pipeline_group + pipeline_config -> stored correctly
- [x] Complete parent -> 3 child jobs created with correct params and same pipeline_group
- [x] Fail one child -> siblings cancelled with descriptive error message
- [x] GET /pipeline/{group_id} -> returns all 4 jobs with derived status
- [x] Non-pipeline jobs unaffected (pipeline_group=NULL, no grouping)
- [x] Frontend Pipeline tab renders form with all sections
- [x] Pipeline submit sends correct payload (mode="complete", UUID, config)
- [x] Job history groups pipeline jobs into compact row
- [x] Pipeline report drawer shows all 4 result sections
- [x] Migration applies and downgrades cleanly

---

## Dependency Graph

```
Phase 1 (Data Model)
    |
    v
Phase 2 (API Backend)
    |
    v
Phase 3 (Frontend Types)
    |
    v
Phase 4 (Pipeline Tab + Form)
    |
    v
Phase 5 (Status Row + Report)
    |
    v
Phase 6 (Verification)
```

Phases are strictly sequential. Within each phase, tasks can be done in order listed (some are parallelizable within a phase, e.g., 2.2 and 2.3 are independent after 2.1).
