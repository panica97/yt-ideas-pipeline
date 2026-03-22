# Design: Simple Backtesting Integration

## Technical Approach

Wire the existing `ops-worker-v0.1.0` backtest engine into IRT's Docker stack as a standalone worker service. The API creates jobs in PostgreSQL, the worker polls and executes them via subprocess, and the frontend provides trigger/results UI within the existing draft viewer. All new code follows IRT's established patterns: SQLAlchemy models in `tools/db/models.py`, async services, Pydantic schemas, React Query polling.

## Architecture Decisions

### Decision: PostgreSQL job queue (not Redis/Celery)

**Choice**: `backtest_jobs` table with atomic claim via `UPDATE ... WHERE status = 'pending' RETURNING id`
**Alternatives considered**: Redis + Celery, RabbitMQ, in-memory queue
**Rationale**: IRT already uses PostgreSQL as its only data store. Adding Redis/Celery introduces a new dependency for a low-throughput use case (sequential single-strategy backtests). The atomic claim pattern prevents race conditions if multiple workers ever run. Matches IRT's "minimal stack" philosophy.

### Decision: Worker as separate Docker Compose service (not API background task)

**Choice**: Dedicated `worker` service in `docker-compose.yml` with its own Dockerfile
**Alternatives considered**: FastAPI BackgroundTasks, asyncio subprocess from API process
**Rationale**: The backtest engine requires TA-Lib (C library) and has heavy CPU/memory usage. Running it inside the API process would block the event loop and require TA-Lib in the API image. Separate service isolates dependencies, allows independent scaling, and crash isolation -- a worker OOM won't take down the API.

### Decision: Subprocess execution (not in-process import)

**Choice**: Run engine via `subprocess.run(["python", "main.py", ...])` and parse stdout
**Alternatives considered**: Import engine modules directly in worker Python process
**Rationale**: The engine already has a clean CLI interface with `--metrics-json` output. Subprocess provides process-level isolation (memory cleanup on exit), avoids import conflicts between engine and worker dependencies, and uses the engine exactly as designed. The `###METRICS_JSON_START###` / `###METRICS_JSON_END###` markers make parsing reliable.

### Decision: Draft JSONB exported as temp JSON file

**Choice**: Write `drafts.data` JSONB to `/tmp/strategies/{strat_code}.json`, pass path via `--strategies-path`
**Alternatives considered**: Pipe JSON via stdin, modify engine to accept inline JSON
**Rationale**: The engine's `StratOBJ.upload()` expects a folder of `{strat_code}.json` files (line 154 of `strat_loader.py`). Writing a temp file with the strat_code as filename is the zero-modification path -- the engine loads it as-is. Temp files are cleaned up after each run.

### Decision: Synchronous worker with psycopg2 (not asyncpg)

**Choice**: Worker uses `psycopg2` (sync) for DB access, matching the existing `pipeline` service pattern
**Alternatives considered**: asyncpg with asyncio loop
**Rationale**: The worker is a sequential poll loop -- it processes one job at a time and blocks on subprocess. There's no concurrency benefit from async. The `pipeline` service already uses `DATABASE_URL_SYNC` with psycopg2. Same pattern, same connection string.

### Decision: Results stored as JSONB (not normalized tables)

**Choice**: `backtest_results.metrics` and `backtest_results.trades` as JSONB columns
**Alternatives considered**: Normalized `backtest_trades` table with typed columns
**Rationale**: The engine's metrics output is a dynamic dict (keys vary by mode). Trades are read-only after creation and always fetched as a batch for display. JSONB avoids schema coupling between engine output format and DB schema. If trade-level queries are needed later, a normalized table can be added without breaking this design.

## Data Flow

