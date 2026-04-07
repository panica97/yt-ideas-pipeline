# Technical Design: One-Click Full Backtest Pipeline

## 1. Architecture Overview

### Data Flow

```
                                  Frontend (BacktestPanel)
                                         |
                         [1] POST /api/backtests
                             mode="complete"
                             pipeline_group=<uuid4>
                             pipeline_config={mc:{...}, monkey:{...}, stress:{...}}
                                         |
                                         v
                            +---------------------------+
                            |   backtest_service        |
                            |   create_job()            |
                            |   (stores parent job      |
                            |    with pipeline_group    |
                            |    + pipeline_config)     |
                            +---------------------------+
                                         |
                                  Worker picks up
                                  (existing polling)
                                         |
                         [2] POST /api/backtests/{id}/results
                                         |
                                         v
                            +---------------------------+
                            |   backtest_service        |
                            |   complete_job()          |
                            |                           |
                            |   Detects pipeline_group  |
                            |   + pipeline_config       |
                            |   on completed parent     |
                            |                           |
                            |   Creates 3 child jobs:   |
                            |   - montecarlo            |
                            |   - monkey                |
                            |   - stress                |
                            |   Same pipeline_group,    |
                            |   pipeline_config=NULL    |
                            +---------------------------+
                                    |     |     |
                              +-----+     |     +-----+
                              v           v           v
                           MC job    Monkey job   Stress job
                          (pending)  (pending)    (pending)
                              |           |           |
                         Worker picks up each (existing polling)
                              |           |           |
                              v           v           v
                          complete    complete     complete
                              \           |           /
                               +-----+---+---+------+
                                     |
                         [3] GET /api/backtests/pipeline/{group_id}
                                     |
                                     v
                            +---------------------------+
                            |  Frontend groups by       |
                            |  pipeline_group           |
                            |  Shows compact row +      |
                            |  Pipeline Report drawer   |
                            +---------------------------+

         [4] If any child fails:
             PATCH /api/backtests/{id}/fail
                     |
                     v
             fail_job() detects pipeline_group
             Cancels sibling jobs (pending/running -> failed)
```

## 2. Impact Radius

### Backend
| File | Change Type | Impact |
|------|-------------|--------|
| `tools/db/models.py` | Modified | Add 2 columns to BacktestJob. No relationship changes. |
| `api/alembic/versions/017_add_pipeline_columns.py` | **New** | Migration for pipeline_group + pipeline_config. |
| `api/models/schemas/backtest.py` | Modified | Add pipeline fields to request/response/summary schemas. New PipelineStatusResponse. |
| `api/services/backtest_service.py` | Modified | Orchestration in complete_job, cancellation in fail_job, new get_pipeline function. |
| `api/routers/backtests.py` | Modified | New GET endpoint for pipeline status. |

### Frontend
| File | Change Type | Impact |
|------|-------------|--------|
| `frontend/src/types/backtest.ts` | Modified | Add pipeline fields to types. New PipelineConfig, PipelineStatus types. |
| `frontend/src/services/backtests.ts` | Modified | Add getPipelineStatus() API call. |
| `frontend/src/components/strategies/BacktestPanel.tsx` | Modified | 6th Pipeline tab, pipeline form, pipeline status row in history. |
| `frontend/src/components/strategies/BacktestReportDrawer.tsx` | Modified | Support opening in "pipeline mode" with all 4 results. |

### Not Touched
- Worker code (picks up jobs via existing `/pending` polling -- no changes)
- `api/dependencies.py`
- Existing test modes (pipeline_group defaults to NULL for non-pipeline jobs)

## 3. Architecture Decisions

### ADR-1: No New Table

**Decision:** Add `pipeline_group` and `pipeline_config` as nullable columns to `backtest_jobs` instead of creating a `pipelines` table.

**Rationale:**
- Avoids new model, new relationships, new CRUD. Two nullable columns are simpler.
- Pipeline status is derived from job statuses, not stored. No extra state to sync.
- Existing queries, worker polling, and list endpoints work unchanged (pipeline_group=NULL for non-pipeline jobs).
- Rollback is trivial: drop two columns.

