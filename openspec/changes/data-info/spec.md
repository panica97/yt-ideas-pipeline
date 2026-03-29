# Data Info — Specification

**Change:** data-info (Phase 12.3)
**Date:** 2026-03-29
**Status:** specified
**Type:** New (no existing specs for this domain)

---

## 1. API Specification

### Purpose

Endpoints for managing scan jobs that discover historical data date ranges per instrument. Mounted under the existing instruments router (`/api/instruments`).

### 1.1 Database: `scan_jobs` Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | PRIMARY KEY | Auto-incrementing job ID |
| `status` | `VARCHAR(20)` | NOT NULL, DEFAULT `'pending'` | One of: `pending`, `running`, `completed`, `failed` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | When the job was created |
| `started_at` | `TIMESTAMPTZ` | NULLABLE | When the worker claimed the job |
| `completed_at` | `TIMESTAMPTZ` | NULLABLE | When the job finished (success or failure) |
| `error_message` | `TEXT` | NULLABLE | Error details if status is `failed` |
| `results` | `JSONB` | NULLABLE | Scan results array: `[{symbol, data_from, data_to}, ...]` |

### 1.2 Pydantic Schemas

#### `ScanJobResponse`

```
{
  id: int
  status: "pending" | "running" | "completed" | "failed"
  created_at: datetime
  started_at: datetime | null
  completed_at: datetime | null
  error_message: string | null
  results: list[ScanResult] | null
}
```

#### `ScanResult`

```
{
  symbol: string
  data_from: datetime | null
  data_to: datetime | null
}
```

#### `ScanResultsRequest`

```
{
  results: list[ScanResult]
}
```

### 1.3 Requirements

#### Requirement: Create Scan Job

The system MUST allow creating a new scan job via `POST /api/instruments/scan-data`.

The system MUST reject the request with HTTP 409 if a scan job with status `pending` or `running` already exists.

The system MUST return the created job with status `pending` and HTTP 201.

##### Scenario: Successful scan job creation

- GIVEN no scan job exists with status `pending` or `running`
- WHEN a `POST /api/instruments/scan-data` request is received
- THEN the system creates a new row in `scan_jobs` with status `pending`
- AND returns HTTP 201 with a `ScanJobResponse` body

##### Scenario: Duplicate scan job rejected

- GIVEN a scan job exists with status `running`
- WHEN a `POST /api/instruments/scan-data` request is received
- THEN the system returns HTTP 409 with body `{"detail": "A scan job is already pending or running"}`
- AND no new row is created in `scan_jobs`

#### Requirement: Poll Scan Job Status

The system MUST allow polling a scan job's status via `GET /api/instruments/scan-data/{job_id}`.

The system MUST return HTTP 404 if the job ID does not exist.

##### Scenario: Poll existing job

- GIVEN a scan job with id `42` exists and has status `running`
- WHEN a `GET /api/instruments/scan-data/42` request is received
- THEN the system returns HTTP 200 with a `ScanJobResponse` showing status `running`

##### Scenario: Poll non-existent job

- GIVEN no scan job with id `999` exists
- WHEN a `GET /api/instruments/scan-data/999` request is received
- THEN the system returns HTTP 404

#### Requirement: Worker Polls for Pending Scan Jobs

The system MUST expose `GET /api/instruments/scan-data/pending` for the worker to discover pending scan jobs.

The system MUST return HTTP 204 (no content) if no pending scan jobs exist.

The system MUST return the oldest pending scan job (by `created_at`) if one exists.

##### Scenario: Pending job available

- GIVEN a scan job with status `pending` exists
- WHEN a `GET /api/instruments/scan-data/pending` request is received
- THEN the system returns HTTP 200 with a `ScanJobResponse` for the oldest pending job

##### Scenario: No pending jobs

- GIVEN no scan jobs with status `pending` exist
- WHEN a `GET /api/instruments/scan-data/pending` request is received
- THEN the system returns HTTP 204 with no body