```
User clicks "Run Backtest" in DraftViewer
        │
        ▼
Frontend ──POST /api/backtests──▶ API (backtests router)
        │                              │
        │                    Validate draft exists,
        │                    status=validated, todo_count=0
        │                              │
        │                    INSERT backtest_jobs (status=pending)
        │                              │
        │                    Return job_id + status
        │                              │
        ▼                              ▼
Frontend polls                  PostgreSQL
GET /api/backtests/{id}         backtest_jobs table
every 3s while                         │
status=pending|running                 │
        │                              │
        │                     Worker poll loop (5s interval)
        │                              │
        │                     SELECT ... WHERE status='pending'
        │                     ORDER BY created_at LIMIT 1
        │                     FOR UPDATE SKIP LOCKED
        │                              │
        │                     UPDATE status='running'
        │                              │
        │                     1. Fetch draft.data from drafts table
        │                     2. Write /tmp/strategies/{code}.json
        │                     3. subprocess: python main.py
        │                        --mode single
        │                        --strategy {code}
        │                        --start {start} --end {end}
        │                        --metrics-json
        │                        --hist-data-path /data/hist
        │                        --strategies-path /tmp/strategies
        │                     4. Parse ###METRICS_JSON_START###...###METRICS_JSON_END###
        │                     5. INSERT backtest_results (metrics, trades)
        │                     6. UPDATE backtest_jobs status='completed'
        │                     7. Cleanup temp file
        │                              │
        ▼                              ▼
Frontend receives              On error:
completed status ──────────▶   UPDATE status='failed',
Displays metrics + trades      error_message = stderr/exception
```

## Data Model Design

### SQLAlchemy Models (in `tools/db/models.py`)

Following the existing pattern (mapped_column, Mapped types, TimestampMixin):

```python
class BacktestJob(Base, TimestampMixin):
    __tablename__ = "backtest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_strat_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("drafts.strat_code"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False, default="1 min")
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)    # YYYY-MM-DD
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )  # pending | running | completed | failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result: Mapped[Optional["BacktestResult"]] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("backtest_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trades: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped["BacktestJob"] = relationship(back_populates="result")
```

**Key decisions**:
- `draft_strat_code` references `drafts.strat_code` (not `drafts.id`) because strat_code is the natural key used throughout the codebase and is unique
- `start_date`/`end_date` as String(10) to match engine CLI format (YYYY-MM-DD) without date conversion overhead
- `status` as String(20) rather than PostgreSQL ENUM to avoid migration complexity on status additions (matches `ResearchSession.status` pattern)
- `relationship` between job and result enables eager loading on job fetch

### Alembic Migration (`api/alembic/versions/007_add_backtesting.py`)

Following the `006_add_instruments_table.py` pattern:

```python
revision: str = "007"
down_revision: Union[str, None] = "006"
```

Creates both tables. Foreign key from `backtest_jobs.draft_strat_code` to `drafts.strat_code`. Index on `backtest_jobs.status` for worker polling. Index on `backtest_jobs.draft_strat_code` for listing backtests per draft.

## Worker Service Design

### Dockerfile (`worker/Dockerfile`)

```dockerfile
FROM python:3.12-slim

# Install TA-Lib C library (required by TA-Lib Python package)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget && \
    wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz && \
    tar xzf ta-lib-0.6.4-src.tar.gz && \
    cd ta-lib-0.6.4 && ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib-0.6.4* && \
    apt-get purge -y build-essential wget && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy engine packages
COPY packages/backtest-engine/ /app/backtest-engine/
COPY packages/ibkr-core/ /app/ibkr-core/

# Install ibkr-core first (dependency), then backtest-engine
RUN pip install --no-cache-dir /app/ibkr-core && \
    pip install --no-cache-dir /app/backtest-engine

# Copy worker code
COPY worker/ /app/worker/

# Install worker dependencies
RUN pip install --no-cache-dir psycopg2-binary

CMD ["python", "-m", "worker.main"]
```

### docker-compose.yml entry

```yaml
worker:
  build:
    context: .
    dockerfile: worker/Dockerfile
  environment:
    DATABASE_URL_SYNC: postgresql+psycopg2://irt:${POSTGRES_PASSWORD:-irt_dev_password}@postgres:5432/irt
    POLL_INTERVAL: 5
    HIST_DATA_PATH: /data/hist
  volumes:
    - hist_data:/data/hist:ro
  depends_on:
    postgres:
      condition: service_healthy
  restart: unless-stopped
```