**Trade-off:** If pipeline metadata grows (e.g. pipeline-level notes, retries), a dedicated table would be cleaner. Acceptable for current scope.

### ADR-2: API-Side Orchestration (Not Frontend)

**Decision:** The API service layer creates child jobs when the parent backtest completes, not the frontend.

**Rationale:**
- Single source of truth. Frontend sends one POST; API handles the fan-out.
- If frontend crashes or disconnects after parent completes, children are still created.
- Worker needs no changes -- it continues polling `/pending`.

**Trade-off:** API has more logic. Acceptable because `backtest_service.py` is already the orchestration layer.

### ADR-3: Frontend Generates pipeline_group UUID

**Decision:** The frontend generates the UUID v4 for `pipeline_group` and sends it in the initial POST request.

**Rationale:**
- Frontend immediately knows the pipeline_group for polling/display without waiting for a server response.
- Avoids a two-step create flow (create pipeline, then create job).
- UUID v4 collision is negligible.

### ADR-4: Derived Pipeline Status

**Decision:** Pipeline status is computed on read, never stored.

**Rationale:**
- No stale status. Always reflects actual job states.
- Computation is trivial (4 rows max per pipeline).
- No extra column, no update triggers.

### ADR-5: Failure Propagation via fail_job

**Decision:** When `fail_job` is called for a pipeline job, the service cancels all sibling jobs that are still pending or running.

**Rationale:**
- Prevents wasted compute on a doomed pipeline.
- Simple: query siblings by pipeline_group, set status="failed" with a descriptive error message.
- Running jobs may not stop immediately (worker would need to check), but they'll be marked failed so results are discarded.

## 4. Database Changes

### Alembic Migration: `017_add_pipeline_columns.py`

Following the exact pattern of `016_add_stress_test_params_to_backtest_jobs.py`:

```python
"""add pipeline columns to backtest jobs

Revision ID: 017
Revises: 016
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("pipeline_group", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("pipeline_config", JSONB, nullable=True),
    )
    op.create_index(
        "idx_backtest_jobs_pipeline_group",
        "backtest_jobs",
        ["pipeline_group"],
        postgresql_where=sa.text("pipeline_group IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_backtest_jobs_pipeline_group", table_name="backtest_jobs")
    op.drop_column("backtest_jobs", "pipeline_config")
    op.drop_column("backtest_jobs", "pipeline_group")
```

**Note:** Partial index on `pipeline_group IS NOT NULL` so lookups for pipeline siblings are fast without bloating the index with NULLs from regular jobs.

### Model Change: `tools/db/models.py`

Add to `BacktestJob` class, after `stress_max_parallel`:

```python
import uuid as _uuid
from sqlalchemy.dialects.postgresql import UUID

# Inside BacktestJob:
pipeline_group: Mapped[Optional[_uuid.UUID]] = mapped_column(
    UUID(as_uuid=True), nullable=True
)
pipeline_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
```

UUID import note: `UUID` is already available from `sqlalchemy.dialects.postgresql`. The `uuid` stdlib import is new and uses alias `_uuid` to avoid collision with the SQLAlchemy type.

## 5. API Layer Changes

### Schema Changes: `api/models/schemas/backtest.py`

Add pipeline fields to existing schemas (following the exact pattern of stress_* fields):

```python
import uuid as _uuid

# --- BacktestCreateRequest: add after stress_max_parallel ---
pipeline_group: Optional[_uuid.UUID] = None
pipeline_config: Optional[dict] = None

# --- BacktestJobResponse: add after stress_max_parallel ---
pipeline_group: _uuid.UUID | None = None
pipeline_config: dict | None = None

# --- BacktestJobSummary: add after stress_max_parallel ---
pipeline_group: _uuid.UUID | None = None
# (pipeline_config NOT in summary -- too large for list view)
```

New response model for the pipeline endpoint:

```python
PipelineStatus = Literal["pending", "running", "completed", "failed"]


class PipelineStatusResponse(BaseModel):
    pipeline_group: _uuid.UUID
    status: PipelineStatus
    jobs: list[BacktestJobSummary]

    model_config = ConfigDict(from_attributes=True)
```

