# Tasks: simple-backtesting

**Change**: simple-backtesting
**Created**: 2026-03-22
**Updated**: 2026-03-22 (architecture change: worker runs on host, not Docker)
**Total tasks**: 16 (across 5 phases)
**Estimated sessions**: 4-6

---

## Phase 1: Foundation (Data Model + Schemas)

Everything downstream depends on the DB tables and Pydantic schemas existing first.

### Task 1.1: SQLAlchemy Models — BacktestJob and BacktestResult [x]

**File**: `tools/db/models.py` (modify)
**Refs**: REQ-DM-01..13, design §Data Model Design

Add two model classes at the bottom of `tools/db/models.py`, following the existing pattern (`Mapped`, `mapped_column`, `Base`, `TimestampMixin` from `.base`):

- `BacktestJob(Base, TimestampMixin)` — `__tablename__ = "backtest_jobs"`
  - `id: Mapped[int]` (PK)
  - `draft_strat_code: Mapped[int]` (FK → `drafts.strat_code`)
  - `symbol: Mapped[str]` — `String(20)`
  - `timeframe: Mapped[str]` — `String(10)`
  - `start_date: Mapped[str]` — `String(10)` (YYYY-MM-DD)
  - `end_date: Mapped[str]` — `String(10)`
  - `status: Mapped[str]` — `String(20)`, default `"pending"`
  - `error_message: Mapped[Optional[str]]` — `Text`, nullable
  - `started_at: Mapped[Optional[datetime]]` — `DateTime(timezone=True)`, nullable
  - `completed_at: Mapped[Optional[datetime]]` — `DateTime(timezone=True)`, nullable
  - `result` relationship → `BacktestResult`, `uselist=False`, `cascade="all, delete-orphan"`

- `BacktestResult(Base)` — `__tablename__ = "backtest_results"`
  - `id: Mapped[int]` (PK)
  - `job_id: Mapped[int]` (FK → `backtest_jobs.id`, `ondelete="CASCADE"`, unique)
  - `metrics: Mapped[dict]` — `JSONB`
  - `trades: Mapped[list]` — `JSONB`, `server_default="[]"`
  - `created_at: Mapped[datetime]` — `DateTime(timezone=True)`, `server_default=func.now()`
  - `job` relationship → `BacktestJob`

**Imports to add**: `func` from `sqlalchemy` (if not already imported).

**Verification**: Models import cleanly — `python -c "from tools.db.models import BacktestJob, BacktestResult"`.

---

### Task 1.2: Alembic Migration — 007_add_backtesting.py [x]

**File**: `api/alembic/versions/007_add_backtesting.py` (create)
**Refs**: REQ-DM-14..15, design §Alembic Migration
**Pattern**: Follow `006_add_instruments_table.py` structure.

```
revision = "007"
down_revision = "006"
```

`upgrade()`:
1. Create `backtest_jobs` table with all columns from Task 1.1.
2. Add `CHECK` constraint on `status` column: `status IN ('pending','running','completed','failed')` (REQ-DM-01).
3. Add `CHECK` constraint: `start_date < end_date` (REQ-DM-03).
4. Create composite index on `(status, created_at)` for worker polling (REQ-DM-05).
5. Create index on `draft_strat_code` for listing backtests per draft.
6. Create `backtest_results` table with FK to `backtest_jobs.id` (`ON DELETE CASCADE`), unique constraint on `job_id`.

`downgrade()`:
1. Drop `backtest_results` first (REQ-DM-15).
2. Drop `backtest_jobs` second.

**Verification**: `docker compose run api alembic upgrade head` succeeds; `alembic downgrade 006` cleans up.

---

### Task 1.3: Pydantic Schemas [x]

**File**: `api/models/schemas/backtest.py` (create)
**Refs**: REQ-API-22, design §Pydantic Schemas
**Pattern**: Follow `api/models/schemas/draft.py` — `BaseModel`, `ConfigDict(from_attributes=True)`.