With a new named volume or bind mount:

```yaml
volumes:
  pgdata:
  hist_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: "C:/Users/Pablo Nieto/Desktop/PopFinance/data_futuros"
```

**Note**: The bind mount path is Windows-specific (dev only). For production, this would be a standard Docker volume or NFS mount.

### Worker Module Structure (`worker/`)

```
worker/
├── __init__.py
├── main.py          # Entry point: poll loop with graceful shutdown
├── bridge.py        # Draft export, subprocess execution, result parsing
└── config.py        # Environment variable loading
```

### Worker Poll Loop (`worker/main.py`)

```python
import signal
import time
import logging
from worker.config import Config
from worker.bridge import execute_backtest_job

logger = logging.getLogger("worker")
_running = True

def _shutdown(signum, frame):
    global _running
    logger.info("Received signal %s, shutting down...", signum)
    _running = False

def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    config = Config()
    logger.info("Worker started, polling every %ds", config.poll_interval)

    while _running:
        job = claim_next_job(config.db_url)
        if job:
            execute_backtest_job(job, config)
        else:
            time.sleep(config.poll_interval)
```

### Job Claim SQL (atomic, prevents race conditions)

```sql
UPDATE backtest_jobs
SET status = 'running', started_at = NOW()
WHERE id = (
    SELECT id FROM backtest_jobs
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, draft_strat_code, symbol, timeframe, start_date, end_date;
```

`FOR UPDATE SKIP LOCKED` ensures multiple workers (if scaled later) never claim the same job.

### Job Bridge (`worker/bridge.py`)

1. **Fetch draft data**: `SELECT data FROM drafts WHERE strat_code = {draft_strat_code}`
2. **Write temp strategy file**:
   ```python
   tmp_dir = Path("/tmp/strategies")
   tmp_dir.mkdir(exist_ok=True)
   strat_file = tmp_dir / f"{strat_code}.json"
   strat_file.write_text(json.dumps(draft_data))
   ```
3. **Build CLI command**:
   ```python
   cmd = [
       "python", "/app/backtest-engine/main.py",
       "--mode", "single",
       "--strategy", str(strat_code),
       "--start", start_date,
       "--end", end_date,
       "--metrics-json",
       "--hist-data-path", config.hist_data_path,
       "--strategies-path", str(tmp_dir),
   ]
   ```
4. **Execute subprocess**:
   ```python
   result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
   ```
   Timeout of 1 hour prevents runaway backtests.
5. **Parse metrics output**:
   ```python
   import re
   match = re.search(
       r"###METRICS_JSON_START###(.+?)###METRICS_JSON_END###",
       result.stdout
   )
   if match:
       metrics = json.loads(match.group(1))
   ```
6. **Write results to DB**: INSERT into `backtest_results` with parsed metrics
7. **Update job status**: `completed` or `failed` with error_message from stderr
8. **Cleanup**: Remove temp strategy file

### Error Handling

- **Subprocess timeout**: Set status to `failed`, error_message = "Backtest timed out after 3600s"
- **Subprocess non-zero exit**: Set status to `failed`, error_message = last 500 chars of stderr
- **No metrics marker found**: Set status to `failed`, error_message = "No metrics output found in engine stdout"
- **JSON parse error**: Set status to `failed`, error_message = "Failed to parse metrics JSON: {error}"
- **DB connection loss**: Worker crashes, `restart: unless-stopped` brings it back. Jobs left in `running` state need manual recovery (or a startup sweep that resets stale `running` jobs older than 2 hours back to `pending`)

## API Layer Design

### Router (`api/routers/backtests.py`)

Following the `strategies.py` pattern:

```python
router = APIRouter(prefix="/api/backtests", tags=["backtests"])
```

#### Endpoints

**POST /api/backtests** -- Create a backtest job

