# Exploration: idea-validation-flow

**Change**: Separar ideas de estrategias validadas. Tras una investigacion, los resultados se guardan como "ideas". El usuario las revisa en el frontend y puede marcarlas como validas. Las validadas pasan a mostrarse en la pestana Estrategias.

**Date**: 2026-03-16

---

## 1. Current State Analysis

### 1.1 DB Model (`tools/db/models.py`)

The `Strategy` model has these fields:
- `id`, `name` (unique), `description`, `source_channel_id`, `source_videos` (array)
- JSONB fields: `parameters`, `entry_rules`, `exit_rules`, `risk_management`, `notes`
- Inherits `TimestampMixin` → `created_at`, `updated_at`
- **No status/validation field exists**

Related model `Draft` links to Strategy via `strategy_id` FK and has `active`, `tested`, `prod` boolean flags — this is for the JSON trading strategy translation, separate from validation.

### 1.2 Strategy Repository (`tools/db/strategy_repo.py`)

Sync repo used by the research pipeline. Key functions:
- `upsert_strategy()` — deduplication by name (case-insensitive). No status logic.
- `insert_strategy()` — dict-based insert wrapper. No status parameter.

### 1.3 API Service (`api/services/strategy_service.py`)

Async service for the API. Key functions:
- `list_strategies()` — filters by channel, search, session_id, has_draft. Returns dicts with all fields + resolved `source_channel` name.
- `get_strategy_by_name()` — single strategy lookup.
- **No status filtering exists.**

### 1.4 API Router (`api/routers/strategies.py`)

- `GET /api/strategies` — list with filters (channel, search, session_id, has_draft)
- `GET /api/strategies/{strategy_name}` — detail
- **No PATCH/PUT endpoint exists** — needed for validation action.

### 1.5 API Schema (`api/models/schemas/strategy.py`)

- `StrategyResponse` — all fields, no status field
- `StrategiesListResponse` — total + strategies[]

### 1.6 Frontend Types (`frontend/src/types/strategy.ts`)

- `Strategy` interface — mirrors backend response. No status field.

### 1.7 Frontend Services (`frontend/src/services/strategies.ts`)

- `getStrategies(filters)` — supports channel, search, session_id, has_draft
- `getStrategy(name)` — detail
- **No update/validate function exists.**

### 1.8 Frontend StrategiesPage (`frontend/src/pages/StrategiesPage.tsx`)

Has TWO tabs already:
- **Ideas tab**: ALL strategies (no filter)
- **Strategies tab**: only strategies with JSON drafts (`has_draft: true`)

This is the key insight: the current "Ideas vs Strategies" separation is based on whether a Draft JSON exists, NOT on a validation status. The new feature changes this semantic.

### 1.9 Frontend ResearchDetailPage (`frontend/src/pages/ResearchDetailPage.tsx`)

Shows research session results with ideas listed by video. Ideas are clickable and open `StrategyDetail`. No validation action here currently.

### 1.10 Frontend Components

- `StrategyCard` — display card, click handler, no actions
- `StrategyDetail` — full detail view with rules/params tables. Has "Cerrar" button. **No validate/action buttons.**

### 1.11 Migrations

Uses Alembic. 3 migrations exist (`001_initial_schema`, `002_add_classification`, `003_add_history_title`). Next would be `004`.

---

## 2. Affected Areas

| Layer | File | Change needed |
|-------|------|---------------|
| DB Model | `tools/db/models.py` | Add `status` column to Strategy |
| Migration | `api/alembic/versions/004_*.py` | New migration for status column |
| Sync Repo | `tools/db/strategy_repo.py` | Set status='idea' on insert |
| API Schema | `api/models/schemas/strategy.py` | Add status field to response |
| API Service | `api/services/strategy_service.py` | Add status filter, validate logic |
| API Router | `api/routers/strategies.py` | Add PATCH endpoint for validation |
| Frontend Types | `frontend/src/types/strategy.ts` | Add status field |
| Frontend Service | `frontend/src/services/strategies.ts` | Add status filter, validateStrategy() |
| Frontend Page | `frontend/src/pages/StrategiesPage.tsx` | Filter tabs by status |
| Frontend Component | `frontend/src/components/strategies/StrategyDetail.tsx` | Add validate button |
| Frontend Component | `frontend/src/components/strategies/StrategyCard.tsx` | Optional: show status badge |

