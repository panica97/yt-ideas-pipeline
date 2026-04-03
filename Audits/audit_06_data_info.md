# Audit 06 — Phase 12.3: Data Info

**Date:** 2026-04-02
**Scope:** Data Info scan jobs — worker scanner, API endpoints, service layer, frontend InstrumentsPage, Alembic migration
**Auditor:** Claude (automated)
**Findings:** 9

---

## Files Reviewed

- `worker/data_info.py` — File scanner, date extraction, job execution
- `api/services/data_info_service.py` — Async service for scan CRUD + worker ops
- `api/models/schemas/data_info.py` — Pydantic schemas
- `api/routers/instruments.py` — Scan-data REST endpoints
- `api/alembic/versions/014_add_scan_jobs_table.py` — Migration
- `frontend/src/pages/InstrumentsPage.tsx` — Scan button + polling
- `frontend/src/services/instruments.ts` — API client
- `frontend/src/types/instrument.ts` — TypeScript types
- `tools/db/models.py` — ScanJob SQLAlchemy model
- `worker/orchestrator.py` — Scan job polling + dispatch

---

## Findings

### MEDIUM

#### M-01: No polling timeout / max retries on frontend scan job polling

**File:** `frontend/src/pages/InstrumentsPage.tsx:68-85`
**Description:** The `setInterval` polling for scan job status runs indefinitely every 2 seconds until the job completes or fails. If the worker crashes or the scan job gets stuck in "running" status, the polling never stops. There is no maximum polling duration, retry limit, or stale-job detection.
**Severity:** MEDIUM
**Impact:** Browser continues polling forever on stuck jobs, wasting bandwidth and never updating the UI.

#### M-02: No stale scan job recovery mechanism

**File:** `api/services/data_info_service.py:24-38`
**Description:** `create_scan_job` rejects if a pending/running job exists, but there is no mechanism to time out or recover a stuck "running" scan job. If the worker crashes mid-scan, the job stays "running" forever and blocks all future scans.
**Severity:** MEDIUM
**Impact:** A single crashed scan renders the scan feature permanently blocked until manual DB intervention.

#### M-03: `complete_scan_job` does N+1 queries per symbol

**File:** `api/services/data_info_service.py:123-135`
**Description:** For each `ScanResult`, the service issues a separate `SELECT` on `Instrument` by symbol. With 50+ instruments this is 50+ queries in one request. Should batch-load all instruments and match in-memory, or use a single `WHERE symbol IN (...)` query.
**Severity:** MEDIUM
**Impact:** Slow completion for large instrument sets; each query is a DB round-trip.

#### M-04: `_read_last_line` may read partial UTF-8 at chunk boundary

**File:** `worker/data_info.py:113-134`
**Description:** Reading a 4KB binary chunk from the end of a file and decoding with `errors="replace"` can split a multi-byte UTF-8 character at the chunk boundary. This would corrupt the first characters of the chunk, potentially mangling a date string if the line happened to start at the boundary. The probability is low for ASCII-heavy CSV files, but the code is fragile for files with non-ASCII content.
**Severity:** MEDIUM
**Impact:** Rare edge case: corrupted date parsing for a symbol if the chunk boundary splits a character.

### LOW

#### L-01: ScanJob model missing `updated_at` column

**File:** `tools/db/models.py:258-275`
**Description:** Unlike `BacktestJob` which inherits `TimestampMixin`, `ScanJob` does not have `updated_at`. This means status transitions (pending -> running -> completed) are not tracked with a last-modified timestamp.
**Severity:** LOW
**Impact:** Cannot easily detect stale jobs by comparing `updated_at` vs current time.

#### L-02: No index on `scan_jobs.status` column

**File:** `api/alembic/versions/014_add_scan_jobs_table.py`
**Description:** The `scan_jobs` table has no index on `status`. The `get_pending_scan_job` and `create_scan_job` queries filter by status. With very few scan jobs this is irrelevant, but the pattern differs from `backtest_jobs` which has proper indexing.
**Severity:** LOW
**Impact:** Negligible performance impact given low scan job volume.

#### L-03: `_is_header` heuristic can mis-classify numeric-only headers

**File:** `worker/data_info.py:37-50`
**Description:** The header detection returns `True` if the first character is not a digit. A header like `"123,OPEN,HIGH"` would pass as data. Conversely, unusual date formats starting with a letter would be skipped as headers. The heuristic works for known file formats but is fragile for edge cases.
**Severity:** LOW
**Impact:** Potential mis-parse on non-standard data files.

#### L-04: Frontend `deleteMut` has no `onError` handler

**File:** `frontend/src/pages/InstrumentsPage.tsx:126-129`
**Description:** The delete mutation swallows errors silently. If instrument deletion fails, the user gets no feedback.
**Severity:** LOW
**Impact:** Silent failure on delete.

#### L-05: `_sanitize_for_json` helper duplicated across runner.py and aggregator.py in monkey-test

**File:** `packages/monkey-test/runner.py:50-63`, `packages/monkey-test/aggregator.py:123-136`
**Description:** This finding is technically about Phase 12.4, but the pattern applies here too: the `_report_scan_failure` truncates error messages to 2000 chars from the end, which may lose the root cause if the exception message has a long traceback prefix before the actual error.
**Severity:** LOW
**Impact:** Minor — error messages may lose context on truncation.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 0     |
| MEDIUM   | 4     |
| LOW      | 5     |
| **Total** | **9** |

### Key Themes

1. **No stale job recovery (M-01, M-02):** Both frontend polling and backend lack timeout/recovery for stuck scan jobs. A crashed worker blocks future scans.

2. **Performance (M-03):** N+1 query pattern in `complete_scan_job` when updating instruments with scan results.

3. **Robustness of file parsing (M-04, L-03):** The data scanner handles common CSV formats well but has edge cases with chunk-boundary UTF-8 and header detection heuristics.

4. **Minor gaps (L-01, L-02, L-04):** Missing `updated_at`, missing index, missing error handler — standard cleanup items.