### Service Changes: `api/services/backtest_service.py`

#### 5a. `create_job` -- accept pipeline fields

Add to the `BacktestJob(...)` constructor call:

```python
pipeline_group=getattr(body, "pipeline_group", None),
pipeline_config=getattr(body, "pipeline_config", None),
```

No other changes to create_job logic.

#### 5b. `complete_job` -- pipeline orchestration

After setting `job.status = "completed"` and creating BacktestResult, add:

```python
# --- Pipeline orchestration ---
if job.pipeline_group and job.pipeline_config:
    await _create_pipeline_children(db, job)
```

New private function:

```python
async def _create_pipeline_children(
    db: AsyncSession, parent: BacktestJob
) -> list[BacktestJob]:
    """Create MC, Monkey, and Stress child jobs from a completed pipeline parent."""
    config = parent.pipeline_config  # dict with keys: montecarlo, monkey, stress
    children = []

    # Map of mode -> config key -> mode-specific field mappings
    mode_configs = {
        "montecarlo": {
            "config_key": "montecarlo",
            "fields": lambda c: {
                "n_paths": c.get("n_paths", 1000),
                "fit_years": c.get("fit_years", 10),
            },
        },
        "monkey": {
            "config_key": "monkey",
            "fields": lambda c: {
                "n_simulations": c.get("n_simulations", 1000),
                "monkey_mode": c.get("monkey_mode", "A"),
            },
        },
        "stress": {
            "config_key": "stress",
            "fields": lambda c: {
                "stress_test_name": c.get("stress_test_name"),
                "stress_param_overrides": c.get("stress_param_overrides"),
                "stress_single_overrides": c.get("stress_single_overrides"),
                "stress_max_parallel": c.get("stress_max_parallel", 4),
            },
        },
    }

    for mode, cfg in mode_configs.items():
        mode_params = config.get(cfg["config_key"], {})
        extra_fields = cfg["fields"](mode_params)

        child = BacktestJob(
            draft_strat_code=parent.draft_strat_code,
            symbol=parent.symbol,
            timeframe=parent.timeframe,
            start_date=parent.start_date,
            end_date=parent.end_date,
            status="pending",
            mode=mode,
            pipeline_group=parent.pipeline_group,
            pipeline_config=None,  # only parent stores config
            **extra_fields,
        )
        db.add(child)
        children.append(child)

    await db.flush()
    return children
```

#### 5c. `fail_job` -- pipeline failure propagation

After setting `job.status = "failed"`, add:

```python
# --- Pipeline failure propagation ---
if job.pipeline_group:
    await _cancel_pipeline_siblings(db, job)
```

New private function:

```python
async def _cancel_pipeline_siblings(
    db: AsyncSession, failed_job: BacktestJob
) -> None:
    """Cancel all pending/running siblings in the same pipeline."""
    siblings = await db.execute(
        select(BacktestJob)
        .where(
            BacktestJob.pipeline_group == failed_job.pipeline_group,
            BacktestJob.id != failed_job.id,
            BacktestJob.status.in_(["pending", "running"]),
        )
    )
    for sibling in siblings.scalars().all():
        sibling.status = "failed"
        sibling.error_message = f"Pipeline cancelled: {failed_job.mode} failed"
        sibling.completed_at = datetime.now(timezone.utc)

    await db.flush()
```

#### 5d. New function: `get_pipeline`

```python
async def get_pipeline(
    db: AsyncSession, group_id: _uuid.UUID
) -> dict[str, Any]:
    """Get all jobs for a pipeline group with derived overall status."""
    result = await db.execute(
        select(BacktestJob)
        .options(joinedload(BacktestJob.result))
        .where(BacktestJob.pipeline_group == group_id)
        .order_by(BacktestJob.created_at.asc())
    )
    jobs = result.unique().scalars().all()

    # Derive status
    statuses = [j.status for j in jobs]
    if any(s == "failed" for s in statuses):
        overall = "failed"
    elif all(s == "completed" for s in statuses):
        overall = "completed"
    elif all(s == "pending" for s in statuses):
        overall = "pending"
    else:
        overall = "running"

    return {
        "pipeline_group": group_id,
        "status": overall,
        "jobs": jobs,
    }
```

