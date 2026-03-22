# Spec: backtest/api

**Change**: simple-backtesting
**Domain**: api
**Type**: FULL (new domain, no prior spec)

---

## 1. Overview

A new FastAPI router (`api/routers/backtests.py`) exposes REST endpoints for creating, listing, retrieving, and canceling backtest jobs. A new service module (`api/services/backtest_service.py`) encapsulates business logic. The router follows existing patterns from `strategies.py` -- prefix-based routing, async SQLAlchemy sessions via `Depends(get_db)`, Pydantic v2 response models.

---

## 2. Requirements

### 2.1 Router Registration

**REQ-API-01**: The backtests router MUST be registered in `api/routers/__init__.py` with prefix `/api/backtests` and tag `"backtests"`.

**REQ-API-02**: The router MUST use `APIRouter(prefix="/api/backtests", tags=["backtests"])`.

### 2.2 POST /api/backtests -- Create Backtest Job

**REQ-API-03**: The endpoint MUST accept a JSON body with the following schema:

```json
{
  "draft_strat_code": 1001,
  "symbol": "ES",
  "timeframe": "1h",
  "start_date": "2025-01-01",
  "end_date": "2025-06-01"
}
```

All fields are required.

**REQ-API-04**: The endpoint MUST validate that the referenced draft exists. If not, return `404` with detail `"Draft not found"`.

**REQ-API-05**: The endpoint MUST validate that the draft is backtestable:
- The parent strategy's `status` MUST be `"validated"`
- The draft's `todo_count` MUST be `0`

If either condition fails, return `422` with detail `"Draft is not backtestable: strategy must be validated and draft must have no pending TODOs"`.

**REQ-API-06**: `start_date` MUST be before `end_date`. If not, return `422` with detail `"start_date must be before end_date"`.

**REQ-API-07**: On success, the endpoint MUST insert a row into `backtest_jobs` with `status='pending'` and return status `201` with the created job object.

**REQ-API-08**: The response schema for a created job MUST include: `id`, `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`, `status`, `created_at`.

### 2.3 GET /api/backtests -- List Backtest Jobs

**REQ-API-09**: The endpoint MUST return a list of backtest jobs, ordered by `created_at DESC` (newest first).

**REQ-API-10**: The endpoint MUST support an optional query parameter `draft_strat_code` (integer) to filter jobs for a specific draft.

**REQ-API-11**: The endpoint MUST support optional query parameter `status` (string) to filter by job status.

**REQ-API-12**: The response MUST follow the existing list pattern:

```json
{
  "total": 5,
  "jobs": [...]
}
```

**REQ-API-13**: Each job in the list MUST include: `id`, `draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`, `status`, `error_message` (if failed), `created_at`, `started_at`, `completed_at`.

### 2.4 GET /api/backtests/{job_id} -- Get Job Detail

**REQ-API-14**: The endpoint MUST return the full job object including results if `status='completed'`.

**REQ-API-15**: If the job has associated `backtest_results`, the response MUST include a `results` field containing `metrics` and `trades`.

**REQ-API-16**: If the job does not exist, return `404` with detail `"Backtest job not found"`.

**REQ-API-17**: The response schema for a detailed job:

```json
{
  "id": 1,
  "draft_strat_code": 1001,
  "symbol": "ES",
  "timeframe": "1h",
  "start_date": "2025-01-01",
  "end_date": "2025-06-01",
  "status": "completed",
  "error_message": null,
  "created_at": "2025-03-20T10:00:00Z",
  "started_at": "2025-03-20T10:00:05Z",
  "completed_at": "2025-03-20T10:02:30Z",
  "results": {
    "metrics": {
      "net_pnl": 1250.50,
      "win_rate": 0.62,
      "max_drawdown": -3200.00,
      "sharpe_ratio": 1.45,
      "total_trades": 48
    },
    "trades": [...]
  }
}
```

### 2.5 DELETE /api/backtests/{job_id} -- Cancel or Remove Job

**REQ-API-18**: If the job `status` is `pending`, the endpoint MUST delete the job row and return `204 No Content`.

**REQ-API-19**: If the job `status` is `running`, the endpoint MUST return `409 Conflict` with detail `"Cannot delete a running backtest job"`. The worker must finish or fail it.

**REQ-API-20**: If the job `status` is `completed` or `failed`, the endpoint MUST delete the job row (and cascade-delete the results) and return `204 No Content`.

**REQ-API-21**: If the job does not exist, return `404` with detail `"Backtest job not found"`.

### 2.6 Pydantic Schemas

**REQ-API-22**: Request and response schemas MUST be defined in `api/models/schemas/backtest.py`:

