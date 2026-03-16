# Spec: idea-validation-flow

**Change**: Separar ideas de estrategias validadas mediante un campo `status` en la tabla `strategies`.

**Date**: 2026-03-16
**Based on**: [proposal.md](./proposal.md)

---

## 1. Database

### 1.1 Model change — `tools/db/models.py`

Add `status` column to `Strategy` model:

```python
status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="idea")
```

Valid values: `'idea'`, `'validated'`.
Position: after the `name` field.

### 1.2 Migration — `api/alembic/versions/004_add_strategy_status.py`

```python
revision = "004"
down_revision = "003"
```

**Upgrade**:
```sql
ALTER TABLE strategies ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'idea';
```

All existing rows get `'idea'` automatically via the DEFAULT clause. No explicit backfill needed.

**Downgrade**:
```sql
ALTER TABLE strategies DROP COLUMN status;
```

### 1.3 Sync repo — `tools/db/strategy_repo.py`

No changes required. The column default `'idea'` handles new inserts from the research pipeline.

---

## 2. API

### 2.1 Schema — `api/models/schemas/strategy.py`

Add to `StrategyResponse`:

```python
status: str = "idea"
```

Position: after `name` field.

### 2.2 Service — `api/services/strategy_service.py`

#### 2.2.1 Modify `list_strategies()`

Add `status: str | None = None` parameter.

Filter logic (before existing filters):
```python
if status:
    query = query.where(Strategy.status == status)
```

Add `"status": strat.status` to the dict returned for each strategy row.

#### 2.2.2 Modify `get_strategy_by_name()`

Add `"status": strat.status` to the returned dict.

#### 2.2.3 New function `validate_strategy()`

```python
async def validate_strategy(db: AsyncSession, name: str) -> dict[str, Any]:
    result = await db.execute(
        select(Strategy).where(Strategy.name == name)
    )
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(status_code=404, detail=f"Estrategia '{name}' no encontrada")
    strat.status = "validated"
    await db.commit()
    await db.refresh(strat)
    return await get_strategy_by_name(db, name)
```

#### 2.2.4 New function `unvalidate_strategy()`

Same as above but sets `strat.status = "idea"`.

### 2.3 Router — `api/routers/strategies.py`

#### 2.3.1 Modify `GET /api/strategies`

Add query parameter:
```python
status: str | None = Query(None)
```

Pass to service: `status=status`.

#### 2.3.2 New endpoint `PATCH /api/strategies/{strategy_name}/validate`

```
PATCH /api/strategies/{strategy_name}/validate
Response 200: StrategyResponse (status='validated')
Response 404: {"detail": "Estrategia '{name}' no encontrada"}
```

#### 2.3.3 New endpoint `PATCH /api/strategies/{strategy_name}/unvalidate`

```
PATCH /api/strategies/{strategy_name}/unvalidate
Response 200: StrategyResponse (status='idea')
Response 404: {"detail": "Estrategia '{name}' no encontrada"}
```

**Important**: These PATCH routes MUST be registered before the `/{strategy_name}` GET catch-all, same pattern as `/drafts` routes.

---

## 3. Frontend

### 3.1 Types — `frontend/src/types/strategy.ts`

Add to `Strategy` interface:
```typescript
status: 'idea' | 'validated';
```

### 3.2 Service — `frontend/src/services/strategies.ts`

#### 3.2.1 Add `status` to `StrategyFilters`

```typescript
interface StrategyFilters {
  channel?: string;
  search?: string;
  session_id?: number;
  has_draft?: boolean;
  status?: 'idea' | 'validated';
}
```

In `getStrategies()`, add:
```typescript
if (filters.status) params.set('status', filters.status);
```

#### 3.2.2 New functions

```typescript
export async function validateStrategy(name: string): Promise<Strategy> {
  const { data } = await api.patch<Strategy>(`/strategies/${encodeURIComponent(name)}/validate`);
  return data;
}

export async function unvalidateStrategy(name: string): Promise<Strategy> {
  const { data } = await api.patch<Strategy>(`/strategies/${encodeURIComponent(name)}/unvalidate`);
  return data;
}
```

### 3.3 StrategiesPage — `frontend/src/pages/StrategiesPage.tsx`

#### Tab filter changes

- **Ideas tab** query: `getStrategies({ ..., status: 'idea' })`
- **Estrategias tab** query: `getStrategies({ ..., status: 'validated' })`
  - Within "Estrategias" tab, keep `has_draft` as an optional secondary filter.

Query key updates:
- Ideas: `['ideas', search, channelFilter, sessionFilter]` — add `status: 'idea'` to fetch call.
- Strategies: `['strategies-validated', search, channelFilter, sessionFilter, hasDraftFilter]` — use `status: 'validated'` and optionally `has_draft`.

#### Callback for validation

After a successful validate/unvalidate call, invalidate both query keys (`'ideas'` and `'strategies-validated'`) so tabs refresh. Use `queryClient.invalidateQueries()`.

### 3.4 StrategyDetail — `frontend/src/components/strategies/StrategyDetail.tsx`

#### Add validate/unvalidate button

In the header area (next to "Cerrar" button):

- If `strategy.status === 'idea'`: show "Validar" button (green/primary style).
- If `strategy.status === 'validated'`: show "Des-validar" button (secondary/muted style).

