# Tasks: idea-validation-flow

Separar ideas de estrategias validadas mediante un campo `status` en la tabla `strategies`.

**Based on**: [proposal.md](./proposal.md), [spec.md](./spec.md), [design.md](./design.md)
**Date**: 2026-03-16

---

## Phase 1: Database & Model (Foundation)

- [ ] **T1.1** — Add `status` column to Strategy model
  - **File**: `tools/db/models.py`
  - **Action**: Add `status: Mapped[str] = mapped_column(String(20), default="idea", server_default="idea")` after the `name` field in the `Strategy` class.
  - **Dependencies**: None

- [ ] **T1.2** — Create Alembic migration 004 for status column
  - **File**: `api/alembic/versions/004_add_strategy_status.py` (new)
  - **Action**: Create migration with `revision = "004"`, `down_revision = "003"`. Upgrade: `ALTER TABLE strategies ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'idea'` + `CREATE INDEX idx_strategies_status ON strategies (status)`. Downgrade: drop index + drop column.
  - **Dependencies**: T1.1

---

## Phase 2: API Backend (Schema, Service, Router)

- [ ] **T2.1** — Add `status` field to StrategyResponse schema
  - **File**: `api/models/schemas/strategy.py`
  - **Action**: Add `status: str = "idea"` to the `StrategyResponse` Pydantic model, after the `name` field.
  - **Dependencies**: T1.1

- [ ] **T2.2** — Add status filter + include status in service dicts
  - **File**: `api/services/strategy_service.py`
  - **Action**: (1) Add `status: str | None = None` parameter to `list_strategies()` with filter `query.where(Strategy.status == status)`. (2) Add `"status": strat.status` to the dict returned in both `list_strategies()` and `get_strategy_by_name()`.
  - **Dependencies**: T1.1, T2.1

- [ ] **T2.3** — Add `validate_strategy()` and `unvalidate_strategy()` service functions
  - **File**: `api/services/strategy_service.py`
  - **Action**: Create two async functions. Each: SELECT strategy by name (404 if not found), UPDATE status to `'validated'` or `'idea'`, commit, refresh, return dict via `get_strategy_by_name()`.
  - **Dependencies**: T2.2

- [ ] **T2.4** — Add `status` query param to GET /api/strategies
  - **File**: `api/routers/strategies.py`
  - **Action**: Add `status: str | None = Query(None)` parameter to `list_strategies` endpoint handler. Pass `status=status` to the service call.
  - **Dependencies**: T2.2

- [ ] **T2.5** — Add PATCH validate/unvalidate endpoints
  - **File**: `api/routers/strategies.py`
  - **Action**: Add `PATCH /{strategy_name}/validate` and `PATCH /{strategy_name}/unvalidate` endpoints. **Critical**: register these BEFORE the `GET /{strategy_name}` catch-all route to avoid path collision. Both return `StrategyResponse`.
  - **Dependencies**: T2.3

---

## Phase 3: Frontend Services & Types

- [ ] **T3.1** — Add `status` to Strategy type
  - **File**: `frontend/src/types/strategy.ts`
  - **Action**: Add `status: 'idea' | 'validated'` to the `Strategy` interface.
  - **Dependencies**: T2.1 (schema must match)

- [ ] **T3.2** — Add `status` filter param to `getStrategies()`
  - **File**: `frontend/src/services/strategies.ts`
  - **Action**: (1) Add `status?: 'idea' | 'validated'` to `StrategyFilters` interface. (2) In `getStrategies()`, add `if (filters.status) params.set('status', filters.status)`.
  - **Dependencies**: T3.1

- [ ] **T3.3** — Add `validateStrategy()` and `unvalidateStrategy()` API functions
  - **File**: `frontend/src/services/strategies.ts`
  - **Action**: Add two exported async functions that call `api.patch<Strategy>(/strategies/${encodeURIComponent(name)}/validate)` and the unvalidate equivalent.
  - **Dependencies**: T3.1

---

## Phase 4: Frontend UI

- [ ] **T4.1** — Extend ConfirmDialog with `confirmVariant` prop
  - **File**: `frontend/src/components/common/ConfirmDialog.tsx`
  - **Action**: Add optional `confirmVariant?: 'danger' | 'success'` prop (default `'danger'`). When `'success'`, the confirm button uses `bg-green-600 hover:bg-green-700` instead of `bg-red-600`. This enables green button for validate and red for unvalidate.
  - **Dependencies**: None

- [ ] **T4.2** — Add validate/unvalidate button + confirmation modal to StrategyDetail
  - **File**: `frontend/src/components/strategies/StrategyDetail.tsx`
  - **Action**: (1) Add `onStatusChange?: () => void` to props interface. (2) Add `confirmOpen` and `updating` state. (3) Add button in header: green "Validar estrategia" when `status === 'idea'`, amber "Devolver a ideas" when `status === 'validated'`. (4) Wire ConfirmDialog with appropriate texts per design doc. (5) On confirm: call validate/unvalidateStrategy, invalidate query keys `['ideas']` and `['validated-strategies']`, call `onStatusChange?.()`.
  - **Dependencies**: T3.3, T4.1

- [ ] **T4.3** — Update StrategiesPage tab filtering from `has_draft` to `status`
  - **File**: `frontend/src/pages/StrategiesPage.tsx`
  - **Action**: (1) Ideas tab query: add `status: 'idea'` to `getStrategies()` call, query key `['ideas', ...]`. (2) Estrategias tab query: add `status: 'validated'`, query key `['validated-strategies', ...]`. Keep `has_draft` as secondary filter within validated tab. (3) Update empty state text to "No hay estrategias validadas todavia". (4) Pass `onStatusChange` to StrategyDetail that closes the detail panel.
  - **Dependencies**: T3.2, T4.2

- [ ] **T4.4** — Pass `onStatusChange` in ResearchDetailPage
  - **File**: `frontend/src/pages/ResearchDetailPage.tsx`
  - **Action**: Add `onStatusChange={() => setSelectedIdea(null)}` prop to `StrategyDetail` component. The invalidateQueries inside StrategyDetail handles data refresh.
  - **Dependencies**: T4.2

---

## Phase 5: Integration & Verification

- [ ] **T5.1** — Run migration and rebuild frontend
  - **Action**: (1) Run `docker compose build` to rebuild frontend image. (2) Run alembic migration 004 against the database. (3) Verify all existing strategies have `status='idea'`.
  - **Dependencies**: All previous tasks

- [ ] **T5.2** — End-to-end manual testing
  - **Action**: Verify spec scenarios:
    - **S1**: Research pipeline inserts strategies with `status='idea'` (column default).
    - **S2**: Validate from StrategiesPage — strategy moves from Ideas to Estrategias tab.
    - **S3**: Validate from ResearchDetailPage — button changes, status updates.
    - **S4**: Unvalidate — strategy returns to Ideas tab.
    - **S5**: `GET /api/strategies?status=validated` returns only validated.
    - **S6**: `GET /api/strategies` (no filter) returns all — backward compatible.
    - **S7**: Migration safe — all existing rows have `status='idea'`, no NULLs.
  - **Dependencies**: T5.1

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| Phase 1 | 2 | Database model + migration |
| Phase 2 | 5 | API schema, service, router |
| Phase 3 | 3 | Frontend types + services |
| Phase 4 | 4 | Frontend UI components + pages |
| Phase 5 | 2 | Integration + verification |
| **Total** | **16** | |
