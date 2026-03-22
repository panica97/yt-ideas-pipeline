# Audit 01 - Full Codebase Audit

**Date**: 2026-03-22
**Scope**: Entire codebase - frontend, backend, infrastructure, configuration
**Auditor**: Claude Opus 4.6 (1M context)

---

## Tracking Table

| # | Severity | Category | Finding | File(s) | Status |
|---|----------|----------|---------|---------|--------|
| 01 | HIGH | Security | Default API key in source code | `api/config.py:10` | Open |
| 02 | HIGH | Security | API key transmitted in WebSocket URL query parameter | `frontend/src/hooks/useResearchStatus.ts:11`, `api/routers/research.py:59` | Open |
| 03 | HIGH | Security | Health endpoint returns 200 even when DB is down | `api/routers/health.py:44-49` | Open |
| 04 | HIGH | Security | No rate limiting on any endpoint | `api/main.py` | Open |
| 05 | HIGH | Security | Dual auth (middleware + dependency) creates bypass risk | `api/middleware/auth.py`, `api/dependencies.py` | Open |
| 06 | MEDIUM | Backend | No pagination on strategies list endpoint | `api/services/strategy_service.py:91-93` | Open |
| 07 | MEDIUM | Backend | Unused import: `inspect` in health.py | `api/routers/health.py:6` | Open |
| 08 | MEDIUM | Backend | `fill_todo` does not verify current value is `_TODO` | `api/services/strategy_service.py:467-487` | Open |
| 09 | MEDIUM | Backend | History `sort` parameter accepts arbitrary strings silently | `api/services/history_service.py:79` | Open |
| 10 | MEDIUM | Backend | Missing `instruments` in health check expected tables | `api/routers/health.py:12-19` | Open |
| 11 | MEDIUM | Backend | `channel_service.add_channel` uses `flush()` without `commit()` | `api/services/channel_service.py:61` | Open |
| 12 | MEDIUM | Backend | `ResearchSession` model not in `_EXPECTED_TABLES` synced with `instruments` | `api/routers/health.py:12-19` | Open |
| 13 | MEDIUM | Backend | Strategy model `parameters` typed as `Optional[dict]` but defaults to `[]` (list) | `tools/db/models.py:68-80` | Open |
| 14 | MEDIUM | Frontend | `formatDuration` duplicated in 4 files | `DashboardPage.tsx`, `HistoryPage.tsx`, `ResearchPage.tsx`, `ResearchDetailPage.tsx` | Open |
| 15 | MEDIUM | Frontend | `error: any` type in DraftViewer.tsx | `frontend/src/components/strategies/DraftViewer.tsx:55` | Open |
| 16 | MEDIUM | Frontend | No Error Boundary wrapping the app | `frontend/src/App.tsx` | Open |
| 17 | MEDIUM | Frontend | WebSocket reconnect has no max retry limit | `frontend/src/hooks/useWebSocket.ts:42-46` | Open |
| 18 | MEDIUM | Frontend | API key stored in localStorage (XSS-accessible) | `frontend/src/services/api.ts:8`, `frontend/src/router.tsx:14` | Open |
| 19 | MEDIUM | Infra | Docker Compose exposes PostgreSQL port 5432 to host | `docker-compose.yml:9` | Open |
| 20 | MEDIUM | Infra | No Docker health check for `api` or `frontend` services | `docker-compose.yml:31-50` | Open |
| 21 | MEDIUM | Infra | Nginx proxy has no timeouts, buffer limits, or security headers | `frontend/nginx.conf` | Open |
| 22 | LOW | Backend | `import_service.py` has duplicated `_extract_todo_fields` function | `api/services/import_service.py:179`, `api/services/strategy_service.py:217` | Open |
| 23 | LOW | Backend | `health.py` imports `inspect` but never uses it | `api/routers/health.py:6` | Open |
| 24 | LOW | Backend | `channel_service.delete_channel` prevents deletion of last channel but no business justification documented | `api/services/channel_service.py:98` | Open |
| 25 | LOW | Frontend | No favicon or meta tags for SEO/sharing | `frontend/` | Open |
| 26 | LOW | Frontend | Channel filter in HistoryPage has unused filtering logic | `frontend/src/pages/HistoryPage.tsx:158` | Open |
| 27 | LOW | Infra | Root Dockerfile has no CMD or purpose clarity | `Dockerfile` (root) | Open |
| 28 | LOW | Infra | `node_modules/` present in project root (should be gitignored or absent) | Root dir | Open |
| 29 | LOW | Backend | `onupdate=func.now()` in TimestampMixin only works for ORM updates, not raw SQL | `tools/db/base.py:19` | Open |
| 30 | LOW | Cross | No test suite exists for backend or frontend | Project-wide | Open |

