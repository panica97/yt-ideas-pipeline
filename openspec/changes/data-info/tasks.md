# Tasks: Data Info — Scan Worker Historical Data

**Change:** data-info (Phase 12.3)
**Date:** 2026-03-29

> Tasks marked ~~strikethrough~~ are already done and should be skipped.

---

## Phase 1: Database & Models (Foundation)

- [x] ~~1.1 Add `data_from` and `data_to` columns to `Instrument` model in `tools/db/models.py`~~ *(done)*
- [x] ~~1.2 Add `data_from` and `data_to` to `InstrumentResponse` schema in `api/models/schemas/instrument.py`~~ *(done)*
- [x] ~~1.3 Create Alembic migration 013 for `data_from`/`data_to` on instruments table~~ *(done)*
- [ ] 1.4 Add `ScanJob` SQLAlchemy model to `tools/db/models.py` with columns: `id` (SERIAL PK), `status` (VARCHAR(20), default `'pending'`), `created_at` (TIMESTAMPTZ, default now()), `started_at` (TIMESTAMPTZ, nullable), `completed_at` (TIMESTAMPTZ, nullable), `error_message` (TEXT, nullable), `results` (JSONB, nullable)
- [ ] 1.5 Create Alembic migration `api/alembic/versions/014_add_scan_jobs_table.py` — creates `scan_jobs` table matching the model in 1.4. Downgrade drops the table.

## Phase 2: API Schemas & Service (Backend Logic)

- [ ] 2.1 Create `api/models/schemas/data_info.py` with Pydantic schemas: `ScanResult` (symbol, data_from, data_to), `ScanResultsRequest` (results: list[ScanResult]), `ScanJobResponse` (id, status, created_at, started_at, completed_at, error_message, results), `ScanFailRequest` (error_message: str)
- [ ] 2.2 Create `api/services/data_info_service.py` with async functions:
  - `create_scan_job(db)` — insert new ScanJob if no pending/running exists, else raise HTTP 409
  - `get_scan_job(db, job_id)` — fetch by id, raise HTTP 404 if missing
  - `get_pending_scan_job(db)` — return oldest pending job or None
  - `claim_scan_job(db, job_id)` — transition pending->running + set started_at, raise HTTP 409 if not pending
  - `complete_scan_job(db, job_id, results)` — update instruments' data_from/data_to by matching symbol, store results JSONB, transition to completed, raise HTTP 409 if not running. Skip unmatched symbols with a log warning.
  - `fail_scan_job(db, job_id, error_message)` — transition running->failed + set completed_at and error_message, raise HTTP 409 if not running

## Phase 3: API Endpoints (Wiring)

- [ ] 3.1 Add scan-data endpoints to `api/routers/instruments.py`:
  - `POST /api/instruments/scan-data` — calls `create_scan_job`, returns 201
  - `GET /api/instruments/scan-data/pending` — calls `get_pending_scan_job`, returns 204 if none
  - `GET /api/instruments/scan-data/{job_id}` — calls `get_scan_job`
  - `PATCH /api/instruments/scan-data/{job_id}/claim` — calls `claim_scan_job`
  - `POST /api/instruments/scan-data/{job_id}/results` — calls `complete_scan_job`
  - `PATCH /api/instruments/scan-data/{job_id}/fail` — calls `fail_scan_job`
- [ ] 3.2 Import `data_info` schemas in router; ensure `/scan-data/pending` route is registered BEFORE `/{job_id}` to avoid path parameter conflicts

## Phase 4: Worker Scanner Module (Core Logic)

- [ ] 4.1 Create `worker/data_info.py` with function `execute_scan_job(job: dict, config: Config) -> None`:
  - **File discovery**: scan `config.hist_data_path` for files matching `{symbol}_1M_edit.txt`, `{symbol}_1M.txt`, `{symbol}.csv` (in priority order). For each symbol, use the highest-priority file found.
  - **Symbol mapping**: extract symbol from filename portion before `_1M` or `.csv`, strip leading `@`.
  - **Date extraction**: read first non-header line for `data_from`, seek to end and read last line for `data_to`. Try formats: `MM/DD/YYYY HH:MM`, `DD/MM/YYYY HH:MM`, ISO 8601. Skip files with unparseable dates (log warning, continue).
  - **Header detection**: if first line's first character is non-numeric or contains common header keywords, skip to second line.
  - **Result reporting**: POST bulk results to `/api/instruments/scan-data/{job_id}/results`.
  - **Failure reporting**: if `hist_data_path` does not exist or is not a directory, PATCH `/api/instruments/scan-data/{job_id}/fail` with descriptive error.

## Phase 5: Worker Orchestrator Integration (Wiring)

- [ ] 5.1 Modify `worker/orchestrator.py` `_claim_all_pending()` (or add a parallel method `_claim_pending_scan_jobs()`) to also poll `GET /api/instruments/scan-data/pending`, claim via `PATCH .../claim`, and return scan jobs separately
- [ ] 5.2 Modify `worker/orchestrator.py` `run()` poll loop to call the scan-job polling alongside the backtest polling, and dispatch scan jobs to `execute_scan_job` from `worker/data_info.py` (not `execute_backtest_job`). Scan jobs should use the same slot/thread infrastructure.
- [ ] 5.3 Import `execute_scan_job` in `worker/orchestrator.py` and add a `job_type` field or similar mechanism to `WorkUnit` so `_slot_worker` dispatches to the correct executor based on type

## Phase 6: Frontend (UI)

- [ ] 6.1 Add `data_from: string | null` and `data_to: string | null` fields to the `Instrument` interface in `frontend/src/types/instrument.ts`
- [ ] 6.2 Add `ScanJobResponse` interface to `frontend/src/types/instrument.ts` with fields: `id`, `status`, `created_at`, `started_at`, `completed_at`, `error_message`, `results`
- [ ] 6.3 Add service functions to `frontend/src/services/instruments.ts`:
  - `triggerScanData()` — `POST /api/instruments/scan-data`, returns `ScanJobResponse`
  - `getScanJobStatus(jobId: number)` — `GET /api/instruments/scan-data/{jobId}`, returns `ScanJobResponse`
- [ ] 6.4 Add `Data From` and `Data To` columns to the instruments table in `frontend/src/pages/InstrumentsPage.tsx`. Format dates as `YYYY-MM-DD`. Display `—` when null.
- [ ] 6.5 Add "Scan Data" button to the Instruments page header (next to the "New" button). On click: call `triggerScanData()`, disable button with loading spinner, poll `getScanJobStatus()` every 2s until `completed` or `failed`. On completion: invalidate instruments query. On failure: show error message. On HTTP 409: show "A scan is already in progress" message.

## Phase 7: Verification

- [ ] 7.1 Run Alembic migration 014 against dev database — verify `scan_jobs` table is created with correct columns
- [ ] 7.2 Manual API test: `POST /api/instruments/scan-data` creates a pending job, second POST returns 409
- [ ] 7.3 Manual API test: `GET /pending` returns job, `PATCH /claim` transitions to running, `POST /results` updates instruments and completes job
- [ ] 7.4 End-to-end test: trigger scan from frontend, verify worker picks up job, scans files, posts results, frontend shows updated dates
- [ ] 7.5 Edge case: verify scan with no data files completes successfully with empty results
- [ ] 7.6 Edge case: verify files with unparseable dates are skipped (not crash the scan)
