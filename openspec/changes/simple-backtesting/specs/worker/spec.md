# Spec: backtest/worker

**Change**: simple-backtesting
**Domain**: worker
**Type**: FULL (new domain, no prior spec)

---

## 1. Overview

The backtest worker is a standalone Python process running in its own Docker container. It polls the `backtest_jobs` table for pending jobs, claims them atomically, executes the backtest engine as a subprocess, parses the output, and writes results back to the database. The worker runs as a long-lived service alongside the existing API and frontend containers.

---

## 2. Requirements

### 2.1 Polling Behavior

**REQ-WK-01**: The worker MUST poll `backtest_jobs` for rows with `status = 'pending'` ordered by `created_at ASC` (FIFO).

**REQ-WK-02**: The polling interval MUST be configurable via the `WORKER_POLL_INTERVAL` environment variable, defaulting to 5 seconds.

**REQ-WK-03**: The worker MUST process one job at a time (single-threaded execution). It MUST NOT pick up a new job while one is running.

**REQ-WK-04**: Between poll cycles with no pending jobs, the worker MUST sleep for the configured interval to avoid busy-waiting.

### 2.2 Job Claim Pattern

**REQ-WK-05**: The worker MUST claim a job atomically using an `UPDATE ... WHERE ... RETURNING` pattern to prevent race conditions if multiple worker instances exist:

```sql
UPDATE backtest_jobs
SET status = 'running', started_at = now()
WHERE id = (
    SELECT id FROM backtest_jobs
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

**REQ-WK-06**: If the atomic claim returns no rows, the worker MUST treat it as "no work available" and continue polling.

**REQ-WK-07**: `started_at` MUST be set to the current timestamp when the job transitions to `running`.

### 2.3 Job Bridge (Draft Export)

**REQ-WK-08**: Before executing the engine, the worker MUST export the draft's `data` JSONB field to a temporary JSON file on disk. The engine expects strategy definitions as files loadable by ibkr-core's StratOBJ loader.

**REQ-WK-09**: The temporary file MUST be written to a dedicated temp directory (e.g., `/tmp/irt-backtests/`) and MUST be named using the `strat_code` to avoid collisions: `{strat_code}.json`.

**REQ-WK-10**: The worker MUST fetch the draft data by joining `backtest_jobs.draft_strat_code` to `drafts.strat_code`. If the draft no longer exists, the job MUST be marked as `failed` with an appropriate error message.

### 2.4 Engine Execution

**REQ-WK-11**: The worker MUST invoke the backtest engine as a subprocess with the following CLI pattern:

```
python main.py --mode single --strategy {strat_code} --start {start_date} --end {end_date} --metrics-json --hist-data-path {hist_data_dir} --strategies-path {strategies_dir}
```

Where:
- `{strat_code}` is the draft's strat_code
- `{start_date}` and `{end_date}` are from the job record (ISO format YYYY-MM-DD)
- `{hist_data_dir}` is the mounted historical data volume path
- `{strategies_dir}` is the temp directory containing the exported strategy JSON

**REQ-WK-12**: The engine paths MUST be configurable via environment variables:
- `HIST_DATA_PATH`: path to historical price data (default: `/data/hist`)
- `ENGINE_PATH`: path to the engine's `main.py` (default: `/app/engine/main.py`)

**REQ-WK-13**: The subprocess MUST have a configurable timeout via `WORKER_JOB_TIMEOUT` environment variable (default: 300 seconds / 5 minutes). If the timeout is exceeded, the process MUST be killed and the job marked as `failed`.

**REQ-WK-14**: The worker MUST capture both stdout and stderr from the subprocess. Stdout contains the metrics JSON output; stderr contains log messages.

### 2.5 Result Parsing and Storage

**REQ-WK-15**: When the engine exits with code 0 and `--metrics-json` flag is set, the worker MUST parse the JSON output from stdout. The output is a JSON object containing metrics and optionally a trades array.

**REQ-WK-16**: The worker MUST insert a row into `backtest_results` with:
- `job_id`: the current job's id
- `metrics`: the parsed metrics JSON object
- `trades`: the parsed trades array (or empty array if not present)

**REQ-WK-17**: After successful result storage, the worker MUST update the job: `status = 'completed'`, `completed_at = now()`.

### 2.6 Error Handling

**REQ-WK-18**: If the engine subprocess exits with a non-zero code, the worker MUST:
1. Set `status = 'failed'`
2. Set `completed_at = now()`
3. Set `error_message` to the last 2000 characters of stderr (to avoid unbounded storage)

**REQ-WK-19**: If any unexpected exception occurs during job processing (DB error, file I/O error, JSON parse error), the worker MUST:
1. Mark the job as `failed` with the exception message
2. Log the full traceback
3. Continue polling (MUST NOT crash the worker loop)

**REQ-WK-20**: The worker MUST clean up temporary strategy files after job completion, regardless of success or failure (use a `finally` block or equivalent).

### 2.7 Lifecycle

**REQ-WK-21**: The worker MUST handle `SIGTERM` gracefully: finish the currently running job (if any), then exit. It MUST NOT accept new jobs after receiving SIGTERM.

**REQ-WK-22**: On startup, the worker SHOULD log its configuration (poll interval, timeout, data paths) at INFO level.

**REQ-WK-23**: The worker MUST log each job state transition (claimed, completed, failed) at INFO level, including the job ID and duration.

### 2.8 Docker Configuration

**REQ-WK-24**: The worker MUST be defined as a new service in `docker-compose.yml` named `worker`.

**REQ-WK-25**: The worker service MUST depend on `postgres` with `condition: service_healthy`.

**REQ-WK-26**: The worker service MUST mount the historical data directory as a read-only volume.

**REQ-WK-27**: The worker service MUST share the same `DATABASE_URL_SYNC` connection string pattern as the `pipeline` service (sync psycopg2 driver, since the worker uses synchronous DB access).

**REQ-WK-28**: The worker's `Dockerfile` MUST install TA-Lib system library before `pip install TA-Lib`. The engine depends on TA-Lib for technical indicator computation.

---

## 3. Acceptance Scenarios

### Scenario WK-S1: Happy Path -- Job Pickup and Execution

```
Given a backtest_job exists with status='pending', draft_strat_code=1001, symbol='ES', start_date='2025-01-01', end_date='2025-06-01'
And the draft with strat_code=1001 exists with valid data
And historical data for 'ES' is available in the mounted volume
When the worker polls for pending jobs
Then it MUST atomically claim the job (status='running', started_at=now)
And export the draft data to /tmp/irt-backtests/1001.json
And invoke the engine subprocess with the correct CLI arguments
And parse the JSON metrics output from stdout
And insert a backtest_results row with the parsed metrics and trades
And update the job to status='completed', completed_at=now
And delete the temporary strategy file
```

### Scenario WK-S2: Engine Failure

```
Given a backtest_job with status='pending' and valid draft data
When the worker claims the job and the engine subprocess exits with code 1
And stderr contains "Error: insufficient data for symbol ES in date range"
Then the job MUST be updated to status='failed'
And error_message MUST contain the stderr output (truncated to 2000 chars)
And completed_at MUST be set
And the temporary strategy file MUST be cleaned up
And the worker MUST continue polling for the next job
```

### Scenario WK-S3: Draft Deleted Before Execution

```
Given a backtest_job with status='pending' and draft_strat_code=1001
And the draft with strat_code=1001 has been deleted since the job was created
When the worker claims the job and attempts to fetch the draft data
Then the job MUST be marked as failed with error_message indicating the draft no longer exists
And the worker MUST continue polling
```

### Scenario WK-S4: Job Timeout

```
Given a backtest_job with status='pending'
And WORKER_JOB_TIMEOUT is set to 10 seconds
When the worker claims the job and the engine subprocess runs for more than 10 seconds
Then the subprocess MUST be killed
And the job MUST be marked as failed with error_message indicating timeout
And completed_at MUST be set
```

### Scenario WK-S5: Race Condition Prevention

```
Given two worker instances are running
And a single backtest_job with status='pending' exists
When both workers poll simultaneously
Then exactly one worker MUST claim the job (via FOR UPDATE SKIP LOCKED)
And the other worker MUST receive no rows and continue polling
```

### Scenario WK-S6: Graceful Shutdown

```
Given the worker is currently executing a backtest job
When SIGTERM is sent to the worker process
Then the worker MUST finish the current job (do not kill the subprocess)
And MUST NOT claim any new jobs
And MUST exit with code 0 after the current job completes
```

### Scenario WK-S7: No Pending Jobs

```
Given there are no backtest_jobs with status='pending'
When the worker polls
Then no UPDATE query MUST be executed (or the UPDATE returns 0 rows)
And the worker MUST sleep for WORKER_POLL_INTERVAL seconds before polling again
```

### Scenario WK-S8: Worker Crash Recovery

```
Given a backtest_job with status='running' (worker crashed during execution)
When a new worker instance starts
Then the stale 'running' job SHOULD remain as-is (manual intervention required)
And the worker MUST only pick up 'pending' jobs
```

### Scenario WK-S9: Invalid JSON Output from Engine

```
Given the engine subprocess exits with code 0
But stdout contains malformed JSON
When the worker attempts to parse the output
Then the job MUST be marked as failed with error_message indicating JSON parse failure
And the worker MUST continue polling
```