---

## Findings by Severity

### HIGH (5 findings)

#### H-01: Default API key hardcoded in source code
- **File**: `api/config.py:10`
- **Detail**: `DASHBOARD_API_KEY: str = "change-me-to-a-secure-key"` is the default. If `.env` is missing or incomplete, the app runs with a publicly known key.
- **Risk**: Full unauthorized access to all API endpoints.
- **Route**: Change default to empty string and fail startup if not set. Add validation in `Settings` class.

#### H-02: API key in WebSocket URL query parameter
- **Files**: `frontend/src/hooks/useResearchStatus.ts:11`, `api/routers/research.py:59`
- **Detail**: The WebSocket URL includes `?api_key=<value>` in the query string. This value appears in server access logs, browser history, and potentially proxy logs.
- **Risk**: API key leakage through logs.
- **Route**: Use the first message after WebSocket connect for authentication, or use a short-lived token.

#### H-03: Health endpoint returns HTTP 200 with degraded status
- **File**: `api/routers/health.py:44-49`
- **Detail**: When the database is down, the health endpoint returns `{"status": "degraded"}` with HTTP 200. Load balancers and monitoring will treat this as healthy.
- **Risk**: Traffic routed to unhealthy instances.
- **Route**: Return HTTP 503 when database is unreachable.

#### H-04: No rate limiting
- **File**: `api/main.py`
- **Detail**: No rate limiting middleware on any endpoint. Login validation, CRUD operations, and export endpoints are all unprotected.
- **Risk**: Brute-force API key guessing, denial of service.
- **Route**: Add `slowapi` or similar rate limiting middleware, especially on authentication-adjacent endpoints.

#### H-05: Dual authentication creates confusion
- **Files**: `api/middleware/auth.py`, `api/dependencies.py`
- **Detail**: Authentication is implemented twice: as middleware (`ApiKeyMiddleware`) that runs on all requests, and as a FastAPI dependency (`verify_api_key`) on individual routers. The middleware intercepts before the dependency runs. If either is modified independently, auth gaps may appear. Additionally, WebSocket requests bypass the middleware (line 33) and rely solely on query parameter auth.
- **Risk**: Auth bypass if middleware is inadvertently changed; inconsistent auth enforcement.
- **Route**: Choose one auth strategy and remove the other. Middleware-based is simpler for uniform enforcement; dependency-based is more testable.

---

### MEDIUM (13 findings)

#### M-06: No pagination on strategies endpoint
- **File**: `api/services/strategy_service.py:91-93`
- **Detail**: `list_strategies()` fetches ALL matching rows without `LIMIT/OFFSET`. With many strategies, this returns unbounded data.
- **Route**: Add `page` and `limit` query parameters (like `history` endpoint already has).

#### M-07: Unused import in health.py
- **File**: `api/routers/health.py:6`
- **Detail**: `from sqlalchemy import inspect, text` - `inspect` is imported but never used.
- **Route**: Remove the unused import.

#### M-08: fill_todo does not validate current value is a TODO
- **File**: `api/services/strategy_service.py:467-487`
- **Detail**: The `fill_todo` endpoint allows overwriting ANY field, not just `_TODO` sentinels. The old value is read but never checked.
- **Route**: Add validation: `if "_TODO" not in str(current_value): raise HTTPException(422, ...)`.

#### M-09: History sort parameter silent fallback
- **File**: `api/services/history_service.py:79`
- **Detail**: Invalid `sort` values fall back silently to `researched_at`. User gets no feedback their sort parameter was wrong.
- **Route**: Return 422 if `sort` is not in `_VALID_SORT_FIELDS`.

#### M-10: Missing `instruments` in health check
- **File**: `api/routers/health.py:12-19`
- **Detail**: `_EXPECTED_TABLES` list does not include `instruments`, which was added in migration 006.
- **Route**: Add `"instruments"` to the list.

#### M-11: Service methods use flush() without commit()
- **Files**: `channel_service.py:61`, `topic_service.py:27`, `instrument_service.py:49`
- **Detail**: Multiple service methods call `flush()` but not `commit()`. The commit happens in the `get_db` dependency's exit. This works correctly but is fragile -- if the dependency's try/commit pattern changes, data could be lost. More importantly, `channel_service.delete_channel` calls `flush()` but if the session is not auto-committing, deletes might not persist in certain error flows.
- **Route**: Either consistently use `commit()` in services or document the dependency on the session lifecycle.