### Router Changes: `api/routers/backtests.py`

Add new endpoint (before the `/{job_id}` routes to avoid path conflict):

```python
import uuid as _uuid
from api.models.schemas.backtest import PipelineStatusResponse

@router.get("/pipeline/{group_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    group_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.get_pipeline(db, group_id)
```

**Route ordering note:** This must be registered before `/{job_id}` to prevent FastAPI from matching "pipeline" as a job_id integer (would 422 anyway, but cleaner).

## 6. Frontend Changes

### 6a. Types: `frontend/src/types/backtest.ts`

```typescript
// New: pipeline config sent in create request
export interface PipelineConfig {
  montecarlo: {
    n_paths: number;
    fit_years: number;
  };
  monkey: {
    n_simulations: number;
    monkey_mode: string;
  };
  stress: {
    stress_test_name?: string;
    stress_param_overrides?: Record<string, any>;
    stress_single_overrides?: Record<string, any>;
    stress_max_parallel?: number;
  };
}

// Add to BacktestMode:
export type BacktestMode = 'simple' | 'complete' | 'montecarlo' | 'monkey' | 'stress' | 'pipeline';
// Note: 'pipeline' is frontend-only UI mode. The actual API mode sent is 'complete'.

// Add to BacktestJob, BacktestJobSummary:
//   pipeline_group?: string;  // UUID as string from JSON

// Add to CreateBacktestParams:
//   pipeline_group?: string;
//   pipeline_config?: PipelineConfig;

// New: pipeline status response
export type PipelineOverallStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface PipelineStatusResponse {
  pipeline_group: string;
  status: PipelineOverallStatus;
  jobs: BacktestJobSummary[];
}
```

### 6b. API Service: `frontend/src/services/backtests.ts`

```typescript
import type { PipelineStatusResponse } from '../types/backtest';

export async function getPipelineStatus(groupId: string): Promise<PipelineStatusResponse> {
  const { data } = await api.get<PipelineStatusResponse>(`/backtests/pipeline/${groupId}`);
  return data;
}
```

### 6c. BacktestPanel: Pipeline Tab + Form

Add a 6th button in the mode selector:

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

When `backtestMode === 'pipeline'`:
- Show shared params (symbol, timeframe, dates) -- reuse existing inputs
- Show 3 collapsible sections (MC params, Monkey params, Stress params) -- reuse existing param inputs
- "Run Pipeline" button generates `crypto.randomUUID()`, sends POST with:
  - `mode: "complete"` (actual API mode)
  - `pipeline_group: uuid`
  - `pipeline_config: { montecarlo: {...}, monkey: {...}, stress: {...} }`

### 6d. BacktestPanel: Pipeline Status Row in History

In the job history section, group jobs by `pipeline_group` before rendering:

```typescript
// Group jobs: pipeline jobs grouped, non-pipeline jobs as singles
const { pipelineGroups, individualJobs } = useMemo(() => {
  const groups = new Map<string, BacktestJobSummary[]>();
  const singles: BacktestJobSummary[] = [];

  for (const job of jobs) {
    if (job.pipeline_group) {
      const existing = groups.get(job.pipeline_group) ?? [];
      existing.push(job);
      groups.set(job.pipeline_group, existing);
    } else {
      singles.push(job);
    }
  }

  return { pipelineGroups: groups, individualJobs: singles };
}, [jobs]);
```

Render pipeline groups as a compact `PipelineStatusRow` component:

```
+--------------------------------------------------------------+
| Pipeline  [BT checkmark] [MC spinner] [Monkey checkmark] [Stress spinner] |
| MNQ . 1H . 2025-01-01 -> 2025-12-31         2m ago          |
+--------------------------------------------------------------+
```

Each step shows an icon: checkmark (completed), spinner (running), clock (pending), X (failed). Clicking the row opens the Pipeline Report drawer.

### 6e. BacktestReportDrawer: Pipeline Mode

