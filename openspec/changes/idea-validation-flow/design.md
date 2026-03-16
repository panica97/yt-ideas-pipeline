# Design: idea-validation-flow

**Change**: Separar ideas de estrategias validadas mediante un campo de estado.

**Date**: 2026-03-16

---

## 1. Architecture Decisions

### 1.1 Status field on existing table (not separate tables)

La tabla `strategies` recibe una columna `status VARCHAR(20) NOT NULL DEFAULT 'idea'`. Una idea y una estrategia validada son la misma entidad en distinta fase del lifecycle. No se crean tablas nuevas. La columna es extensible a futuros estados (rejected, archived) sin migracion adicional.

### 1.2 Dos endpoints separados (validate / unvalidate) en vez de toggle

Se usan dos endpoints PATCH distintos en lugar de un toggle unico:

- `PATCH /api/strategies/{strategy_name}/validate`
- `PATCH /api/strategies/{strategy_name}/unvalidate`

**Razon**: Endpoints explicitos son idempotentes y predecibles. Un toggle es ambiguo — el cliente necesitaria saber el estado actual para predecir el resultado. Con endpoints separados, la intencion es clara y no hay race conditions si el usuario hace doble click.

### 1.3 Reusar ConfirmDialog existente (no crear componente nuevo)

Ya existe `frontend/src/components/common/ConfirmDialog.tsx` con la interfaz exacta que necesitamos: `open`, `title`, `message`, `confirmLabel`, `cancelLabel`, `onConfirm`, `onCancel`. Se reutiliza directamente en `StrategyDetail`. No se crea ningun componente modal nuevo.

### 1.4 Refetch en vez de optimistic update

Tras la llamada al API de validate/unvalidate, se hace `queryClient.invalidateQueries` para refrescar los datos. No se usa optimistic update porque:
- La operacion es rapida (un UPDATE de una columna).
- Evita inconsistencias si el API falla.
- El refetch es mas simple de implementar y mantener.

---

## 2. Backend Changes

### 2.1 Migration `004_add_strategy_status`

**File**: `api/alembic/versions/004_add_strategy_status.py`

```sql
ALTER TABLE strategies ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'idea';
CREATE INDEX idx_strategies_status ON strategies (status);
```

- Backfill automatico: todas las filas existentes reciben `'idea'` via DEFAULT.
- Indice para filtrado eficiente por status.

### 2.2 Model — `tools/db/models.py`

Agregar a `Strategy`:

```python
status: Mapped[str] = mapped_column(String(20), default="idea", server_default="idea")
```

### 2.3 Schema — `api/models/schemas/strategy.py`

Agregar a `StrategyResponse`:

```python
status: str = "idea"
```

### 2.4 Service — `api/services/strategy_service.py`

**`list_strategies()`** — nuevo parametro `status: str | None`:

```python
if status:
    query = query.where(Strategy.status == status)
```

Incluir `"status": strat.status` en el dict de cada estrategia (tanto en `list_strategies` como en `get_strategy_by_name`).

**Nuevas funciones**:

```python
async def validate_strategy(db: AsyncSession, name: str) -> dict[str, Any]:
    """Set strategy status to 'validated'."""
    # SELECT + UPDATE + commit + return updated dict

async def unvalidate_strategy(db: AsyncSession, name: str) -> dict[str, Any]:
    """Set strategy status back to 'idea'."""
    # SELECT + UPDATE + commit + return updated dict
```

Ambas funciones:
1. Buscan la estrategia por nombre (404 si no existe).
2. Actualizan `status`.
3. Hacen `db.commit()`.
4. Retornan el dict completo de la estrategia (mismo formato que `get_strategy_by_name`).

### 2.5 Router — `api/routers/strategies.py`

**Modificar `list_strategies`**:

```python
@router.get("", response_model=StrategiesListResponse)
async def list_strategies(
    channel: str | None = Query(None),
    search: str | None = Query(None),
    session_id: int | None = Query(None),
    has_draft: bool | None = Query(None),
    status: str | None = Query(None),  # NUEVO
    db: AsyncSession = Depends(get_db),
):
```

**Nuevos endpoints** (antes de `/{strategy_name}` para evitar captura de path):

```python
@router.patch("/{strategy_name}/validate", response_model=StrategyResponse)
async def validate_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.validate_strategy(db, strategy_name)

@router.patch("/{strategy_name}/unvalidate", response_model=StrategyResponse)
async def unvalidate_strategy(strategy_name: str, db: AsyncSession = Depends(get_db)):
    return await strategy_service.unvalidate_strategy(db, strategy_name)
```

