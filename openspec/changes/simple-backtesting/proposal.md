# Proposal: simple-backtesting

## Intent

Integrate the existing backtest engine (ops-worker-v0.1.0) into the IRT Docker stack as a worker service, enabling quantitative validation of strategies discovered by the research pipeline using historical futures data. The engine already exists and works -- this change wires it into IRT's infrastructure (DB job queue, API, frontend).

## Scope

### In scope
- New PostgreSQL tables (`backtest_jobs`, `backtest_results`) with Alembic migration
- Worker Docker service that bundles `backtest-engine` + `ibkr-core`, polls jobs from DB
- Job bridge: export `drafts.data` JSONB to temp JSON files, build CLI args, parse `--metrics-json` output, write results back to DB
- API endpoints: trigger backtest, check job status, retrieve results
- Frontend: trigger backtests from draft view, display results (metrics + trade list)
- Volume mount for historical price data (`C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros`)

### Out of scope
- Building a new backtest engine (using existing ops-worker-v0.1.0)
- Portfolio mode (multi-strategy backtests) -- single strategy only for now
- Strategy optimization or parameter sweeping
- Live/paper trading integration
- Real-time data feeds
- Custom indicator development

## Approach

**DB-based job queue with a Docker worker service (5 sub-phases)**

### Sub-phase 1: Data Model

Add two tables via Alembic migration (`006_add_backtesting.py`):

**`backtest_jobs`**: `id` (PK), `draft_strat_code` (FK to drafts), `symbol`, `timeframe`, `start_date`, `end_date`, `status` (enum: pending/running/completed/failed), `error_message`, `created_at`, `started_at`, `completed_at`

**`backtest_results`**: `id` (PK), `job_id` (FK to backtest_jobs, unique), `metrics` (JSONB -- net_pnl, win_rate, max_drawdown, sharpe, total_trades, etc.), `trades` (JSONB -- array of individual trades), `created_at`

New SQLAlchemy models in `api/models/backtest.py`. New Pydantic schemas in `api/models/schemas/backtest.py`.

### Sub-phase 2: Worker Service

- New `worker/` directory at project root with its own `Dockerfile`
- Bundle `packages/backtest-engine/` and `packages/ibkr-core/` from ops-worker-v0.1.0 into the image
- Install dependencies: TA-Lib, pandas, numpy
- Poll loop: query `backtest_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1`, set to `running`, execute, set to `completed`/`failed`
- New service in `docker-compose.yml` with volume mounts for historical data and shared DB connection
- Graceful shutdown on SIGTERM

### Sub-phase 3: Job Bridge

- Export `drafts.data` JSONB to a temp JSON file on disk (engine expects file path via ibkr-core StratOBJ loader)
- Build CLI command: `python main.py --mode single --strategy {strat_code} --start {start} --end {end} --metrics-json`
- Parse JSON metrics output from engine stdout
- Write parsed metrics + trades to `backtest_results` table
- Clean up temp files after execution

### Sub-phase 4: API Endpoints

New router `api/routers/backtests.py`:
- `POST /api/backtests` -- create a backtest job (validates draft is backtestable: status=validated, todo_count=0)
- `GET /api/backtests/{job_id}` -- get job status + results
- `GET /api/backtests?draft_strat_code={code}` -- list backtests for a draft
- `DELETE /api/backtests/{job_id}` -- cancel a pending job

### Sub-phase 5: Frontend

- New `BacktestPanel` component in draft view -- trigger button, symbol/date range inputs, status indicator
- Results display: key metrics cards (PnL, win rate, drawdown, Sharpe), trades table
- Uses existing React Query patterns for polling job status until completion

## Affected Areas

| File / Directory | Change |
|-----------------|--------|
| `api/models/backtest.py` | New -- SQLAlchemy models for backtest_jobs, backtest_results |
| `api/models/schemas/backtest.py` | New -- Pydantic request/response schemas |
| `api/routers/backtests.py` | New -- REST endpoints for backtest CRUD |
| `api/routers/__init__.py` | Modified -- register backtests router |
| `api/alembic/versions/006_add_backtesting.py` | New -- migration for both tables |
| `worker/` | New directory -- Dockerfile, poll loop, job bridge logic |
| `worker/Dockerfile` | New -- Python 3.12 + TA-Lib + engine bundles |
| `worker/bridge.py` | New -- draft export, CLI execution, result parsing |
| `worker/poll.py` | New -- DB polling loop with graceful shutdown |
| `docker-compose.yml` | Modified -- add worker service, hist_data volume mount |
| `frontend/src/components/strategies/BacktestPanel.tsx` | New -- backtest trigger + results UI |
| `frontend/src/components/strategies/DraftViewer.tsx` | Modified -- integrate BacktestPanel |
| `frontend/src/lib/api.ts` | Modified -- add backtest API functions |

## Risks

1. **TA-Lib installation in Docker** -- TA-Lib requires system-level C library compilation. The worker Dockerfile must install `ta-lib` from source before `pip install TA-Lib`. Medium risk; well-documented pattern but adds build time.
2. **Engine bundling** -- Copying `backtest-engine` and `ibkr-core` packages into the worker image requires careful dependency resolution. The engine was developed outside IRT and may have implicit dependencies. Medium risk.
3. **Volume mount path** -- Historical data lives at a Windows host path (`C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros`). This is dev-only; production deployment would need a different data strategy. Low risk for dev, flagged for later.
4. **Job race conditions** -- Multiple worker instances could pick the same pending job. Mitigated by `UPDATE ... WHERE status = 'pending' RETURNING id` atomic claim pattern. Low risk.
5. **Large result payloads** -- Backtests with many trades could produce large JSONB blobs in `backtest_results.trades`. May need pagination or summary-only mode later. Low risk for initial implementation.

## Rollback

1. Drop migration: `alembic downgrade -1` removes `backtest_jobs` and `backtest_results` tables
2. Remove `worker/` directory entirely
3. Revert `docker-compose.yml` to remove worker service
4. Remove `api/routers/backtests.py`, `api/models/backtest.py`, `api/models/schemas/backtest.py`
5. Revert frontend files (`BacktestPanel.tsx`, `DraftViewer.tsx`, `api.ts`)

No data loss -- backtesting tables are new and independent of existing strategy/draft data.

## Success Criteria

- User can open a validated draft (status=validated, todo_count=0) and trigger a backtest with symbol and date range
- Worker picks up the job, runs the engine, and stores results in the DB
- API returns job status (pending/running/completed/failed) and results when complete
- Frontend displays key metrics (net PnL, win rate, max drawdown, Sharpe ratio, total trades)
- Frontend shows a table of individual trades from the backtest
- Multiple backtests can run sequentially without conflicts
- Worker service starts/stops cleanly with `docker compose up/down`