#### Requirement: Worker Claims a Scan Job

The system MUST allow the worker to claim a pending scan job via `PATCH /api/instruments/scan-data/{job_id}/claim`.

The system MUST transition the job status from `pending` to `running` and set `started_at` to the current timestamp.

The system MUST return HTTP 409 if the job status is not `pending`.

##### Scenario: Successful claim

- GIVEN a scan job with id `42` exists and has status `pending`
- WHEN a `PATCH /api/instruments/scan-data/42/claim` request is received
- THEN the system updates the job status to `running` and sets `started_at`
- AND returns HTTP 200 with the updated `ScanJobResponse`

##### Scenario: Claim non-pending job

- GIVEN a scan job with id `42` exists and has status `running`
- WHEN a `PATCH /api/instruments/scan-data/42/claim` request is received
- THEN the system returns HTTP 409 with body `{"detail": "Job is not in pending state"}`

#### Requirement: Worker Posts Scan Results

The system MUST accept scan results via `POST /api/instruments/scan-data/{job_id}/results` with a `ScanResultsRequest` body.

The system MUST iterate over each result and update the corresponding instrument's `data_from` and `data_to` fields by matching `result.symbol` to `instruments.symbol`.

The system MUST store the full results array in the job's `results` JSONB column.

The system MUST transition the job status to `completed` and set `completed_at`.

The system SHOULD skip (not fail) results where the symbol does not match any instrument, logging a warning.

The system MUST return HTTP 409 if the job status is not `running`.

##### Scenario: Successful results submission

- GIVEN a scan job with id `42` exists and has status `running`
- AND instruments `ES` and `NQ` exist in the database
- WHEN a `POST /api/instruments/scan-data/42/results` request is received with body `{"results": [{"symbol": "ES", "data_from": "2020-01-02T00:00:00Z", "data_to": "2026-03-28T00:00:00Z"}, {"symbol": "NQ", "data_from": "2019-06-01T00:00:00Z", "data_to": "2026-03-28T00:00:00Z"}]}`
- THEN the system updates instrument `ES` with `data_from=2020-01-02` and `data_to=2026-03-28`
- AND updates instrument `NQ` with `data_from=2019-06-01` and `data_to=2026-03-28`
- AND stores the results array in the job's `results` column
- AND transitions the job to `completed` with `completed_at` set
- AND returns HTTP 200 with the updated `ScanJobResponse`

##### Scenario: Results with unmatched symbols

- GIVEN a scan job with id `42` exists and has status `running`
- AND instrument `ES` exists but `ZZ` does not
- WHEN results are posted with symbols `["ES", "ZZ"]`
- THEN the system updates instrument `ES` successfully
- AND skips `ZZ` without error (logs a warning)
- AND the job completes successfully

##### Scenario: Empty results

- GIVEN a scan job with id `42` exists and has status `running`
- WHEN results are posted with body `{"results": []}`
- THEN the system transitions the job to `completed`
- AND no instruments are updated (their `data_from`/`data_to` remain unchanged)

#### Requirement: Worker Reports Scan Failure

The system MUST allow the worker to report a scan failure via `PATCH /api/instruments/scan-data/{job_id}/fail` with body `{"error_message": "..."}`.

The system MUST transition the job status to `failed`, set `completed_at`, and store the error message.

##### Scenario: Report failure

- GIVEN a scan job with id `42` exists and has status `running`
- WHEN a `PATCH /api/instruments/scan-data/42/fail` request is received with body `{"error_message": "HIST_DATA_PATH not configured"}`
- THEN the system updates the job status to `failed`, sets `completed_at`, and stores the error message
- AND returns HTTP 200 with the updated `ScanJobResponse`

---

## 2. Worker Specification

### Purpose

A new worker module that scans the `HIST_DATA_PATH` directory for historical data files, extracts the first and last dates from each file, maps filenames to instrument symbols, and reports results back to the API.