**Orden de rutas en el router**:
1. `/drafts` y `/drafts/{strat_code}` (ya existentes, primero)
2. `GET ""` (list)
3. `PATCH /{strategy_name}/validate`
4. `PATCH /{strategy_name}/unvalidate`
5. `GET /{strategy_name}` (detail, ultimo porque captura cualquier path)

---

## 3. Frontend Changes

### 3.1 Types — `frontend/src/types/strategy.ts`

```typescript
export interface Strategy {
  // ... campos existentes ...
  status: 'idea' | 'validated';  // NUEVO
}
```

### 3.2 Service — `frontend/src/services/strategies.ts`

**Modificar `StrategyFilters`**:

```typescript
interface StrategyFilters {
  channel?: string;
  search?: string;
  session_id?: number;
  has_draft?: boolean;
  status?: 'idea' | 'validated';  // NUEVO
}
```

Agregar `status` a la construccion de `URLSearchParams` en `getStrategies()`.

**Nuevas funciones**:

```typescript
export async function validateStrategy(name: string): Promise<Strategy> {
  const { data } = await api.patch<Strategy>(
    `/strategies/${encodeURIComponent(name)}/validate`
  );
  return data;
}

export async function unvalidateStrategy(name: string): Promise<Strategy> {
  const { data } = await api.patch<Strategy>(
    `/strategies/${encodeURIComponent(name)}/unvalidate`
  );
  return data;
}
```

### 3.3 StrategyDetail — `frontend/src/components/strategies/StrategyDetail.tsx`

Este es el cambio mas significativo en el frontend. El componente pasa de ser puro display a tener una accion.

**Cambios en la interfaz**:

```typescript
interface StrategyDetailProps {
  strategy: Strategy;
  onClose: () => void;
  onStatusChange?: () => void;  // NUEVO — callback para notificar que el status cambio
}
```

**Nuevo estado interno**:

```typescript
const [confirmOpen, setConfirmOpen] = useState(false);
const [updating, setUpdating] = useState(false);
```

**Boton de validacion**: Se agrega junto al boton "Cerrar" en el header, con aspecto condicionado al status:

- `status === 'idea'`: Boton verde "Validar estrategia"
- `status === 'validated'`: Boton naranja/amber "Devolver a ideas"

**Flujo al pulsar el boton**:
1. Click en boton → `setConfirmOpen(true)`
2. Se muestra `ConfirmDialog` con mensaje apropiado al status actual
3. Si confirma → `setUpdating(true)` → llama `validateStrategy(name)` o `unvalidateStrategy(name)` → `queryClient.invalidateQueries(...)` → llama `onStatusChange?.()` → `setConfirmOpen(false)` → `setUpdating(false)`
4. Si cancela → `setConfirmOpen(false)`

**ConfirmDialog — textos**:

| Status actual | Titulo | Mensaje | Boton |
|---|---|---|---|
| `idea` | "Validar estrategia" | "Esta idea pasara a la pestana Estrategias. Podras revertirlo luego." | "Validar" |
| `validated` | "Devolver a ideas" | "Esta estrategia volvera a la pestana Ideas." | "Devolver" |

**Nota sobre ConfirmDialog**: El componente existente tiene el boton de confirmar con estilo `bg-red-600`. Para validate (accion positiva) seria mejor verde. Hay dos opciones:
- **Opcion A**: Extender `ConfirmDialog` con prop `variant?: 'danger' | 'success'` que cambie el color del boton.
- **Opcion B**: Usar el rojo existente para ambas acciones (es una confirmacion, no un delete).
- **Recomendacion**: Opcion A es poco trabajo y mejora la UX. Agregar `confirmVariant` prop con default `'danger'`.

### 3.4 StrategiesPage — `frontend/src/pages/StrategiesPage.tsx`

**Cambio principal**: La separacion de tabs pasa de `has_draft` a `status`.

**Ideas tab query**:

```typescript
const { data: ideasData, isLoading: loadingIdeas } = useQuery({
  queryKey: ['ideas', search, channelFilter, sessionFilter],
  queryFn: () => getStrategies({
    search: search || undefined,
    channel: channelFilter || undefined,
    session_id: sessionFilter ? Number(sessionFilter) : undefined,
    status: 'idea',  // CAMBIO: era sin filtro, ahora filtra por status
  }),
  enabled: tab === 'ideas',
});
```

**Estrategias tab query**:

```typescript
const { data: strategiesData, isLoading: loadingStrategies } = useQuery({
  queryKey: ['validated-strategies', search, channelFilter, sessionFilter],
  queryFn: () => getStrategies({
    search: search || undefined,
    channel: channelFilter || undefined,
    session_id: sessionFilter ? Number(sessionFilter) : undefined,
    status: 'validated',  // CAMBIO: era has_draft: true, ahora filtra por status
  }),
  enabled: tab === 'strategies',
});
```