```python
@router.post("", status_code=201)
async def create_backtest(
    body: CreateBacktestRequest,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.create_job(db, body)
```

Request schema:
```python
class CreateBacktestRequest(BaseModel):
    draft_strat_code: int
    symbol: str
    timeframe: str = "1 min"
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
```

Response: `BacktestJobResponse` (see below)

Validation:
- Draft with given strat_code must exist
- Draft's parent strategy must have `status = 'validated'`
- Draft must have `todo_count = 0`
- `start_date` < `end_date`
- No existing job for this draft with `status in ('pending', 'running')` (prevent duplicate submissions)

**GET /api/backtests/{job_id}** -- Get job status + results

```python
@router.get("/{job_id}")
async def get_backtest(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.get_job(db, job_id)
```

Response includes nested `result` when status = completed.

**GET /api/backtests?draft_strat_code={code}** -- List backtests for a draft

```python
@router.get("")
async def list_backtests(
    draft_strat_code: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await backtest_service.list_jobs(db, draft_strat_code)
```

**DELETE /api/backtests/{job_id}** -- Cancel a pending job

```python
@router.delete("/{job_id}", status_code=204)
async def cancel_backtest(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    await backtest_service.cancel_job(db, job_id)
```

Only cancels if status = `pending`. Returns 409 if already running/completed.

### Pydantic Schemas (`api/models/schemas/backtest.py`)

Following the `draft.py` pattern:

```python
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Any

class CreateBacktestRequest(BaseModel):
    draft_strat_code: int
    symbol: str
    timeframe: str = "1 min"
    start_date: str
    end_date: str

class BacktestResultResponse(BaseModel):
    id: int
    metrics: dict[str, Any]
    trades: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class BacktestJobResponse(BaseModel):
    id: int
    draft_strat_code: int
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    status: str
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: BacktestResultResponse | None = None

    model_config = ConfigDict(from_attributes=True)

class BacktestListResponse(BaseModel):
    total: int
    jobs: list[BacktestJobResponse]
```

### Service Layer (`api/services/backtest_service.py`)

Following the `strategy_service.py` pattern (async functions, HTTPException for errors):

```python
async def create_job(db: AsyncSession, body: CreateBacktestRequest) -> dict:
    # 1. Validate draft exists
    # 2. Validate strategy status = validated
    # 3. Validate todo_count = 0
    # 4. Check no pending/running job for this draft
    # 5. INSERT backtest_jobs
    # 6. Return job dict

async def get_job(db: AsyncSession, job_id: int) -> dict:
    # SELECT backtest_jobs LEFT JOIN backtest_results
    # 404 if not found

async def list_jobs(db: AsyncSession, draft_strat_code: int) -> dict:
    # SELECT backtest_jobs WHERE draft_strat_code = X ORDER BY created_at DESC
    # Include result via joinedload

async def cancel_job(db: AsyncSession, job_id: int) -> None:
    # UPDATE status = 'cancelled' WHERE status = 'pending'
    # 404 if not found, 409 if not pending
```

## Frontend Design

### Component Structure

```
frontend/src/
├── components/strategies/
│   └── BacktestPanel.tsx          # NEW - main backtest UI
├── services/
│   └── backtests.ts               # NEW - API client functions
└── types/
    └── backtest.ts                # NEW - TypeScript interfaces
```

### BacktestPanel Component (`components/strategies/BacktestPanel.tsx`)

Integrates into `DraftViewer.tsx` as a new `SectionPanel` at the bottom of the sections list, after Notes:

```tsx
<SectionPanel id="backtest" title="Backtest" icon="📊">
  <BacktestPanel draft={draft} />
</SectionPanel>
```

**States**:
1. **Idle** (no running job): Shows form with symbol (pre-filled from draft), date range inputs, "Run Backtest" button. Disabled if `todo_count > 0`.
2. **Running**: Shows spinner + "Running backtest..." status. Polls `GET /api/backtests/{id}` every 3 seconds via React Query `refetchInterval`.
3. **Completed**: Shows metrics cards grid + trades table. "Run Again" button to create new job.
4. **Failed**: Shows error message + "Retry" button.
5. **History**: Below the main panel, a collapsible list of previous backtests for this draft (from `GET /api/backtests?draft_strat_code=X`).