#### M-13: Model type mismatch for JSONB columns
- **File**: `tools/db/models.py:68-80`
- **Detail**: `Strategy.parameters`, `entry_rules`, `exit_rules`, `risk_management`, and `notes` are typed as `Mapped[Optional[dict]]` but their `server_default` is `"[]"` (a list). Python type hints say dict, actual data is list.
- **Route**: Change type hint to `Mapped[Optional[list]]` or `Mapped[Optional[list | dict]]`.

#### M-14: `formatDuration` duplicated in 4 files
- **Files**: `DashboardPage.tsx`, `HistoryPage.tsx`, `ResearchPage.tsx`, `ResearchDetailPage.tsx`
- **Detail**: Identical helper function copy-pasted across 4 page components.
- **Route**: Extract to `frontend/src/utils/formatDuration.ts` and import.

#### M-15: `any` type usage
- **File**: `frontend/src/components/strategies/DraftViewer.tsx:55`
- **Detail**: `onError: (error: any) => {` -- using `any` bypasses type safety.
- **Route**: Type as `AxiosError` or `Error` with proper narrowing.

#### M-16: No Error Boundary
- **File**: `frontend/src/App.tsx`
- **Detail**: No React Error Boundary wraps the application. An unhandled render error in any component crashes the entire app with a blank screen.
- **Route**: Add an ErrorBoundary component wrapping `RouterProvider`.

#### M-17: WebSocket reconnect has no max retries
- **File**: `frontend/src/hooks/useWebSocket.ts:42-46`
- **Detail**: The WebSocket reconnect loop uses exponential backoff (max 30s) but never stops retrying. If the server is permanently down, the client retries forever.
- **Route**: Add a max retry count (e.g., 20) and show a "connection lost" state.

#### M-18: API key in localStorage
- **Files**: `frontend/src/services/api.ts:8`, `frontend/src/router.tsx:14`
- **Detail**: The API key is stored in `localStorage`, which is accessible to any JavaScript running on the page (XSS vulnerability).
- **Route**: For a single-user dashboard this is acceptable, but document the trade-off. Consider `httpOnly` cookies for production.

#### M-19: PostgreSQL port exposed
- **File**: `docker-compose.yml:9`
- **Detail**: Port 5432 is mapped to the host, making the database accessible from outside Docker.
- **Route**: Remove `ports` mapping for postgres in production, or bind to `127.0.0.1:5432:5432`.

#### M-20: No health checks for api/frontend in Docker
- **File**: `docker-compose.yml:31-50`
- **Detail**: Only `postgres` has a health check. The `api` and `frontend` services have none, so Docker cannot detect if they crash or hang.
- **Route**: Add `healthcheck` to both services (e.g., `curl -f http://localhost:8000/api/health`).