Both buttons open a confirmation modal before executing.

#### Props change

Add optional callback `onStatusChange?: (updated: Strategy) => void` to `StrategyDetailProps`. Parent components use this to refresh their data after validation.

### 3.5 Confirmation Modal

A simple reusable modal component (or inline in StrategyDetail):

```
Title: "Confirmar accion"
Body:
  - Validate: "¿Estas seguro de que quieres validar esta estrategia?"
  - Unvalidate: "¿Estas seguro de que quieres des-validar esta estrategia?"
Buttons: "Confirmar" (primary) | "Cancelar" (ghost)
```

If a shared `ConfirmModal` component already exists in the codebase, reuse it. Otherwise create a minimal one at `frontend/src/components/common/ConfirmModal.tsx`.

### 3.6 ResearchDetailPage — `frontend/src/pages/ResearchDetailPage.tsx`

When displaying idea detail (via StrategyDetail component), the validate button is already available through the StrategyDetail changes above. Ensure:

- `onStatusChange` callback is passed so the research detail view refreshes after validation.
- The StrategyDetail component receives the latest strategy data (with `status` field).

### 3.7 StrategyCard — `frontend/src/components/strategies/StrategyCard.tsx`

Optional visual badge showing status. Low priority — the tab separation already communicates status. Can be deferred.

---

## 4. File Change Summary

| # | File | Action |
|---|------|--------|
| 1 | `tools/db/models.py` | Add `status` column to Strategy |
| 2 | `api/alembic/versions/004_add_strategy_status.py` | New migration file |
| 3 | `api/models/schemas/strategy.py` | Add `status` field to StrategyResponse |
| 4 | `api/services/strategy_service.py` | Add status filter + validate/unvalidate functions + status in dicts |
| 5 | `api/routers/strategies.py` | Add status query param + 2 PATCH endpoints |
| 6 | `frontend/src/types/strategy.ts` | Add `status` to Strategy interface |
| 7 | `frontend/src/services/strategies.ts` | Add status filter + validate/unvalidate API calls |
| 8 | `frontend/src/pages/StrategiesPage.tsx` | Change tab filters to use status |
| 9 | `frontend/src/components/strategies/StrategyDetail.tsx` | Add validate/unvalidate button + modal |
| 10 | `frontend/src/components/common/ConfirmModal.tsx` | New (if not existing) confirmation modal |
| 11 | `frontend/src/pages/ResearchDetailPage.tsx` | Pass onStatusChange to StrategyDetail |

---

## 5. Test Scenarios

### S1: Research pipeline saves strategies with default status
- **Given**: Research pipeline runs and extracts strategies
- **When**: `upsert_strategy()` inserts a new row
- **Then**: `status = 'idea'` (via column default, no code change needed)
- **Verify**: `SELECT status FROM strategies WHERE name = '<new>' → 'idea'`

### S2: User validates from StrategiesPage
- **Given**: Strategy with `status='idea'` visible in "Ideas" tab
- **When**: User clicks strategy -> clicks "Validar" -> confirms modal
- **Then**: `PATCH /api/strategies/{name}/validate` returns `status='validated'`
- **Then**: Strategy disappears from "Ideas" tab, appears in "Estrategias" tab
- **Verify**: Both tab queries re-fetch and reflect the change

### S3: User validates from ResearchDetailPage
- **Given**: User is viewing a research session's idea detail
- **When**: User clicks "Validar" -> confirms modal
- **Then**: Same API call and result as S2
- **Then**: Strategy detail updates to show `status='validated'` and button changes to "Des-validar"

### S4: User unvalidates
- **Given**: Strategy with `status='validated'` visible in "Estrategias" tab
- **When**: User clicks strategy -> clicks "Des-validar" -> confirms modal
- **Then**: `PATCH /api/strategies/{name}/unvalidate` returns `status='idea'`
- **Then**: Strategy moves back to "Ideas" tab

### S5: GET with status filter returns only matching
- **When**: `GET /api/strategies?status=validated`
- **Then**: Response contains only strategies where `status='validated'`
- **Then**: `total` reflects the filtered count

### S6: GET without status filter returns all (backward compatible)
- **When**: `GET /api/strategies` (no status param)
- **Then**: Response contains all strategies regardless of status
- **Then**: Existing clients not using `status` param see no behavior change

### S7: Migration is safe for existing data
- **Given**: Existing strategies table with N rows
- **When**: Migration 004 runs
- **Then**: All N rows have `status='idea'`
- **Then**: No NULL values in status column (NOT NULL constraint)

---

## 6. Constraints & Edge Cases

- **PATCH route ordering**: The validate/unvalidate PATCH routes must be registered BEFORE the `/{strategy_name}` GET route in the router file, otherwise FastAPI will try to match "validate" as a strategy name.
- **URL encoding**: Strategy names may contain special characters. The frontend already uses `encodeURIComponent()` — the new PATCH calls must do the same.
- **Concurrent validation**: No locking needed. The operation is idempotent — validating an already-validated strategy just sets `status='validated'` again. Same for unvalidate.
- **Draft linkage**: Drafts remain linked to Strategy regardless of status. A validated strategy can have a draft; an idea can have a draft. The `has_draft` filter is orthogonal to `status`.