**Metrics cards** (grid layout, matching `BacktestSection.tsx` `StatCell` pattern):
- Net PnL
- Win Rate %
- Max Drawdown
- Sharpe Ratio
- Total Trades
- Initial/Final Equity

**Trades table**: Simple table with columns: Entry Date, Exit Date, Side, Entry Price, Exit Price, PnL. Scrollable, max height.

### API Client (`services/backtests.ts`)

Following `strategies.ts` pattern:

```typescript
import api from './api';
import type { BacktestJob, BacktestListResponse } from '../types/backtest';

export async function createBacktest(params: {
  draft_strat_code: number;
  symbol: string;
  timeframe?: string;
  start_date: string;
  end_date: string;
}): Promise<BacktestJob> {
  const { data } = await api.post<BacktestJob>('/backtests', params);
  return data;
}

export async function getBacktest(jobId: number): Promise<BacktestJob> {
  const { data } = await api.get<BacktestJob>(`/backtests/${jobId}`);
  return data;
}

export async function getBacktestsByDraft(stratCode: number): Promise<BacktestListResponse> {
  const { data } = await api.get<BacktestListResponse>(`/backtests?draft_strat_code=${stratCode}`);
  return data;
}

export async function cancelBacktest(jobId: number): Promise<void> {
  await api.delete(`/backtests/${jobId}`);
}
```

### TypeScript Types (`types/backtest.ts`)

```typescript
export interface BacktestMetrics {
  total_pnl: number;
  win_rate: number;
  max_drawdown: number;
  sharpe_ratio: number;
  total_trades: number;
  trade_count: number;
  initial_equity: number | null;
  final_equity: number | null;
  [key: string]: unknown;  // engine may add fields
}

export interface BacktestTrade {
  entry_date: string;
  exit_date: string;
  side: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  [key: string]: unknown;
}

export interface BacktestResult {
  id: number;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  created_at: string;
}

export interface BacktestJob {
  id: number;
  draft_strat_code: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: BacktestResult | null;
}

export interface BacktestListResponse {
  total: number;
  jobs: BacktestJob[];
}
```

### Polling Mechanism

Uses React Query's `refetchInterval` (same pattern as `ResearchStatus.tsx` polling):

```tsx
const { data: job } = useQuery({
  queryKey: ['backtest', activeJobId],
  queryFn: () => getBacktest(activeJobId!),
  enabled: !!activeJobId,
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    // Poll every 3s while pending/running, stop when terminal
    return status === 'pending' || status === 'running' ? 3000 : false;
  },
});
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `tools/db/models.py` | Modify | Add `BacktestJob` and `BacktestResult` models |
| `api/alembic/versions/007_add_backtesting.py` | Create | Migration: create `backtest_jobs` and `backtest_results` tables with indexes |
| `api/models/schemas/backtest.py` | Create | Pydantic request/response schemas |
| `api/routers/backtests.py` | Create | REST endpoints for backtest CRUD |
| `api/services/backtest_service.py` | Create | Async service layer with validation logic |
| `api/main.py` | Modify | Import and register `backtests` router |
| `worker/__init__.py` | Create | Empty package init |
| `worker/main.py` | Create | Poll loop entry point with graceful shutdown |
| `worker/bridge.py` | Create | Draft export, subprocess execution, result parsing |
| `worker/config.py` | Create | Environment variable config class |
| `worker/Dockerfile` | Create | Python 3.12 + TA-Lib + engine packages |
| `docker-compose.yml` | Modify | Add `worker` service and `hist_data` volume |
| `frontend/src/types/backtest.ts` | Create | TypeScript interfaces for backtest API |
| `frontend/src/services/backtests.ts` | Create | API client functions |
| `frontend/src/components/strategies/BacktestPanel.tsx` | Create | Backtest trigger + results UI component |
| `frontend/src/components/strategies/DraftViewer.tsx` | Modify | Add BacktestPanel as a SectionPanel |

**Summary**: 11 new files, 4 modified files, 0 deleted files.

## Interfaces / Contracts

### Engine CLI Contract (existing, not modified)

```
python main.py \
  --mode single \
  --strategy {strat_code} \
  --start {YYYY-MM-DD} \
  --end {YYYY-MM-DD} \
  --metrics-json \
  --hist-data-path {path} \
  --strategies-path {path}
