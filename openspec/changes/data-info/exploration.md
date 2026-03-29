# SDD Exploration: data-info

**Date:** 2026-03-29
**Status:** explored
**Change:** Phase 12.3 — Data Info (sub-phases 2-4)

---

## 1. Current State

### Already Done (sub-phase 1)
- `data_from` and `data_to` columns added to `Instrument` model (`tools/db/models.py:124-129`) as `DateTime(timezone=True), nullable=True`
- Alembic migration 013 applied (`api/alembic/versions/013_add_data_range_to_instruments.py`)
- `InstrumentResponse` schema already exposes `data_from` and `data_to` (`api/models/schemas/instrument.py:34-35`)
- Frontend `Instrument` type does NOT yet include `data_from`/`data_to` (`frontend/src/types/instrument.ts`)

### Existing Patterns
- **Worker polling:** `Orchestrator._claim_all_pending()` polls `GET /api/backtests/pending`, claims with `PATCH /api/backtests/{id}/claim`, then `_decompose_job()` creates `WorkUnit`(s), executed by `execute_backtest_job()` (`worker/orchestrator.py`)
- **Job lifecycle:** pending -> claimed -> running -> completed/failed. Jobs stored in `backtest_jobs` table with `mode` field (simple/complete/montecarlo)
- **Executor dispatch:** `executor.py:execute_backtest_job()` checks `job.get("mode")` to branch between backtest engine and MC engine. Data-info would need a third branch.
- **Worker config:** `Config.hist_data_path` already exists (`worker/config.py:27`)
- **Data files:** `DataPreprocessor` (`packages/backtest-engine/engine/_01_data_processor.py`) uses patterns: `{symbol}_1M_edit.txt`, `{symbol}_1M.txt`, `{symbol}.csv` in `data_folder/`
- **Symbol convention:** Data files use `@ES` prefix, Instrument table uses `ES`. Mapping = strip leading `@`.

---

## 2. Affected Areas

### Files to Create
| File | Purpose |
|------|---------|
| `worker/data_info.py` | New module: scan `HIST_DATA_PATH`, match files to symbols, read first/last dates |
| `api/services/data_info_service.py` | Service: create scan job + receive/apply results |
| `api/models/schemas/data_info.py` | Pydantic schemas for scan request/response |

### Files to Modify
| File | Change |
|------|--------|
| `worker/executor.py` | Add `data-info` mode branch that calls `data_info.scan_data_files()` instead of engine/MC |
| `api/routers/instruments.py` | Add `POST /api/instruments/scan-data` + `POST /api/instruments/scan-data/{job_id}/results` endpoints |
| `api/models/schemas/backtest.py` | Add `"data-info"` to `BacktestMode` literal (or keep separate) |
| `frontend/src/types/instrument.ts` | Add `data_from`, `data_to` fields |
| `frontend/src/pages/InstrumentsPage.tsx` | Add "Scan Data" button, date columns, loading state |
| `frontend/src/services/instruments.ts` | Add `scanData()` API call |

---

## 3. Key Design Decisions

### Decision 1: Reuse `backtest_jobs` table vs. new table

**Option A: Reuse `backtest_jobs` with new mode `"data-info"`**
- Pro: Zero schema changes, reuses polling/claim/fail infrastructure
- Con: `backtest_jobs` has required fields (`draft_strat_code`, `symbol`, `timeframe`, `start_date`, `end_date`) that are meaningless for data-info. FK constraint on `draft_strat_code -> drafts.strat_code` means we'd need a dummy draft.
- Con: `get_pending_job` returns data-info jobs to the same queue — works but semantically confusing

**Option B: Separate lightweight mechanism (direct HTTP call, no job queue)**
- Pro: Simpler — frontend calls `POST /api/instruments/scan-data`, API creates a "scan in progress" marker, worker picks it up
- Con: Still needs a polling mechanism or push

**Option C (Recommended): New `scan_jobs` table with minimal columns**
- `id`, `status` (pending/running/completed/failed), `created_at`, `started_at`, `completed_at`, `error_message`, `results` (JSONB)
- New polling endpoint `GET /api/scan-jobs/pending`
- Worker checks both `/api/backtests/pending` and `/api/scan-jobs/pending`
- Pro: Clean separation, no dummy data, no FK issues
- Con: New table + migration, new polling endpoint

**Recommendation: Option A with relaxed constraints.** The simplest path:
- Add `"data-info"` to the mode values
- Make `draft_strat_code` nullable OR use a sentinel value (e.g., `0`)
- The existing pending/claim/results/fail lifecycle works unchanged
- Worker executor just branches on `mode == "data-info"`

Actually, looking more carefully at the FK constraint (`draft_strat_code -> drafts.strat_code`), this would require a dummy draft row, which is messy.

**Revised recommendation: Option C — new `scan_jobs` table.** It's a single migration with 6 columns, and keeps the domain clean. The worker adds a second poll for scan jobs alongside backtest jobs.

### Decision 2: Lightweight file scan vs. DataPreprocessor

**Option A: Use DataPreprocessor.load_csv()**
- Pro: Reuses existing logic, handles all file patterns and date formats
- Con: Loads the ENTIRE file into memory (polars DataFrame). For 5GB+ files, this is slow and memory-heavy. We only need first/last date.

**Option B (Recommended): Lightweight file scan — read first and last lines**
- Open file, read first data line (skip header), parse date from it -> `data_from`
- Seek to end of file, read last line, parse date -> `data_to`
- Reuse file pattern matching from DataPreprocessor: `{symbol}_1M_edit.txt`, `{symbol}_1M.txt`, `{symbol}.csv`
- Reuse date parsing format detection (try MM/DD/YYYY then DD/MM/YYYY then ISO)
- Pro: Fast (O(1) per file regardless of size), low memory
- Con: Must replicate some parsing logic