- `BacktestCreateRequest`: `draft_strat_code` (int), `symbol` (str), `timeframe` (str), `start_date` (date), `end_date` (date)
- `BacktestJobResponse`: all job fields + optional `results` field
- `BacktestJobSummary`: job fields without results (for list endpoint)
- `BacktestResultResponse`: `metrics` (dict), `trades` (list[dict])
- `BacktestListResponse`: `total` (int), `jobs` (list[BacktestJobSummary])

### 2.7 Service Layer

**REQ-API-23**: Business logic MUST be in `api/services/backtest_service.py`, following the pattern of `strategy_service.py`. The router MUST NOT contain direct SQLAlchemy queries.

**REQ-API-24**: The service MUST use async SQLAlchemy session (`AsyncSession`) consistent with the existing API service pattern.

---

## 3. Acceptance Scenarios

### Scenario API-S1: Create Backtest -- Happy Path

```
Given a strategy with status='validated' exists
And a draft with strat_code=1001, todo_count=0 belongs to that strategy
When POST /api/backtests is called with:
  {"draft_strat_code": 1001, "symbol": "ES", "timeframe": "1h", "start_date": "2025-01-01", "end_date": "2025-06-01"}
Then the response status MUST be 201
And the response body MUST contain id, status='pending', created_at
And a row MUST exist in backtest_jobs with the provided values
```

### Scenario API-S2: Create Backtest -- Draft Not Found

```
Given no draft with strat_code=9999 exists
When POST /api/backtests is called with draft_strat_code=9999
Then the response status MUST be 404
And the detail MUST be "Draft not found"
```

### Scenario API-S3: Create Backtest -- Draft Not Backtestable (TODOs Pending)

```
Given a draft with strat_code=1001 and todo_count=3 exists
When POST /api/backtests is called with draft_strat_code=1001
Then the response status MUST be 422
And the detail MUST indicate the draft is not backtestable
```

### Scenario API-S4: Create Backtest -- Strategy Not Validated

```
Given a strategy with status='pending'
And a draft with strat_code=1001, todo_count=0 belongs to that strategy
When POST /api/backtests is called with draft_strat_code=1001
Then the response status MUST be 422
And the detail MUST indicate the draft is not backtestable
```

### Scenario API-S5: Create Backtest -- Invalid Date Range

```
When POST /api/backtests is called with start_date='2025-06-01' and end_date='2025-01-01'
Then the response status MUST be 422
And the detail MUST indicate start_date must be before end_date
```

### Scenario API-S6: List Backtests -- All

```
Given 3 backtest_jobs exist
When GET /api/backtests is called
Then the response MUST contain total=3 and 3 job objects
And jobs MUST be ordered by created_at DESC
```

### Scenario API-S7: List Backtests -- Filter by Draft

```
Given 2 backtest_jobs exist for draft_strat_code=1001 and 1 for draft_strat_code=1002
When GET /api/backtests?draft_strat_code=1001 is called
Then the response MUST contain total=2 and only jobs for strat_code=1001
```

### Scenario API-S8: List Backtests -- Filter by Status

```
Given 2 completed and 1 pending backtest_jobs exist
When GET /api/backtests?status=completed is called
Then the response MUST contain total=2 and only completed jobs
```

### Scenario API-S9: Get Job Detail -- Completed with Results

```
Given a backtest_job with id=1, status='completed'
And backtest_results with job_id=1, metrics={...}, trades=[...]
When GET /api/backtests/1 is called
Then the response MUST contain the job fields plus a results object with metrics and trades
```

### Scenario API-S10: Get Job Detail -- Pending (No Results)

```
Given a backtest_job with id=2, status='pending'
When GET /api/backtests/2 is called
Then the response MUST contain the job fields with results=null
```

### Scenario API-S11: Get Job Detail -- Not Found

```
When GET /api/backtests/999 is called
Then the response status MUST be 404
```

### Scenario API-S12: Delete Pending Job

```
Given a backtest_job with id=1, status='pending'
When DELETE /api/backtests/1 is called
Then the response status MUST be 204
And the row MUST be deleted from backtest_jobs
```

### Scenario API-S13: Delete Running Job -- Rejected

```
Given a backtest_job with id=1, status='running'
When DELETE /api/backtests/1 is called
Then the response status MUST be 409
And the job MUST NOT be deleted
```

### Scenario API-S14: Delete Completed Job with Results

```
Given a backtest_job with id=1, status='completed' and associated backtest_results
When DELETE /api/backtests/1 is called
Then the response status MUST be 204
And both the job and results rows MUST be deleted (cascade)
```

### Scenario API-S15: Delete Non-Existent Job

```
When DELETE /api/backtests/999 is called
Then the response status MUST be 404
```
