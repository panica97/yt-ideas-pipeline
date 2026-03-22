# Master Audit - IRT Project

**Last updated**: 2026-03-22

---

## Audit History

| Audit | Date | Scope | Findings | HIGH | MEDIUM | LOW | Resolved |
|-------|------|-------|----------|------|--------|-----|----------|
| [audit_01](audit_01.md) | 2026-03-22 | Full codebase | 30 | 5 | 17 | 8 | 0 |

---

## Open Findings Summary

### HIGH (5 open)

| # | Finding | Source | Suggested Route |
|---|---------|--------|-----------------|
| 01 | Default API key in source code | audit_01 | Fail startup if `DASHBOARD_API_KEY` is default/empty |
| 02 | API key in WebSocket query param (log leakage) | audit_01 | Auth via first WS message or short-lived token |
| 03 | Health endpoint returns 200 when DB is down | audit_01 | Return HTTP 503 on degraded status |
| 04 | No rate limiting on any endpoint | audit_01 | Add `slowapi` middleware |
| 05 | Dual auth mechanism (middleware + dependency) | audit_01 | Consolidate to one approach |

### MEDIUM (17 open)

| # | Finding | Source |
|---|---------|--------|
| 06 | No pagination on strategies list | audit_01 |
| 07 | Unused `inspect` import | audit_01 |
| 08 | `fill_todo` overwrites non-TODO fields | audit_01 |
| 09 | History sort param silent fallback | audit_01 |
| 10 | `instruments` missing from health check tables | audit_01 |
| 11 | flush() without commit() pattern fragility | audit_01 |
| 13 | JSONB columns typed as dict but default to list | audit_01 |
| 14 | `formatDuration` duplicated 4x | audit_01 |
| 15 | `any` type in DraftViewer | audit_01 |
| 16 | No Error Boundary | audit_01 |
| 17 | WebSocket unlimited retries | audit_01 |
| 18 | API key in localStorage | audit_01 |
| 19 | PostgreSQL port exposed to host | audit_01 |
| 20 | No Docker health checks for api/frontend | audit_01 |
| 21 | Nginx missing security headers/limits | audit_01 |

### LOW (8 open)

| # | Finding | Source |
|---|---------|--------|
| 22 | Duplicated `_extract_todo_fields` | audit_01 |
| 23 | Unused import (dup of 07) | audit_01 |
| 24 | Last-channel guard undocumented | audit_01 |
| 25 | No favicon/meta tags | audit_01 |
| 26 | No-op channel filter in HistoryPage | audit_01 |
| 27 | Root Dockerfile unclear | audit_01 |
| 28 | `node_modules` in project root | audit_01 |
| 29 | `onupdate` only for ORM ops | audit_01 |
| 30 | No test suite | audit_01 |

---

## Resolved Findings

_None yet._

---

## Aggregate Statistics

| Metric | Value |
|---|---|
| Total audits | 1 |
| Total findings (all time) | 30 |
| Open findings | 30 |
| Resolved findings | 0 |
| Resolution rate | 0% |