**Recommendation: Option B.** The scan should complete in seconds, not minutes.

### Decision 3: Symbol mapping

Data files: `@ES_1M_edit.txt` -> symbol = `@ES`
Instruments table: `ES`

**Mapping rule:** Strip leading `@` from the filename-extracted symbol, then match against `instruments.symbol`.

This is consistent with how the backtest engine uses `@ES` internally but users see `ES`.

The worker should:
1. List all `*_1M_edit.txt`, `*_1M.txt`, `*.csv` files in `HIST_DATA_PATH`
2. Extract symbol from filename (part before `_1M` or `.csv`)
3. Strip `@` prefix
4. Match against instruments returned by the API
5. For matched instruments, read first/last dates from the file

### Decision 4: Worker result reporting

**Option A: Single bulk POST with all results**
- Worker scans all files, collects `{symbol: {data_from, data_to}}` map, POSTs once
- Pro: Simple, atomic
- Con: If scan partially fails, no results are saved

**Option B (Recommended): Single bulk POST**
- `POST /api/instruments/scan-data/{job_id}/results` with body `{results: [{symbol, data_from, data_to}, ...]}`
- API iterates and updates each matching instrument
- Pro: One round-trip, simple error handling
- Partial failures logged but non-fatal

### Decision 5: Frontend polling for scan status

The frontend needs to know when a scan completes to refresh the instruments list.

**Option A (Recommended): Simple poll**
- After clicking "Scan Data", frontend calls `POST /api/instruments/scan-data` which returns the job ID
- Frontend polls `GET /api/instruments/scan-data/{job_id}` every 2s until status is completed/failed
- On completion, invalidate instruments query to refresh table

**Option B: Optimistic + timer**
- Fire and forget, auto-refresh instruments after 5s
- Simpler but less reliable

---

## 4. Recommended Approach

### Architecture Flow

```
Frontend                    API                           Worker
   |                         |                              |
   |-- POST /scan-data ----->|                              |
   |<-- {job_id, pending} ---|                              |
   |                         |                              |
   |                         |<-- GET /scan-jobs/pending ---|  (poll loop)
   |                         |--- job data --------------->|
   |                         |                              |
   |                         |<-- PATCH /scan-jobs/{id}/claim
   |                         |--- claimed ----------------->|
   |                         |                              |
   |                         |                    [scan HIST_DATA_PATH]
   |                         |                    [read first/last dates]
   |                         |                    [match to instruments]
   |                         |                              |
   |                         |<-- POST /scan-jobs/{id}/results
   |                         |    {results: [{symbol, data_from, data_to}]}
   |                         |                              |
   |                         |  [update instruments.data_from/data_to]
   |                         |  [mark job completed]        |
   |                         |                              |
   |-- GET /scan-jobs/{id} ->|                              |
   |<-- {status: completed} -|                              |
   |                         |                              |
   |-- GET /instruments ---->|   (refresh table)            |
   |<-- instruments w/ dates |                              |
```

### Implementation Order

1. **DB migration:** New `scan_jobs` table (id, status, created_at, started_at, completed_at, error_message, results JSONB)
2. **API schemas:** `ScanJobResponse`, `ScanResultsRequest`
3. **API service:** `data_info_service.py` — create job, claim, receive results (update instruments), get status
4. **API endpoints:** Add to `instruments.py` router: `POST /scan-data`, `GET /scan-data/{id}`, `PATCH /scan-data/{id}/claim`, `POST /scan-data/{id}/results`
5. **Worker scanner:** `worker/data_info.py` — file discovery, first/last date extraction, result reporting
6. **Worker integration:** Update `orchestrator.py` to also poll `/api/instruments/scan-data/pending`, update `executor.py` to dispatch data-info jobs
7. **Frontend type:** Add `data_from`/`data_to` to `Instrument` type
8. **Frontend UI:** "Scan Data" button + date columns + polling logic

---

## 5. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Date parsing from first/last line may fail for unusual formats | Medium | Reuse DataPreprocessor's format detection logic; log warnings per file |
| `HIST_DATA_PATH` may be empty or misconfigured on worker | Low | Worker returns empty results; API handles gracefully |
| Large number of files could slow scan | Low | Scan is O(N) with N = number of instruments (~10-20 typically); each file read is O(1) |
| Race condition: two scan jobs running simultaneously | Low | Only allow one pending/running scan job at a time (reject if exists) |
| Worker must poll two endpoints now | Low | Minimal change to orchestrator poll loop; scan jobs are rare |
| New migration required for `scan_jobs` table | Low | Simple table, no complex constraints |

---

## 6. Estimated Scope

| Component | Files | Complexity |
|-----------|-------|------------|
| DB migration | 1 new | Low |
| API schemas | 1 new | Low |
| API service | 1 new | Medium |
| API endpoints | 1 modified | Medium |
| Worker scanner | 1 new | Medium |
| Worker integration | 2 modified | Medium |
| Frontend type | 1 modified | Low |
| Frontend UI | 2 modified | Medium |
| **Total** | **~6 new + 5 modified** | **Medium overall** |

---

## 7. Alternative Considered and Rejected

**Reusing `backtest_jobs` table:** Initially considered adding `"data-info"` as a mode, but the FK constraint on `draft_strat_code` and the required fields (`symbol`, `timeframe`, `start_date`, `end_date`) make this awkward. A dedicated `scan_jobs` table is cleaner and only costs one simple migration.

**Using DataPreprocessor for full file load:** Rejected due to performance. Loading multi-GB CSV files just to read first/last date is wasteful. A lightweight seek-based approach is better.

**WebSocket for real-time scan status:** Over-engineering for a scan that takes 1-2 seconds. Simple polling is sufficient.