#### M-21: Nginx lacks security headers and limits
- **File**: `frontend/nginx.conf`
- **Detail**: No `proxy_read_timeout`, no `client_max_body_size`, no security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`).
- **Route**: Add standard security headers and proxy timeout configuration.

---

### LOW (8 findings)

#### L-22: Duplicated `_extract_todo_fields` function
- **Files**: `api/services/import_service.py:179`, `api/services/strategy_service.py:217`
- **Detail**: Same logic duplicated. Minor differences in return type (list of strings vs list of dicts).
- **Route**: Extract to a shared utility in `tools/` or `api/utils/`.

#### L-23: Unused `inspect` import (same as M-07)
- Duplicate of M-07 for tracking.

#### L-24: "Last channel" deletion guard undocumented
- **File**: `api/services/channel_service.py:98`
- **Detail**: Business rule preventing deletion of the last channel in a topic. No documentation on why.
- **Route**: Add docstring explaining the rationale.

#### L-25: No favicon or meta tags
- **Files**: `frontend/`
- **Detail**: Missing `<meta>` description, Open Graph tags, and favicon for the dashboard.
- **Route**: Add basic meta tags and a favicon to `index.html`.

#### L-26: Unused channel filter logic in HistoryPage
- **File**: `frontend/src/pages/HistoryPage.tsx:158`
- **Detail**: `.filter(() => true)` is a no-op filter that suggests incomplete implementation of channel filtering by topic.
- **Route**: Implement proper topic-based channel filtering or remove the dead code.

#### L-27: Root Dockerfile unclear
- **File**: `Dockerfile` (root)
- **Detail**: 5-line Dockerfile with no CMD, only copies requirements and source. Purpose unclear (pipeline runner?).
- **Route**: Add a comment or CMD, or remove if unused.

#### L-28: `node_modules` in project root
- **Detail**: A `node_modules/` directory exists at project root (not inside `frontend/`). Could be leftover from global tooling.
- **Route**: Add to `.gitignore` if not already, remove if unnecessary.

#### L-29: `onupdate` only works for ORM operations
- **File**: `tools/db/base.py:19`
- **Detail**: `onupdate=func.now()` on `updated_at` only triggers for ORM-level updates. Raw SQL or bulk operations bypass it.
- **Route**: Add a database-level trigger for `updated_at` or document the limitation.

#### L-30: No test suite
- **Detail**: No `tests/` directory, no `pytest.ini`, no test files found anywhere in the project. Zero test coverage.
- **Route**: Add integration tests for critical API endpoints and unit tests for service logic.

---

## Cross-Cutting Analysis

### API Endpoint Coverage

All frontend service calls map to existing backend endpoints:

| Frontend Service | Backend Endpoint | Match |
|---|---|---|
| `getStats()` | `GET /api/stats` | OK |
| `getChannels()` | `GET /api/channels` | OK |
| `createTopic()` | `POST /api/topics` | OK |
| `updateTopic()` | `PUT /api/topics/{slug}` | OK |
| `deleteTopic()` | `DELETE /api/topics/{slug}` | OK |
| `createChannel()` | `POST /api/channels/{topic}` | OK |
| `deleteChannel()` | `DELETE /api/channels/{topic}/{name}` | OK |
| `getStrategies()` | `GET /api/strategies` | OK |
| `getStrategy()` | `GET /api/strategies/{name}` | OK |
| `setStrategyStatus()` | `PATCH /api/strategies/{name}/status` | OK |
| `getDraftsByStrategy()` | `GET /api/strategies/{name}/drafts` | OK |
| `getDrafts()` | `GET /api/strategies/drafts` | OK |
| `getDraft()` | `GET /api/strategies/drafts/{code}` | OK |
| `updateDraftData()` | `PUT /api/strategies/drafts/{code}/data` | OK |
| `getHistory()` | `GET /api/history` | OK |
| `getHistoryStats()` | `GET /api/history/stats` | OK |
| `getResearchSessions()` | `GET /api/research/sessions` | OK |
| `getResearchSessionDetail()` | `GET /api/research/sessions/{id}` | OK |
| `getInstruments()` | `GET /api/instruments` | OK |
| `createInstrument()` | `POST /api/instruments` | OK |
| `updateInstrument()` | `PUT /api/instruments/{symbol}` | OK |
| `deleteInstrument()` | `DELETE /api/instruments/{symbol}` | OK |
| WebSocket | `WS /api/research/status` | OK |

**Result**: Full coverage. No orphaned endpoints and no frontend calls to missing endpoints.

### Orphaned/Dead Code
- `from sqlalchemy import inspect` in `health.py` (unused import)
- `.filter(() => true)` in `HistoryPage.tsx:158` (no-op)
- Root `Dockerfile` has no clear purpose

### Error Handling Consistency
- Backend: Consistent use of `HTTPException` with proper status codes across all services. Good 404/409/422 coverage.
- Frontend: Axios interceptor handles 401 globally. Individual pages handle loading states. Missing: global error boundary, mutation error feedback on some pages.

### Hardcoded Values
- `DASHBOARD_API_KEY` default: `"change-me-to-a-secure-key"` (H-01)
- `staleTime: 30 * 1000` in React Query config (acceptable)
- `total_steps: 6` in `ResearchSession` model (acceptable, matches pipeline)
- Database connection defaults point to Docker service names (acceptable for dev)

---

## Statistics

| Metric | Value |
|---|---|
| Total findings | 30 |
| HIGH severity | 5 |
| MEDIUM severity | 17 |
| LOW severity | 8 |
| Backend findings | 14 |
| Frontend findings | 7 |
| Infrastructure findings | 5 |
| Cross-cutting findings | 4 |
| Files audited (backend) | ~25 |
| Files audited (frontend) | ~40 |
| Files audited (infra) | 4 |
| API endpoints | 23 (22 REST + 1 WebSocket) |
| Frontend-backend coverage | 100% |
| Orphaned endpoints | 0 |
| Dead code instances | 3 |
| Test coverage | 0% |

---

## Recommendations (Priority Order)

1. **Immediate** (H-01 to H-04): Fix security issues -- hardcoded key, health status code, rate limiting
2. **Short-term** (M-06, M-08, M-10, M-13): Fix data integrity issues -- pagination, TODO validation, type mismatches
3. **Medium-term** (M-14, M-16, L-30): Code quality -- deduplicate utils, add error boundary, start test suite
4. **Long-term** (M-18, M-19, M-21): Production hardening -- auth token strategy, network security, nginx headers