Define:
- `BacktestCreateRequest` — `draft_strat_code: int`, `symbol: str`, `timeframe: str = "1h"`, `start_date: str`, `end_date: str`
- `BacktestResultResponse` — `id: int`, `metrics: dict[str, Any]`, `trades: list[dict[str, Any]]`, `created_at: datetime` + `ConfigDict(from_attributes=True)`
- `BacktestJobResponse` — all job fields + `result: BacktestResultResponse | None = None` + `ConfigDict(from_attributes=True)`
- `BacktestJobSummary` — job fields without result (for list endpoint)
- `BacktestListResponse` — `total: int`, `jobs: list[BacktestJobSummary]`

**Verification**: Schemas import cleanly; sample data round-trips.

---

## Phase 2: Worker (Host Process)

The worker runs directly on the host machine (not in Docker). It polls the IRT API for pending jobs, exports draft data to a temp file, calls the backtest engine via subprocess, and parses results back.

### Task 2.1: Worker Environment Config [x]

**File**: `worker/.env` (create)
**File**: `worker/config.py` (create)
**File**: `worker/__init__.py` (create, empty)
**Refs**: REQ-WK-02, REQ-WK-12, REQ-WK-13

Create a `.env` file with the following keys (and sensible defaults):
- `IRT_API_URL` — URL of the IRT API, default `http://localhost:8000`
- `WORKER_POLL_INTERVAL` — seconds between polls, default `5`
- `WORKER_JOB_TIMEOUT` — subprocess timeout in seconds, default `300`
- `HIST_DATA_PATH` — absolute path to historical data directory on the host (e.g., `C:/Users/Pablo Nieto/Desktop/PopFinance/data_futuros`)
- `ENGINE_PATH` — absolute path to the backtest engine entry point on the host (e.g., `C:/Users/Pablo Nieto/codigos/ops-worker-v0.1.0/packages/backtest-engine/main.py`)

Create `config.py` with a `Config` dataclass or simple class that reads from `.env` (using `python-dotenv` or `os.environ`):
- `api_url: str`
- `poll_interval: int`
- `job_timeout: int`
- `hist_data_path: str`
- `engine_path: str`

**Verification**: `python -c "from worker.config import Config"` works.

---

### Task 2.2: Worker Poll Loop [x]

**File**: `worker/main.py` (create)
**Refs**: REQ-WK-01..07, REQ-WK-21..23

Implement:
- `_running` global flag, `_shutdown(signum, frame)` handler for SIGTERM/SIGINT.
- `claim_next_job(api_url)` — call `GET {api_url}/api/backtests?status=pending` to find next pending job. If found, call `PATCH {api_url}/api/backtests/{job_id}/claim` (or use a dedicated claim endpoint) to atomically transition to `running`. Return job dict or `None`.
  - **Alternative (direct DB)**: If the worker has DB access, use psycopg2 with atomic claim SQL (`UPDATE ... WHERE ... FOR UPDATE SKIP LOCKED RETURNING *`). Choose one approach based on whether we want the worker to talk to API or DB directly.
- `main()` loop: claim → `execute_backtest_job()` → sleep if no work. Log config on startup (REQ-WK-22), log state transitions (REQ-WK-23).
- Entry point: `if __name__ == "__main__": main()` and module runnable via `python -m worker.main`.

**Verification**: Worker starts, logs config, polls, exits cleanly on Ctrl+C.

---

### Task 2.3: Draft Export Bridge [x]

**File**: `worker/bridge.py` (create)
**Refs**: REQ-WK-08..10, design §Job Bridge

Implement `export_draft_to_file(job: dict, api_url: str) -> str`:

1. **Fetch draft data**: `GET {api_url}/api/drafts/{draft_strat_code}` to retrieve draft JSONB data. If not found or error → raise exception to mark job `failed` (REQ-WK-10).
2. **Write temp file**: Write the draft JSONB `data` field to a temp JSON file at `{temp_dir}/irt-backtests/{strat_code}.json` (REQ-WK-09). Use `tempfile` or a fixed path under the worker directory.
3. **Return** the path to the temp file directory (the `--strategies-path` arg for the engine).

**Verification**: Given a mock draft response, produces a valid JSON file on disk.

---

### Task 2.4: Engine Runner [x]

**File**: `worker/engine.py` (create)
**Refs**: REQ-WK-11..15, design §Job Bridge

Implement `run_engine(job: dict, strategies_path: str, config: Config) -> dict`:

1. **Build CLI args**: `python {config.engine_path} --mode single --strategy {strat_code} --start {start_date} --end {end_date} --metrics-json --hist-data-path {config.hist_data_path} --strategies-path {strategies_path}` (REQ-WK-11).
2. **Execute subprocess**: `subprocess.run(cmd, capture_output=True, text=True, timeout=config.job_timeout)` (REQ-WK-13..14).
3. **Parse output**: Extract JSON between `###METRICS_JSON_START###` and `###METRICS_JSON_END###` markers from stdout. Handle missing markers, malformed JSON (REQ-WK-15).
4. **Return** parsed metrics dict on success; raise exception with stderr (last 2000 chars) on failure.

**Verification**: Unit test with mocked subprocess — happy path returns parsed metrics; failure path raises with error details.

---

### Task 2.5: Result Reporter and Job Executor [x]

**File**: `worker/executor.py` (create)
**Refs**: REQ-WK-16..20

Implement `execute_backtest_job(job: dict, config: Config)`:

1. **Export draft** → call `export_draft_to_file(job, config.api_url)`.
2. **Run engine** → call `run_engine(job, strategies_path, config)`.
3. **Report results**: `POST {config.api_url}/api/backtests/{job_id}/results` with parsed metrics and trades (REQ-WK-16). Update job status to `completed` + `completed_at`.
4. **On failure**: Update job status to `failed` + `error_message` (last 2000 chars of stderr) via `PATCH {config.api_url}/api/backtests/{job_id}` (REQ-WK-17..18).
5. **Cleanup**: Remove temp strategy file in `finally` block (REQ-WK-20).
6. **Error wrapper**: Catch all exceptions, mark job failed, log traceback, continue (REQ-WK-19).

**Verification**: Integration test — happy path: draft exported, engine run, results posted. Failure path: job marked failed with error message.

---

## Phase 3: API Layer

Depends on Phase 1 (models + schemas). Independent of Phase 2 (worker).

### Task 3.1: Backtest Service Layer [x]

**File**: `api/services/backtest_service.py` (create)
**Refs**: REQ-API-23..24, design §Service Layer
**Pattern**: Follow `api/services/strategy_service.py` — async functions, `AsyncSession`, `HTTPException` for errors.

Implement:
- `create_job(db, body: BacktestCreateRequest) -> dict` — validate draft exists (404), validate strategy `status='validated'` + `todo_count=0` (422), validate `start_date < end_date` (422), INSERT job, return dict.
- `get_job(db, job_id: int) -> dict` — SELECT with `joinedload(BacktestJob.result)`, 404 if not found.
- `list_jobs(db, draft_strat_code: int | None, status: str | None) -> dict` — SELECT ordered by `created_at DESC`, include results via joinedload, return `{total, jobs}`.
- `cancel_job(db, job_id: int) -> None` — 404 if not found, 409 if `status='running'`, DELETE row (cascade handles results).

**Imports**: `BacktestJob`, `BacktestResult` from `tools.db.models`; `Draft`, `Strategy` for validation joins.

**Verification**: Service functions work with a test async session.

---

### Task 3.2: Backtests Router [x]

**File**: `api/routers/backtests.py` (create)
**Refs**: REQ-API-01..21, design §Router
**Pattern**: Follow `api/routers/strategies.py`.

```python
router = APIRouter(prefix="/api/backtests", tags=["backtests"])
```

Endpoints:
- `POST ""` (201) → `backtest_service.create_job(db, body)`
- `GET ""` → `backtest_service.list_jobs(db, draft_strat_code, status)` — both query params optional
- `GET "/{job_id}"` → `backtest_service.get_job(db, job_id)`
- `DELETE "/{job_id}"` (204) → `backtest_service.cancel_job(db, job_id)`

**Verification**: Endpoints show up in OpenAPI docs (`/docs`).

---

### Task 3.3: Register Router in main.py [x]

**File**: `api/main.py` (modify)
**Refs**: REQ-API-01

Two changes:
1. Add import: `from api.routers import ..., backtests` (line 16).
2. Add registration: `app.include_router(backtests.router)` (after line 79).

**Verification**: `GET /api/backtests` returns `{"total": 0, "jobs": []}` (or empty list behavior).

---

## Phase 4: Frontend

Depends on Phase 3 (API must be live to test). Can be developed in parallel if mocking API.