```

**Input**: Strategy JSON file at `{strategies-path}/{strat_code}.json` with structure matching `drafts.data` JSONB.

**Output**: Prints `###METRICS_JSON_START###{json}###METRICS_JSON_END###` to stdout. JSON contains at minimum: `total_pnl`, `trade_count`, `initial_equity`, `final_equity`, plus engine metrics dict.

### Worker-to-Engine File Contract

The worker writes the draft's `data` JSONB verbatim as `{strat_code}.json` into a temp directory. The engine's `StratOBJ.upload()` discovers it by scanning for `*.json` files with numeric stems.

**Critical**: The draft `data` JSONB must already be a valid strategy JSON (with `strat_code`, `strat_name`, `symbol`, `ind_list`, conditions, etc.). This is guaranteed by the existing draft creation pipeline which produces IBKR-compatible JSON via `strategy-translator`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Bridge: temp file creation, metrics parsing, cleanup | pytest with mock subprocess output |
| Unit | Service: validation logic (draft exists, status check, todo_count check, duplicate prevention) | pytest with async SQLAlchemy test session |
| Unit | Pydantic schemas: serialization/deserialization | pytest with sample data |
| Integration | Worker poll loop: claim job, execute bridge, update status | Docker Compose test with a known strategy + hist data |
| Integration | API endpoints: create/get/list/cancel flow | pytest with httpx AsyncClient against FastAPI test app |
| E2E | Full flow: create job via API, worker picks up, results appear | Manual verification via frontend after deployment |

## Migration / Rollout

### Alembic Migration

```bash
docker compose run api alembic upgrade head
```

Creates `backtest_jobs` and `backtest_results` tables. No data migration needed -- these are new tables with no dependency on existing data.

### Engine Package Bundling

The worker Dockerfile copies `packages/backtest-engine/` and `packages/ibkr-core/` from the `ops-worker-v0.1.0` directory. For the Docker build context, these packages need to be available. Two options:

1. **Copy into IRT repo** (recommended for initial dev): Copy the two package dirs into `worker/packages/` and adjust Dockerfile COPY paths
2. **Multi-stage build from external path**: Less portable but avoids duplication

Decision: Option 1 for simplicity. The packages are small and self-contained.

### Rollback

1. `alembic downgrade -1` (drops both tables)
2. Remove `worker/` directory
3. Revert `docker-compose.yml`
4. Remove new API files, revert `api/main.py`
5. Remove new frontend files, revert `DraftViewer.tsx`

No data loss -- backtesting is fully independent of existing strategy/draft data.

## Open Questions

- [ ] **Hist data file naming**: The data directory contains files like `@ES_1M.txt` and `@MNQ_1M.txt`. Need to confirm the engine's `market_data.py` can locate files for a given symbol from drafts (e.g., draft symbol `MNQ` maps to file `@MNQ_1M.txt`). This may require the worker to translate symbol names or pass additional config.
- [ ] **Trades extraction**: The engine's `--metrics-json` output includes `trade_count` but the full trades list comes from `results['trades']` in the Python return value, not the stdout JSON marker. Need to verify if trades are included in the metrics JSON or if the bridge needs to modify the engine to emit them. If not, the worker may need to import the engine in-process for trades data, or we accept metrics-only initially and add trades later.
- [ ] **Engine packages location for Docker build**: Whether to copy `ops-worker-v0.1.0/packages/` into the IRT repo under `worker/packages/` or use a Docker build context that spans both directories. Recommend copying for simplicity.