**Empty state para Estrategias tab**: Cambiar el texto de "No hay estrategias traducidas a JSON todavia" a "No hay estrategias validadas todavia".

**onStatusChange callback**: Cuando `StrategyDetail` notifica un cambio de status, el handler cierra el detalle (`setSelectedStrategy(null)`) para que el usuario vuelva al listado actualizado. React Query se encarga del refetch automatico via `invalidateQueries`.

### 3.5 ResearchDetailPage — `frontend/src/pages/ResearchDetailPage.tsx`

**Cambio minimo**: Solo pasar `onStatusChange` a `StrategyDetail`:

```tsx
<StrategyDetail
  strategy={selectedIdea}
  onClose={() => setSelectedIdea(null)}
  onStatusChange={() => setSelectedIdea(null)}  // NUEVO
/>
```

El `invalidateQueries` dentro de `StrategyDetail` se encarga de refrescar los datos. Al cerrar el detalle, el listado de ideas ya estara actualizado.

---

## 4. Data Flow

### Validate flow (completo)

```
1. Usuario ve StrategyDetail con status='idea'
2. Click en "Validar estrategia"
3. ConfirmDialog aparece: "Esta idea pasara a la pestana Estrategias"
4. Click "Validar"
5. StrategyDetail → validateStrategy(name) → PATCH /api/strategies/{name}/validate
6. Backend: SELECT strategy WHERE name=X → UPDATE status='validated' → COMMIT → return strategy dict
7. Response 200 con strategy actualizada
8. StrategyDetail → queryClient.invalidateQueries(['ideas', ...]) + invalidate(['validated-strategies', ...])
9. StrategyDetail → onStatusChange() → parent cierra el detalle
10. Listado se re-renderiza sin la estrategia (ya no tiene status='idea')
```

### Unvalidate flow

Identico al anterior pero con `unvalidateStrategy(name)` y textos invertidos.

### Query invalidation strategy

Al cambiar status, se invalidan TODAS las query keys que contienen estrategias:
- `['ideas', ...]` — porque la estrategia sale o entra del tab Ideas
- `['validated-strategies', ...]` — porque sale o entra del tab Estrategias
- `['strategies-by-session', ...]` — por si se esta viendo desde ResearchDetailPage

Se puede simplificar con un prefijo comun: `queryClient.invalidateQueries({ queryKey: ['ideas'] })` e `invalidateQueries({ queryKey: ['validated-strategies'] })`.

---

## 5. Files Changed Summary

| File | Action | Effort |
|------|--------|--------|
| `api/alembic/versions/004_add_strategy_status.py` | Create | Small |
| `tools/db/models.py` | Edit — add `status` field to `Strategy` | Small |
| `api/models/schemas/strategy.py` | Edit — add `status` to `StrategyResponse` | Small |
| `api/services/strategy_service.py` | Edit — add status filter + validate/unvalidate functions | Medium |
| `api/routers/strategies.py` | Edit — add status param + 2 PATCH endpoints | Medium |
| `frontend/src/types/strategy.ts` | Edit — add `status` field | Small |
| `frontend/src/services/strategies.ts` | Edit — add status filter + 2 new functions | Small |
| `frontend/src/components/common/ConfirmDialog.tsx` | Edit — add `confirmVariant` prop for button color | Small |
| `frontend/src/components/strategies/StrategyDetail.tsx` | Edit — add validate button + modal + API call | Medium |
| `frontend/src/pages/StrategiesPage.tsx` | Edit — change tab filters from has_draft to status | Small |
| `frontend/src/pages/ResearchDetailPage.tsx` | Edit — pass onStatusChange to StrategyDetail | Small |

**Total**: 11 files (1 new, 10 edits). No file is large or complex.

---

## 6. Edge Cases

| Caso | Manejo |
|------|--------|
| Doble click en validar | `updating` state deshabilita el boton mientras la llamada esta en curso |
| Strategy no encontrada (404 en PATCH) | Catch en StrategyDetail, mostrar error en consola. No deberia ocurrir en uso normal. |
| Validar desde ResearchDetailPage | Funciona igual — StrategyDetail es el mismo componente. Al validar, la idea sigue visible en la lista de research (no se filtra por status ahi) pero su status badge cambiara. |
| Migration con datos existentes | Todas las estrategias existentes reciben status='idea'. La pestana Estrategias queda vacia. Comportamiento correcto y esperado. |
| Draft asociado a idea | Los Drafts son independientes del status. Una idea puede tener draft. Una validada puede no tenerlo. No hay conflicto. |