### Task 4.1: TypeScript Types [x]

**File**: `frontend/src/types/backtest.ts` (create)
**Refs**: REQ-FE-03, design §TypeScript Types

Define and export:
- `BacktestMetrics` — `net_pnl`, `win_rate`, `max_drawdown`, `sharpe_ratio`, `total_trades` + index signature `[key: string]: unknown`
- `BacktestTrade` — `entry_date`, `exit_date`, `direction`, `entry_price`, `exit_price`, `pnl`
- `BacktestResult` — `id`, `metrics: BacktestMetrics`, `trades: BacktestTrade[]`, `created_at`
- `BacktestJob` — all job fields + `result: BacktestResult | null`
- `BacktestListResponse` — `total`, `jobs: BacktestJob[]`
- `CreateBacktestParams` — `draft_strat_code`, `symbol`, `timeframe?`, `start_date`, `end_date`

**Verification**: Types compile without errors.

---

### Task 4.2: API Client Service [x]

**File**: `frontend/src/services/backtests.ts` (create)
**Refs**: REQ-FE-01..02, design §API Client
**Pattern**: Follow `frontend/src/services/strategies.ts` — import `api` from `./api`.

Export functions:
- `createBacktest(params: CreateBacktestParams): Promise<BacktestJob>` — `POST /backtests`
- `getBacktest(jobId: number): Promise<BacktestJob>` — `GET /backtests/{jobId}`
- `getBacktestsByDraft(stratCode: number): Promise<BacktestListResponse>` — `GET /backtests?draft_strat_code={code}`
- `deleteBacktest(jobId: number): Promise<void>` — `DELETE /backtests/{jobId}`

**Verification**: Functions compile; manual API call returns expected shape.

---

### Task 4.3: BacktestPanel Component [x]

**File**: `frontend/src/components/strategies/BacktestPanel.tsx` (create)
**Refs**: REQ-FE-04..23, design §BacktestPanel Component

Props: `{ stratCode: number; backtestable: boolean; defaultSymbol?: string }`

Implement states:
1. **Disabled state** (REQ-FE-08): When `backtestable=false`, show message explaining prerequisites.
2. **Trigger form** (REQ-FE-07): Symbol input (pre-filled), timeframe dropdown (`1m|5m|15m|30m|1h|4h|1d`), start/end date inputs, "Run Backtest" button. Client-side date validation (REQ-FE-10).
3. **Job history list** (REQ-FE-12..14): `useQuery` fetching `getBacktestsByDraft(stratCode)`. Status badges with color coding. Delete button for pending jobs. Polling via `refetchInterval: 3000` when any job is pending/running (REQ-FE-15..16).
4. **Results display** (REQ-FE-18): Metrics cards grid (Net PnL, Win Rate, Max Drawdown, Sharpe, Total Trades) with color coding. Collapsible trades table.
5. **Error display** (REQ-FE-19): Red alert box for failed jobs showing `error_message`.
6. **Empty state** (REQ-FE-21): "No backtests yet" message.

Use `useMutation` for `createBacktest`, invalidate `['backtests', stratCode]` on success (REQ-FE-11).

**Verification**: Component renders in all states; form submits; polling works.

---

### Task 4.4: Integrate BacktestPanel into DraftViewer [x]

**File**: `frontend/src/components/strategies/DraftViewer.tsx` (modify)
**Refs**: REQ-FE-06

Two changes:
1. Add import: `import BacktestPanel from './BacktestPanel';` (near line 13).
2. Add a new `SectionPanel` after the Notes section (after line ~209):

```tsx
<SectionPanel id="backtest" title="Backtest" icon={'🧪'}>
  <BacktestPanel
    stratCode={draft.strat_code}
    backtestable={draft.todo_count === 0}
    defaultSymbol={parsed?.symbol}
  />
</SectionPanel>
```

The `backtestable` prop should also check strategy status if available in the draft detail response. If not available, `todo_count === 0` is the minimum gate (the API will enforce the full validation).

**Verification**: DraftViewer shows Backtest section; clicking "Run Backtest" triggers API call.

---

## Phase 5: Verification

Manual E2E checklist after all phases are deployed.

### Task 5.1: Database Verification

