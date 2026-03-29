# Proposal: Data Info — Scan Worker Historical Data Files

## Intent

Users need visibility into the date ranges of historical data available per instrument so they can make informed decisions when configuring backtests. Currently, `data_from` and `data_to` columns exist on the Instrument model but are never populated. This change adds the mechanism to scan the worker's `HIST_DATA_PATH` directory, extract first/last dates from each data file, and surface them in the frontend Instruments table.

## Scope

### In Scope
- New `scan_jobs` DB table + Alembic migration for tracking scan job lifecycle
- API endpoints for creating, claiming, polling, and receiving scan job results
- Worker module to scan `HIST_DATA_PATH` files, extract first/last dates (lightweight seek-based, not full load)
- Worker orchestrator integration to poll and execute scan jobs alongside backtest jobs
- Frontend: `data_from`/`data_to` fields in Instrument type and columns in Instruments table
- Frontend: "Scan Data" button with polling-based status feedback

### Out of Scope
- Automatic/scheduled scans (manual trigger only for now)
- Per-instrument scan (always scans all files)
- WebSocket-based real-time status updates (simple polling is sufficient)
- Reusing `backtest_jobs` table (rejected due to FK constraints — see exploration)

## Approach

1. **New `scan_jobs` table** with minimal columns (`id`, `status`, `created_at`, `started_at`, `completed_at`, `error_message`, `results` JSONB). Avoids polluting `backtest_jobs` which has FK constraints on `draft_strat_code`.

2. **API layer** adds endpoints under the instruments router:
   - `POST /api/instruments/scan-data` — create a pending scan job (reject if one already pending/running)
   - `GET /api/instruments/scan-data/{job_id}` — poll job status
   - `GET /api/instruments/scan-data/pending` — worker polls for pending jobs
   - `PATCH /api/instruments/scan-data/{job_id}/claim` — worker claims a job
   - `POST /api/instruments/scan-data/{job_id}/results` — worker posts results, API updates instruments

3. **Worker scanner** (`worker/data_info.py`):
   - Discovers files matching `{symbol}_1M_edit.txt`, `{symbol}_1M.txt`, `{symbol}.csv` patterns
   - Reads first data line + last line (seek-based, O(1) per file) to extract dates
   - Maps `@ES` file prefix to `ES` instrument symbol (strip `@`)
   - Posts bulk results to API

4. **Worker orchestrator** adds a second poll for scan jobs in the main loop, dispatching to the data-info scanner instead of the backtest engine.

5. **Frontend** adds `data_from`/`data_to` to the Instrument type, renders date columns in the table, and provides a "Scan Data" button that creates a job and polls until completion.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `api/alembic/versions/014_*.py` | New | Migration for `scan_jobs` table |
| `api/models/scan_job.py` | New | SQLAlchemy model for `scan_jobs` |
| `api/models/schemas/data_info.py` | New | Pydantic schemas: `ScanJobResponse`, `ScanResultsRequest` |
| `api/services/data_info_service.py` | New | Service: create/claim/complete scan jobs, update instruments |
| `worker/data_info.py` | New | File scanner: discover, read dates, report results |
| `api/routers/instruments.py` | Modified | Add scan-data endpoints |
| `worker/executor.py` | Modified | Add `data-info` dispatch branch |
| `worker/orchestrator.py` | Modified | Add scan job polling alongside backtest polling |
| `frontend/src/types/instrument.ts` | Modified | Add `data_from`, `data_to` fields |
| `frontend/src/pages/InstrumentsPage.tsx` | Modified | "Scan Data" button, date columns, polling state |
| `frontend/src/services/instruments.ts` | Modified | Add `scanData()`, `getScanStatus()` API calls |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Date parsing fails for unusual file formats | Medium | Reuse DataPreprocessor's format detection logic (try multiple formats); log warnings per file, skip on failure |
| `HIST_DATA_PATH` empty or misconfigured | Low | Worker returns empty results array; API handles gracefully |
| Two scan jobs triggered simultaneously | Low | API rejects new scan if one is already pending/running |
| Worker must poll two endpoints | Low | Minimal change to orchestrator loop; scan jobs are infrequent |

## Rollback Plan

1. Revert the Alembic migration (downgrade removes `scan_jobs` table)
2. Revert API endpoint additions in `instruments.py` router
3. Revert worker changes in `orchestrator.py` and `executor.py`
4. Revert frontend changes (button, columns, service calls)
5. `data_from`/`data_to` columns on Instrument model remain (already deployed in migration 013) but stay null — no harm

## Dependencies

- Migration 013 already applied (adds `data_from`/`data_to` to instruments) — prerequisite satisfied
- Worker must have `HIST_DATA_PATH` configured and accessible
- No external library additions required

## Success Criteria

- [ ] "Scan Data" button on Instruments page creates a scan job and shows loading state
- [ ] Worker picks up scan job, reads first/last dates from all matching data files in `HIST_DATA_PATH`
- [ ] Instruments table displays populated `data_from` and `data_to` columns after scan completes
- [ ] Scan completes in under 5 seconds for typical deployments (~10-20 instruments)
- [ ] Duplicate scan requests are rejected while one is in progress
- [ ] Files with unparseable dates are skipped with a warning, not crashing the scan