### 2.1 Requirements

#### Requirement: File Discovery

The worker MUST scan the directory at `Config.hist_data_path` for files matching these patterns (in priority order):
1. `{symbol}_1M_edit.txt`
2. `{symbol}_1M.txt`
3. `{symbol}.csv`

For each symbol, the worker MUST use the highest-priority file found (prefer `_1M_edit.txt` over `_1M.txt` over `.csv`).

##### Scenario: Multiple file formats for same symbol

- GIVEN `HIST_DATA_PATH` contains `@ES_1M_edit.txt` and `@ES_1M.txt`
- WHEN the worker discovers files
- THEN it uses `@ES_1M_edit.txt` for symbol `ES` (highest priority)

##### Scenario: Only CSV available

- GIVEN `HIST_DATA_PATH` contains `@NQ.csv` and no `@NQ_1M_edit.txt` or `@NQ_1M.txt`
- WHEN the worker discovers files
- THEN it uses `@NQ.csv` for symbol `NQ`

##### Scenario: Empty data directory

- GIVEN `HIST_DATA_PATH` is an empty directory
- WHEN the worker discovers files
- THEN it returns an empty results list
- AND the scan job completes successfully with no instrument updates

#### Requirement: Symbol Mapping

The worker MUST extract the symbol from the filename (the portion before `_1M` or `.csv`) and strip any leading `@` character.

The mapping rule: `@ES_1M_edit.txt` -> symbol `ES`, `NQ_1M.txt` -> symbol `NQ`.

##### Scenario: Symbol with @ prefix

- GIVEN a file named `@ES_1M_edit.txt`
- WHEN the worker extracts the symbol
- THEN the mapped symbol is `ES`

##### Scenario: Symbol without @ prefix

- GIVEN a file named `CL_1M.txt`
- WHEN the worker extracts the symbol
- THEN the mapped symbol is `CL`

#### Requirement: Date Extraction

The worker MUST extract the first and last data dates from each file using a lightweight seek-based approach (not loading the full file into memory).

The worker MUST read the first non-header line to extract `data_from`.

The worker MUST seek to the end of the file and read the last line to extract `data_to`.

The worker MUST attempt multiple date formats when parsing: `MM/DD/YYYY HH:MM`, `DD/MM/YYYY HH:MM`, and ISO 8601 (`YYYY-MM-DD HH:MM:SS`).

The worker SHOULD skip files where date parsing fails, logging a warning per file, and continue scanning remaining files.

##### Scenario: Successful date extraction

- GIVEN a file `@ES_1M_edit.txt` where the first data line starts with `01/02/2020 00:00` and the last line starts with `03/28/2026 23:59`
- WHEN the worker reads dates from this file
- THEN `data_from` is `2020-01-02T00:00:00` and `data_to` is `2026-03-28T23:59:00`

##### Scenario: Unparseable date in file

- GIVEN a file `@ZB_1M.txt` where the first line contains `INVALID_DATE`
- WHEN the worker attempts to parse dates
- THEN the worker logs a warning for this file
- AND skips it (does not include `ZB` in results)
- AND continues processing other files

##### Scenario: File with header row

- GIVEN a file `@NQ_1M_edit.txt` whose first line is `Date,Open,High,Low,Close,Volume`
- WHEN the worker reads the first line
- THEN it detects the header (non-numeric first character or contains column names)
- AND reads the second line for `data_from` instead

#### Requirement: Result Reporting

The worker MUST collect all successfully parsed results into a single bulk payload and POST it to `POST /api/instruments/scan-data/{job_id}/results`.

The worker MUST call `PATCH /api/instruments/scan-data/{job_id}/fail` if an unrecoverable error occurs (e.g., `HIST_DATA_PATH` does not exist or is not readable).

##### Scenario: Successful bulk report

