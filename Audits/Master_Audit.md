# Master Audit - IRT Project

**Last updated**: 2026-03-23

---

## Audit History

| Audit | Date | Scope | Findings | HIGH | MEDIUM | LOW | Resolved |
|-------|------|-------|----------|------|--------|-----|----------|
| [audit_01](audit_01.md) | 2026-03-22 | Full codebase | 30 | 0 | 0 | 1 | 29 |
| [audit_02](audit_02.md) | 2026-03-22 | Phase 10 Backtesting | 18 | 3 | 9 | 6 | 3 |
| [audit_03_quick](audit_03_quick.md) | 2026-03-23 | Phase 10.3 Frontend Backtest (quick) | 6 | 0 | 3 | 3 | 0 |

---

## Open Findings Summary

### HIGH (0 open)

_No open HIGH findings._

### MEDIUM (12 open)

| # | Finding | Source |
|---|---------|--------|
| 04 | No input validation on `BacktestCreateRequest` | audit_02 |
| 05 | Status filter accepts arbitrary strings | audit_02 |
| 06 | `backtest_jobs`/`backtest_results` missing from health check | audit_02 |
| 07 | Temp directory never cleaned up | audit_02 |
| 08 | `get_pending_job` response model conflict | audit_02 |
| 09 | `backtestable` prop only checks `todo_count` | audit_02 |
| 10 | No pagination on backtest list | audit_02 |
| 11 | Delete mutation has no error handling | audit_02 |
| 12 | No stale job recovery mechanism | audit_02 |
| 19 | Return/DD ratio misleading with signed values | audit_03 |
| 20 | Unsafe type assertion for optional metrics fields | audit_03 |
| 21 | Equity curve date sorting relies on string parsing | audit_03 |

### LOW (10 open)

| # | Finding | Source |
|---|---------|--------|
| 30 | No test suite | audit_01 |
| 13 | `body: Any` type hint on `create_job` | audit_02 |
| 14 | Duplicate `total_trades` / `trade_count` fields | audit_02 |
| 15 | `formatRelativeTime` should be in shared utils | audit_02 |
| 16 | Dates stored as strings instead of Date type | audit_02 |
| 17 | Fragile Python executable resolution | audit_02 |
| 18 | Subprocess security not documented | audit_02 |
| 22 | XAxis date labels overlap on dense data | audit_03 |
| 23 | Index signature weakens BacktestMetrics type safety | audit_03 |
| 24 | Tooltip formatter untyped (Recharts limitation) | audit_03 |

---

## Open Action Items

| # | Source | Severity | Action Item | Route | Status |
|---|--------|----------|-------------|-------|--------|
| 1 | audit_02 H-01 | HIGH | Add `SELECT FOR UPDATE` to `claim_job` | quick fix | Resolved (2026-03-22) |
| 2 | audit_02 H-02 | HIGH | Add status validation to `complete_job`/`fail_job` | quick fix | Resolved (2026-03-22) |
| 3 | audit_02 H-03 | HIGH | Evaluate worker endpoint auth separation | quick fix | Resolved (2026-03-22) |
| 4 | audit_02 M-04 | MEDIUM | Add Pydantic validators to `BacktestCreateRequest` | quick fix | Open |
| 5 | audit_02 M-05 | MEDIUM | Use `Literal` for status filter | quick fix | Open |
| 6 | audit_02 M-06 | MEDIUM | Add backtest tables to health check | quick fix | Open |
| 7 | audit_02 M-07 | MEDIUM | Use `TemporaryDirectory` context manager | quick fix | Open |
| 8 | audit_02 M-08 | MEDIUM | Fix `get_pending_job` response model | quick fix | Open |
| 9 | audit_02 M-09 | MEDIUM | Improve `backtestable` check in DraftViewer | quick fix | Open |
| 10 | audit_02 M-10 | MEDIUM | Add pagination to backtest list | quick fix | Open |
| 11 | audit_02 M-11 | MEDIUM | Add `onError` to delete mutation | quick fix | Open |
| 12 | audit_02 M-12 | MEDIUM | Design stale job recovery | /sdd-new | Open |
| 13 | audit_03 M-01 | MEDIUM | Normalize Return/DD ratio with `Math.abs()` | quick fix | Open |
| 14 | audit_03 M-02 | MEDIUM | Add `typeof === 'number'` runtime checks for metrics | quick fix | Open |
| 15 | audit_03 M-03 | MEDIUM | Add NaN guard on equity curve date parsing | quick fix | Open |

