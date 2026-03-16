# Proposal: idea-validation-flow

**Change**: Separar ideas de estrategias validadas mediante un campo de estado en la tabla strategies.

**Date**: 2026-03-16
**Approach**: A — Add status field to strategies table

---

## 1. Intent

Actualmente todas las estrategias extraidas por el pipeline de research se tratan como iguales. La pestana "Ideas" muestra todo y la pestana "Estrategias" filtra por `has_draft` (si tienen un JSON draft asociado). Esto no refleja la realidad del workflow del usuario: primero se descubren ideas, luego el usuario decide cuales son validas.

Este cambio introduce un ciclo de vida explicito: **idea → validated**. Las estrategias entran como ideas y el usuario las promueve manualmente a validadas. La pestana "Estrategias" pasa a mostrar solo las validadas, no las que tienen draft.

---

## 2. Scope

### 2.1 Backend — Database

| Cambio | Detalle |
|--------|---------|
| Migration `004` | `ALTER TABLE strategies ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'idea'`. Backfill existentes como `'idea'`. |
| Model `Strategy` | Nuevo campo `status: str` con default `'idea'`. |
| Sync repo | `upsert_strategy()` no necesita cambios — el default de la columna se encarga. |

### 2.2 Backend — API

| Cambio | Detalle |
|--------|---------|
| Schema | Agregar `status: str` a `StrategyResponse`. |
| Service `list_strategies()` | Nuevo filtro `status` (query param). |
| Service | Nuevo metodo `validate_strategy(name)` y `unvalidate_strategy(name)`. |
| Router | `PATCH /api/strategies/{strategy_name}/validate` — cambia status a `'validated'`. |
| Router | `PATCH /api/strategies/{strategy_name}/unvalidate` — cambia status a `'idea'`. |

### 2.3 Frontend — Types & Services

| Cambio | Detalle |
|--------|---------|
| `Strategy` type | Agregar campo `status: 'idea' \| 'validated'`. |
| `strategies` service | Agregar `status` a filtros de `getStrategies()`. |
| `strategies` service | Nuevas funciones `validateStrategy(name)` y `unvalidateStrategy(name)`. |

### 2.4 Frontend — Pages & Components

| Cambio | Detalle |
|--------|---------|
| `StrategiesPage` | Tab "Ideas" filtra `status=idea`. Tab "Estrategias" filtra `status=validated`. |
| `StrategiesPage` | Dentro del tab "Estrategias", mantener `has_draft` como filtro secundario. |
| `StrategyDetail` | Boton "Validar estrategia" (cuando status=idea) y "Devolver a ideas" (cuando status=validated). Ambos con modal de confirmacion. |
| `StrategyCard` | Badge visual indicando el status (idea vs validated). |
| `ResearchDetailPage` | Permitir validar ideas directamente desde la vista de resultados de research. |

---

## 3. Key Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Validacion tambien disponible desde `ResearchDetailPage` | El usuario revisa ideas en el contexto de un research — debe poder validar sin navegar a otra pagina. |
| 2 | Soporte para "unvalidate" (devolver a idea) | Permite corregir errores. Reversibilidad sin coste. |
| 3 | Modal de confirmacion antes de validar/unvalidar | Previene clicks accidentales. Accion importante merece confirmacion explicita. |
| 4 | `has_draft` se mantiene como filtro secundario en tab Estrategias | Dentro de las validadas, el usuario puede querer ver cuales ya tienen draft JSON y cuales no. |
| 5 | Approach A (status field) sobre Approach B (tablas separadas) | Una idea y una estrategia validada son la misma entidad en distintas fases. Un campo de status es simple, extensible y no rompe nada existente. |

---

## 4. Approach Detail

### Status lifecycle

```
[Research pipeline] → status='idea' → [User validates] → status='validated'
                                    ← [User unvalidates] ←
```

### API endpoints (new)

```
PATCH /api/strategies/{strategy_name}/validate
  → 200 { strategy: StrategyResponse }  (status cambiado a 'validated')
  → 404 Strategy not found

PATCH /api/strategies/{strategy_name}/unvalidate
  → 200 { strategy: StrategyResponse }  (status cambiado a 'idea')
  → 404 Strategy not found
```

### Existing endpoint changes

```
GET /api/strategies?status=idea          → solo ideas
GET /api/strategies?status=validated     → solo validadas
GET /api/strategies                      → todas (backward compatible)
```

### Migration strategy

- La migracion agrega la columna con `DEFAULT 'idea'`, asi que todas las filas existentes se backfillean automaticamente.
- No hay downtime ni data loss.
- La pestana "Estrategias" quedara vacia tras la migracion. Esto es correcto: el usuario debe validar las que considere validas.

---

## 5. Out of Scope

- **Validacion automatica o semi-automatica**: No hay scoring ni suggestion. Es puramente manual.
- **Mas estados** (rejected, archived, etc.): El campo lo soporta, pero solo implementamos `idea` y `validated` ahora.
- **Bulk validation**: Solo individual, una a una. Se puede agregar luego.
- **Notificaciones**: No hay alertas ni toasts tras validar (solo el modal de confirmacion y el cambio visual).
- **Cambios al Draft workflow**: Los drafts siguen funcionando igual, independientes del status.
- **Cambios al pipeline de research**: El pipeline sigue insertando con el default, sin cambios.

---

## 6. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Tab "Estrategias" vacio tras migracion | Low | Comportamiento esperado. El usuario entiende que debe validar. |
| Estrategias existentes todas como "idea" | Low | Correcto — no estaban validadas. Sin ambiguedad. |
| Confusion entre status y has_draft | Low | La UI deja claro que tabs van por status y has_draft es filtro secundario. |
| Modal de confirmacion puede sentirse lento para power users | Low | Aceptable trade-off por seguridad. Se puede revisar luego. |
