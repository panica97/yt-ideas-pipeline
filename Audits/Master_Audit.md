# Master Audit - IRT Project

**Last updated**: 2026-03-28

---

## Audit History

| Audit | Date | Scope | Findings | HIGH | MEDIUM | LOW | Resolved |
|-------|------|-------|----------|------|--------|-----|----------|
| [audit_01](audit_01.md) | 2026-03-22 | Full codebase | 30 | 0 | 0 | 1 | 29 |
| [audit_02](audit_02.md) | 2026-03-22 | Phase 10 Backtesting | 18 | 3 | 9 | 6 | 3 |
| [audit_03_quick](audit_03_quick.md) | 2026-03-23 | Phase 10.3 Frontend Backtest (quick) | 6 | 0 | 3 | 3 | 0 |
| [audit_04](audit_04.md) | 2026-03-23 | Phase 10.2 Research Pipeline Flexibility | 9 | 0 | 6 | 3 | 9 |
| [audit_05_quick](audit_05_quick.md) | 2026-03-28 | Phase 12.2 Monte Carlo Frontend | 12 | 0 | 6 | 6 | 0 |

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
| 34 | `buildHistogramBins` quadratic O(n*bins) on large arrays | audit_05 |
| 35 | `Math.min(...values)` stack overflow on >65K elements | audit_05 |
| 36 | `percentileRank` repeated O(n) filter per scorecard row | audit_05 |
| 37 | Unsafe double cast `as unknown as MonteCarloMetrics` | audit_05 |
| 38 | `Number(undefined)` produces NaN silently in MCDistributionsGrid | audit_05 |
| 39 | Fan chart Area stacking may not produce correct visual bands | audit_05 |

### LOW (16 open)

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
| 40 | `deleteMutation` no `onError` handler (dup of audit_02 #11) | audit_05 |
| 41 | Hardcoded `nPaths=1000`, `fitYears=10` defaults | audit_05 |
| 42 | nPaths/fitYears max limits only enforced client-side | audit_05 |
| 43 | Scatter chart renders all N points without sampling | audit_05 |
| 44 | Price paths chart renders up to 30 Line components | audit_05 |
| 45 | `MetricCard` component duplicated in both files | audit_05 |

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
| 16 | audit_04 M-01 | MEDIUM | Add `classification` and `title` params to `add_history()` | quick fix | Resolved (audit_04 batch fix) |
| 17 | audit_04 M-02 | MEDIUM | Make `total_steps` dynamic in `create_session()` | quick fix | Resolved (audit_04 batch fix) |
| 18 | audit_04 M-03 | MEDIUM | Fix VIDEO entry point dedup with COALESCE or IS NOT DISTINCT FROM | quick fix | Resolved (audit_04 batch fix) |
| 19 | audit_04 M-04 | MEDIUM | Update research SKILL.md for all entry points | quick fix | Resolved (audit_04 batch fix) |
| 20 | audit_04 M-05 | MEDIUM | Fix session-history correlation for non-topic sessions | quick fix | Resolved (audit_04 batch fix) |
| 21 | audit_04 M-06 | MEDIUM | Add basic URL validation for VIDEO entry point | quick fix | Resolved (audit_04 batch fix) |
| 22 | audit_05 M-01 | MEDIUM | Replace quadratic histogram binning with single-pass | quick fix | Open |
| 23 | audit_05 M-02 | MEDIUM | Replace `Math.min/max(...spread)` with loop-based min/max | quick fix | Open |
| 24 | audit_05 M-03 | MEDIUM | Optimize `percentileRank` calls in MCScorecard | quick fix | Open |
| 25 | audit_05 M-04 | MEDIUM | Add runtime type guard for MonteCarloMetrics at API boundary | quick fix | Open |
| 26 | audit_05 M-05 | MEDIUM | Fix `Number(undefined)` NaN pattern in MCDistributionsGrid | quick fix | Open |
| 27 | audit_05 M-06 | MEDIUM | Verify/fix fan chart Area stacking for correct percentile bands | quick fix | Open |

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
| 25 | MEDIUM | `add_history()` missing `classification` parameter | audit_04 | audit_04 batch fix |
| 26 | MEDIUM | `total_steps=6` hardcoded, pipeline now has 8 steps | audit_04 | audit_04 batch fix |
| 27 | MEDIUM | VIDEO entry point dedup weakness with NULL topic_id | audit_04 | audit_04 batch fix |
| 28 | MEDIUM | Research SKILL.md not updated for new entry points | audit_04 | audit_04 batch fix |
| 29 | MEDIUM | VIDEO session-history correlation is fragile | audit_04 | audit_04 batch fix |
| 30 | MEDIUM | No URL validation for VIDEO entry point | audit_04 | audit_04 batch fix |
| 31 | LOW | Preflight runs for IDEA entry point unnecessarily | audit_04 | audit_04 batch fix |
| 32 | LOW | `_resolve_topic_id` used as public API from AGENT.md | audit_04 | audit_04 batch fix |
| 33 | LOW | IDEA entry point: no minimum-length or content validation | audit_04 | audit_04 batch fix |

---

## Aggregate Statistics

| Metric | Value |
|---|---|
| Total audits | 5 |
| Total findings (all time) | 75 |
| Open findings | 34 |
| Resolved findings | 41 |
| Resolution rate | 55% |