---

## Resolved Findings

| # | Severity | Finding | Source | Resolved In |
|---|----------|---------|--------|-------------|
| 01 | HIGH | Default API key in source code | audit_01 | 7d6c636 |
| 02 | HIGH | API key in WebSocket query param (log leakage) | audit_01 | 7d6c636 |
| 03 | HIGH | Health endpoint returns 200 when DB is down | audit_01 | 7d6c636 |
| 04 | HIGH | No rate limiting on any endpoint | audit_01 | 7d6c636 |
| 05 | HIGH | Dual auth mechanism (middleware + dependency) | audit_01 | 7d6c636 |
| 07 | MEDIUM | Unused `inspect` import | audit_01 | 7d6c636 |
| 08 | MEDIUM | `fill_todo` overwrites non-TODO fields | audit_01 | 7d6c636 |
| 09 | MEDIUM | History sort param silent fallback | audit_01 | 7d6c636 |
| 10 | MEDIUM | `instruments` missing from health check tables | audit_01 | 7d6c636 |
| 11 | MEDIUM | flush() without commit() pattern fragility | audit_01 | 7d6c636 |
| 13 | MEDIUM | JSONB columns typed as dict but default to list | audit_01 | 7d6c636 |
| 14 | MEDIUM | `formatDuration` duplicated 4x | audit_01 | 7d6c636 |
| 15 | MEDIUM | `any` type in DraftViewer | audit_01 | 7d6c636 |
| 16 | MEDIUM | No Error Boundary | audit_01 | 7d6c636 |
| 17 | MEDIUM | WebSocket unlimited retries | audit_01 | 7d6c636 |
| 18 | MEDIUM | API key in localStorage | audit_01 | 7d6c636 |
| 19 | MEDIUM | PostgreSQL port exposed to host | audit_01 | 7d6c636 |
| 20 | MEDIUM | No Docker health checks for api/frontend | audit_01 | 7d6c636 |
| 21 | MEDIUM | Nginx missing security headers/limits | audit_01 | 7d6c636 |
| 22 | LOW | Duplicated `_extract_todo_fields` | audit_01 | 7d6c636 |
| 23 | LOW | Unused import (dup of 07) | audit_01 | 7d6c636 |
| 24 | LOW | Last-channel guard undocumented | audit_01 | 7d6c636 |
| 25 | LOW | No favicon/meta tags | audit_01 | 7d6c636 |
| 26 | LOW | No-op channel filter in HistoryPage | audit_01 | 7d6c636 |
| 27 | LOW | Root Dockerfile unclear | audit_01 | 7d6c636 |
| 28 | LOW | `node_modules` in project root | audit_01 | 7d6c636 |
| 06 | MEDIUM | No pagination on strategies list | audit_01 | 56926fb |
| 29 | LOW | `onupdate` only for ORM ops | audit_01 | 7d6c636 |
| 01 | HIGH | `claim_job` race condition — no row-level locking | audit_02 | 2026-03-22 |
| 02 | HIGH | `complete_job`/`fail_job` skip status validation | audit_02 | 2026-03-22 |
| 03 | HIGH | Worker endpoints auth documented as trade-off | audit_02 | 2026-03-22 |

---

## Aggregate Statistics

| Metric | Value |
|---|---|
| Total audits | 3 |
| Total findings (all time) | 54 |
| Open findings | 22 |
| Resolved findings | 32 |
| Resolution rate | 59% |