---

## 3. Approach Comparison

### Approach A: Add `status` field to existing strategies table

**Description**: Add a `status` column (VARCHAR(20), default 'idea') to the `strategies` table. Research pipeline saves with status='idea'. User validates via PATCH → status='validated'. Strategies tab filters `status='validated'`.

**Pros**:
- Minimal schema change — one column, one migration
- No data duplication
- Simple queries: `WHERE status = 'idea'` vs `WHERE status = 'validated'`
- Existing data gets default 'idea', no breakage
- Extensible: future statuses (rejected, archived) trivial to add
- The frontend already has the two-tab structure — just change the filter logic

**Cons**:
- Shares table for two conceptual entities (minor, they are the same entity at different lifecycle stages)

**Effort estimate**: Small. ~12 files touched, most changes are adding a field + filter.

### Approach B: Separate tables (ideas + strategies)

**Description**: Rename current `strategies` table to `ideas`. Create new `validated_strategies` table. Validation copies a row from ideas to validated_strategies.

**Pros**:
- Clean separation of concerns at DB level

**Cons**:
- Major refactor: rename table, update all references, update Drafts FK
- Data duplication (validated strategy exists in both tables, or needs delete from ideas)
- Two repositories, two services, two sets of endpoints
- Migration is complex (rename + create + update FKs)
- The Draft model's `strategy_id` FK becomes ambiguous
- Research pipeline needs updating to use new table name
- Way more code, way more risk, no functional benefit

**Effort estimate**: Large. 20+ files, risky migration, no tangible benefit.

---

## 4. Recommendation

**Approach A (status field)** is the clear winner. The two approaches differ dramatically in effort and risk, with zero functional advantage for Approach B.

Key reasons:
1. An idea and a validated strategy are the **same entity** at different lifecycle stages — this is textbook status-field territory.
2. The current codebase already treats them as one entity. Adding a column preserves all existing code paths.
3. The frontend already has two tabs. Changing the filter from `has_draft` to `status` is minimal.
4. Alembic migration is trivial: one `ADD COLUMN` with a default.
5. Future extensibility (rejected, archived, etc.) comes for free.

### Recommended Implementation Plan

1. **Migration**: Add `status VARCHAR(20) DEFAULT 'idea' NOT NULL` to strategies. Backfill existing rows as 'idea'.
2. **Model**: Add `status` field to Strategy model.
3. **Pipeline repo**: `upsert_strategy()` sets status='idea' on insert (default handles it).
4. **API**: Add `status` query param to list endpoint. Add `PATCH /api/strategies/{name}/validate` endpoint.
5. **Frontend**: Add `status` to types, add `validateStrategy()` to service, filter Ideas tab by `status=idea`, Strategies tab by `status=validated`, add "Validar" button to StrategyDetail.

---

## 5. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Existing strategies all become "ideas" after migration | Low | This is correct behavior — they ARE unvalidated ideas. Communicate to user. |
| Strategies tab becomes empty after change | Low | Expected — user needs to validate. Could add a migration note in UI. |
| Draft linkage confusion | Low | Drafts remain linked to Strategy regardless of status. A draft can exist for an idea or a validated strategy. |
| has_draft filter becomes obsolete for tab logic | Low | Keep it available as secondary filter if needed, but tabs switch to status-based. |

---

## 6. Open Questions

1. Should the "Strategies" tab also show `has_draft` filter as a secondary filter within validated strategies?
2. Should validation be possible from ResearchDetailPage as well, or only from StrategiesPage?
3. Should there be a way to "unvalidate" (revert to idea)?
4. Should the validation action require confirmation (modal) or be a simple click?