Add an optional `pipelineGroupId` prop:

```typescript
interface BacktestReportDrawerProps {
  jobId: number;            // existing -- used for single-job reports
  pipelineGroupId?: string; // new -- when set, fetches all pipeline jobs
  open: boolean;
  onClose: () => void;
}
```

When `pipelineGroupId` is provided:
- Fetch via `getPipelineStatus(pipelineGroupId)`
- Render a scrollable view with 4 sections: Backtest summary, MC report, Monkey report, Stress report
- Each section reuses existing result components (`MetricsGrid`, `MonkeyTestReport`, `StressTestReport`, etc.)
- Failed sections show the error message instead of results

## 7. pipeline_config JSONB Schema

Validated in `_create_pipeline_children` before creating child jobs. Expected structure:

```json
{
  "montecarlo": {
    "n_paths": 1000,
    "fit_years": 10
  },
  "monkey": {
    "n_simulations": 1000,
    "monkey_mode": "A"
  },
  "stress": {
    "stress_test_name": "param_sweep_01",
    "stress_param_overrides": { "rsi_period": [10, 14, 20] },
    "stress_single_overrides": { "rsi_period": [8, 10, 12, 14, 16, 18, 20] },
    "stress_max_parallel": 4
  }
}
```

All keys are optional within each sub-object; defaults are applied in `_create_pipeline_children`.

## 8. Edge Cases

| Case | Behavior |
|------|----------|
| Parent backtest fails | No children created. Pipeline is "failed" (1 job, failed). |
| Child MC fails, Monkey+Stress pending | Monkey+Stress set to failed with "Pipeline cancelled: montecarlo failed". |
| Child MC fails, Stress already completed | Stress stays completed. Only pending/running siblings cancelled. |
| User deletes pipeline parent | Cascade: children share pipeline_group but have no FK to parent. Deleting parent does NOT delete children. User must delete individually. |
| Pipeline job mixed in list endpoint | `GET /api/backtests?draft_strat_code=X` returns all jobs including pipeline ones. Frontend groups them. |
| Worker picks up child before parent finishes | Not possible. Children are created only after parent completes. |
| Two pipelines for same draft | Each has unique pipeline_group UUID. No conflict. |

## 9. File Change Checklist

### Backend (ordered by dependency)

1. `api/alembic/versions/017_add_pipeline_columns.py` -- **new file**
2. `tools/db/models.py` -- add `pipeline_group`, `pipeline_config` to BacktestJob
3. `api/models/schemas/backtest.py` -- add pipeline fields to schemas + PipelineStatusResponse
4. `api/services/backtest_service.py` -- modify create_job, complete_job, fail_job; add get_pipeline, _create_pipeline_children, _cancel_pipeline_siblings
5. `api/routers/backtests.py` -- add GET /pipeline/{group_id} endpoint

### Frontend (ordered by dependency)

6. `frontend/src/types/backtest.ts` -- add PipelineConfig, PipelineStatusResponse types; extend BacktestMode, BacktestJob, BacktestJobSummary, CreateBacktestParams
7. `frontend/src/services/backtests.ts` -- add getPipelineStatus()
8. `frontend/src/components/strategies/BacktestPanel.tsx` -- Pipeline tab, pipeline form, pipeline status row grouping
9. `frontend/src/components/strategies/BacktestReportDrawer.tsx` -- pipeline mode with multi-section report

## 10. Open Questions

1. **Delete cascading for pipelines:** Should deleting a pipeline parent also delete all children? Current design: no FK between parent/children (only shared pipeline_group). Could add a "Delete Pipeline" action that deletes all jobs with the same group.

2. **Pipeline re-run:** If a pipeline fails at the Stress step, should there be a "Retry failed steps" action? Out of scope per proposal, but design is extensible (pipeline_config is preserved on the parent).

3. **Worker concurrency:** Three child jobs become pending simultaneously. If the worker processes them sequentially (one at a time), pipeline completion could take 3x longer. The existing worker polling picks the oldest pending job; all three will queue up normally. No design change needed, but worth noting for UX expectations.