- GIVEN the worker has extracted dates for symbols `ES`, `NQ`, and `CL`
- WHEN all files are processed
- THEN the worker sends a single POST with `{"results": [{"symbol": "ES", "data_from": "...", "data_to": "..."}, {"symbol": "NQ", ...}, {"symbol": "CL", ...}]}`

##### Scenario: HIST_DATA_PATH does not exist

- GIVEN `Config.hist_data_path` points to a non-existent directory
- WHEN the worker starts the scan
- THEN the worker reports failure with error message `"HIST_DATA_PATH directory does not exist: /path/to/missing"`
- AND the scan job transitions to `failed`

##### Scenario: Worker cannot reach API

- GIVEN the worker has completed scanning files
- AND the API is unreachable
- WHEN the worker attempts to POST results
- THEN the worker logs the connection error
- AND the scan job remains in `running` state (no crash; the orchestrator's existing error handling applies)

#### Requirement: Orchestrator Integration

The worker orchestrator MUST poll `GET /api/instruments/scan-data/pending` in its main loop alongside `GET /api/backtests/pending`.

When a pending scan job is found, the orchestrator MUST claim it via `PATCH /api/instruments/scan-data/{job_id}/claim` and dispatch it to the data-info scanner (not the backtest executor).

##### Scenario: Scan job dispatched alongside backtest jobs

- GIVEN the orchestrator is running its poll loop
- AND there is 1 pending backtest job and 1 pending scan job
- WHEN the orchestrator polls both endpoints
- THEN it claims and dispatches the backtest job to `execute_backtest_job`
- AND claims and dispatches the scan job to the data-info scanner
- AND both execute concurrently in separate worker slots

##### Scenario: API unreachable during scan poll

- GIVEN the orchestrator is running
- AND the API is unreachable
- WHEN the orchestrator attempts to poll for scan jobs
- THEN it logs a connection error
- AND retries on the next poll cycle (same as existing backtest poll behavior)

---

## 3. Frontend Specification

### Purpose

Surface historical data date ranges in the Instruments table and provide a button to trigger a data scan.

### 3.1 Requirements

#### Requirement: Instrument Type Extension

The frontend MUST add `data_from: string | null` and `data_to: string | null` fields to the `Instrument` TypeScript type.

##### Scenario: API returns instruments with dates

- GIVEN the API returns an instrument with `data_from: "2020-01-02T00:00:00Z"` and `data_to: "2026-03-28T23:59:00Z"`
- WHEN the frontend receives the response
- THEN the `Instrument` object includes `data_from` and `data_to` as ISO date strings

##### Scenario: API returns instruments without dates

- GIVEN the API returns an instrument with `data_from: null` and `data_to: null`
- WHEN the frontend receives the response
- THEN the `Instrument` object has `data_from` and `data_to` as `null`

#### Requirement: Date Columns in Instruments Table

The frontend MUST display `Data From` and `Data To` columns in the Instruments table.

The frontend MUST format dates in a human-readable short format (e.g., `2020-01-02`).

The frontend SHOULD display a dash (`—`) or empty cell when `data_from` or `data_to` is `null`.

##### Scenario: Dates displayed after scan

- GIVEN instrument `ES` has `data_from: "2020-01-02T00:00:00Z"` and `data_to: "2026-03-28T23:59:00Z"`
- WHEN the Instruments table renders
- THEN the `Data From` column shows `2020-01-02` and the `Data To` column shows `2026-03-28`

##### Scenario: No dates available

- GIVEN instrument `GC` has `data_from: null` and `data_to: null`
- WHEN the Instruments table renders
- THEN the `Data From` and `Data To` columns display `—`

#### Requirement: Scan Data Button

The frontend MUST display a "Scan Data" button on the Instruments page.

When clicked, the button MUST call `POST /api/instruments/scan-data` to create a scan job.

The frontend MUST disable the button and show a loading indicator while a scan is in progress.

The frontend MUST poll `GET /api/instruments/scan-data/{job_id}` every 2 seconds until the job reaches `completed` or `failed` status.

On completion, the frontend MUST invalidate/refresh the instruments query to display updated dates.

On failure, the frontend MUST display an error message (from the job's `error_message` field or a generic message).

##### Scenario: Happy path — scan triggers and completes

- GIVEN the user is on the Instruments page and no scan is running
- WHEN the user clicks the "Scan Data" button
- THEN the frontend sends `POST /api/instruments/scan-data`
- AND receives a `ScanJobResponse` with status `pending` and a `job_id`
- AND the button becomes disabled with a loading spinner
- AND the frontend polls `GET /api/instruments/scan-data/{job_id}` every 2s
- AND when the poll returns status `completed`, the button re-enables
- AND the instruments table refreshes showing updated `Data From` / `Data To` values

##### Scenario: Scan already running — duplicate rejected

- GIVEN a scan job is already running
- WHEN the user clicks the "Scan Data" button
- THEN the frontend receives HTTP 409
- AND displays a message like "A scan is already in progress"
- AND the button remains enabled (no polling started)

##### Scenario: Scan fails

- GIVEN a scan job is running and the worker reports failure
- WHEN the frontend polls and receives status `failed` with `error_message: "HIST_DATA_PATH directory does not exist"`
- THEN the frontend displays the error message to the user
- AND the button re-enables

#### Requirement: API Service Functions

The frontend MUST add the following service functions to `instruments.ts`:

- `triggerScanData()` — `POST /api/instruments/scan-data`, returns `ScanJobResponse`
- `getScanJobStatus(jobId: number)` — `GET /api/instruments/scan-data/{jobId}`, returns `ScanJobResponse`

##### Scenario: Service function returns scan job

- GIVEN the API is reachable
- WHEN `triggerScanData()` is called
- THEN it returns a `ScanJobResponse` with `id`, `status`, `created_at`

---

## 4. Cross-Cutting Scenarios

### Scenario: Full Happy Path End-to-End

- GIVEN the system is running (API, worker, frontend)
- AND `HIST_DATA_PATH` contains `@ES_1M_edit.txt` and `@NQ_1M.txt`
- AND instruments `ES` and `NQ` exist in the database with `data_from: null` and `data_to: null`
- WHEN the user clicks "Scan Data" on the Instruments page
- THEN a scan job is created with status `pending`
- AND the worker picks up the job, claims it, scans the files
- AND the worker posts results: `[{symbol: "ES", data_from: "2020-01-02", data_to: "2026-03-28"}, {symbol: "NQ", data_from: "2019-06-01", data_to: "2026-03-28"}]`
- AND the API updates both instruments and marks the job `completed`
- AND the frontend poll detects completion, refreshes the table
- AND the user sees populated `Data From` and `Data To` columns

### Scenario: No Data Files Found for Some Instruments

- GIVEN instruments `ES`, `NQ`, and `GC` exist in the database
- AND `HIST_DATA_PATH` contains files for `@ES` and `@NQ` only (no `GC` files)
- WHEN a scan completes
- THEN `ES` and `NQ` get updated `data_from`/`data_to` values
- AND `GC` retains `data_from: null` and `data_to: null`
- AND the scan job still completes successfully

### Scenario: Scan Already Running — Reject Duplicate

- GIVEN a scan job with status `running` exists
- WHEN a second `POST /api/instruments/scan-data` is received
- THEN the API returns HTTP 409
- AND no new scan job is created

### Scenario: Worker Cannot Reach API During Result Reporting

- GIVEN the worker has finished scanning files and has results ready
- AND the API becomes unreachable
- WHEN the worker attempts to POST results
- THEN the worker logs the connection error
- AND the scan job remains in `running` state in the database
- AND the job does NOT crash the orchestrator (existing error handling catches the exception)
- AND a subsequent scan can be triggered once the stale job is cleaned up or times out