- [ ] Run `alembic upgrade head` — both tables created
- [ ] Verify CHECK constraint rejects invalid status values
- [ ] Verify CHECK constraint rejects `start_date >= end_date`
- [ ] Verify FK from `backtest_jobs.draft_strat_code` → `drafts.strat_code`
- [ ] Verify cascade delete from `backtest_jobs` → `backtest_results`
- [ ] Run `alembic downgrade 006` — both tables dropped cleanly

### Task 5.2: Worker Verification

- [ ] `python -m worker.main` — process starts, logs config
- [ ] Worker polls IRT API without errors when no pending jobs
- [ ] Worker shuts down cleanly on Ctrl+C
- [ ] Worker picks up a pending job and transitions it to running
- [ ] Worker exports draft JSONB to temp file correctly
- [ ] Worker calls backtest engine subprocess with correct args
- [ ] Worker parses `--metrics-json` output and posts results back to API

### Task 5.3: API Verification

- [ ] `POST /api/backtests` with valid draft → 201, job created with `status=pending`
- [ ] `POST /api/backtests` with non-existent draft → 404
- [ ] `POST /api/backtests` with draft that has `todo_count > 0` → 422
- [ ] `POST /api/backtests` with `start_date > end_date` → 422
- [ ] `GET /api/backtests?draft_strat_code=X` → lists jobs for draft
- [ ] `GET /api/backtests/{id}` → returns job with results when completed
- [ ] `DELETE /api/backtests/{id}` on pending job → 204
- [ ] `DELETE /api/backtests/{id}` on running job → 409

### Task 5.4: E2E Flow Verification

- [ ] Open a validated draft with `todo_count=0` in the frontend
- [ ] Backtest section visible with enabled form
- [ ] Fill symbol, date range, click "Run Backtest"
- [ ] Job appears in list with `pending` status badge
- [ ] Worker picks up job, status transitions to `running`
- [ ] On completion, metrics cards display (PnL, Win Rate, Drawdown, Sharpe, Total Trades)
- [ ] Trades table is expandable and shows trade details
- [ ] Failed job shows error message in red alert
- [ ] Non-backtestable draft shows disabled state with explanation message
- [ ] Multiple sequential backtests work without conflicts

---

## Implementation Order

```
Phase 1 (Foundation)
  1.1 SQLAlchemy Models    ← start here
  1.2 Alembic Migration    ← depends on 1.1
  1.3 Pydantic Schemas     ← parallel with 1.2

Phase 2 (Worker)           ← depends on 1.1 (models) + 3.x (API endpoints)
  2.1 Environment Config   ← start here
  2.2 Poll Loop            ← depends on 2.1
  2.3 Draft Export Bridge  ← depends on 2.1
  2.4 Engine Runner        ← depends on 2.1
  2.5 Result Reporter      ← depends on 2.3 + 2.4

Phase 3 (API)              ← depends on 1.1 + 1.3
  3.1 Service Layer        ← start here
  3.2 Router               ← depends on 3.1
  3.3 Register Router      ← depends on 3.2

Phase 4 (Frontend)         ← depends on 3.3
  4.1 TypeScript Types     ← start here
  4.2 API Client           ← depends on 4.1
  4.3 BacktestPanel        ← depends on 4.2
  4.4 DraftViewer Integration ← depends on 4.3

Phase 5 (Verification)     ← depends on all above
  5.1 DB Verification
  5.2 Worker Verification
  5.3 API Verification
  5.4 E2E Flow Verification
```

**Parallelism**: Phase 3 (API) can start immediately after Phase 1. Phase 2 (Worker) should start after Phase 3 is complete since the worker calls the API. Phase 4 can start types/client while Phase 3 is finishing.

---

## Open Questions (from design)

- **Hist data file naming**: Confirm engine's `market_data.py` maps draft symbol (e.g., `MNQ`) to file name (e.g., `@MNQ_1M.txt`). May require symbol translation in the bridge.
- **Trades in metrics JSON**: Verify whether `--metrics-json` output includes the trades array or only summary metrics. If trades are not in stdout output, the initial implementation may be metrics-only.
- **Worker-API communication**: Decide whether the worker talks to the IRT API via HTTP or connects directly to the DB. API approach is cleaner (no DB credentials on host); direct DB is simpler for atomic job claiming. Current tasks assume API approach.
