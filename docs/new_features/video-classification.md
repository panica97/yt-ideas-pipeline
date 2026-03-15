# PRD: Clasificador de videos (Pre-filtro por titulo)

## 1. Problema

Algunos canales de YouTube tienen contenido mixto: videos sobre estrategias de trading junto con tours de setup, Q&As, comentarios de mercado y vlogs personales. Actualmente el pipeline envia **todos** los videos a NotebookLM para analisis, lo que supone:

- **Gasto innecesario de creditos** de NotebookLM en videos irrelevantes
- **Tiempo de procesamiento desperdiciado** — cada video tarda varios minutos en analizarse
- **Ruido en la base de datos** — investigaciones sin estrategias extraidas que dificultan el analisis

## 2. Solucion

Un nuevo paso ligero (**Step 1.5: video-classifier**) entre `yt-scraper` y `notebooklm-analyst` que clasifica cada video por su titulo usando **Claude Haiku**. Solo dos categorias:

| Categoria | Descripcion | Accion |
|-----------|-------------|--------|
| `strategy` | Probablemente contiene una estrategia de trading concreta | Continua al paso 2 |
| `irrelevant` | No contiene estrategias (setup tours, Q&As, vlogs, resenas) | Se descarta |

Los videos `irrelevant` se registran en `research_history` con `strategies_found=0` y `classification='irrelevant'`, sin pasar por NotebookLM.

### Pipeline actualizado

```
0. preflight
1. yt-scraper          -> fetch videos
1.5. video-classifier  -> NUEVO: clasificar por titulo (Haiku)
2. notebooklm-analyst  -> extraer estrategias (solo videos "strategy")
3. translator          -> traducir ideas a JSON
4. cleanup
5. db-manager
6. summary
```

## 3. Estado actual (Implementado)

Todo lo siguiente ya esta construido y funcionando:

- **Pipeline completo de research**: `yt-scraper` -> `notebooklm-analyst` -> `translator` -> `db-manager`
- **Frontend dashboard** con paginas de sesiones de research, ideas y estrategias
- **PostgreSQL** con tablas: `channels`, `strategies`, `research_history`, `research_sessions`
- **Docker** con servicios: postgres, api, frontend, pipeline
- **Integracion con NotebookLM** para extraccion de estrategias desde videos
- **Distincion Ideas vs Estrategias**: ideas = YAML crudo extraido, estrategias = ideas con JSON draft generado por el translator

## 4. Implementacion pendiente

### 4.1 Video classifier (Step 1.5) — Estado: Pendiente

Nuevo skill `.claude/skills/video-classifier/SKILL.md` que:

- Recibe la lista de videos (output de yt-scraper)
- Clasifica cada titulo con **Claude Haiku** como `strategy` o `irrelevant`
- Criterio conservador: en caso de duda, clasificar como `strategy`
- Se puede hacer en batch (varios titulos en un solo prompt) para minimizar llamadas
- Devuelve la lista filtrada (solo `strategy`) + resumen de filtrado

### 4.2 Cambio en BD — Estado: Pendiente

Anadir columna `classification` a `research_history`:

```sql
ALTER TABLE research_history
ADD COLUMN classification VARCHAR(20) DEFAULT NULL;
-- Valores: 'strategy', 'irrelevant', NULL (registros legacy)
```

Migracion Alembic:

```python
def upgrade():
    op.add_column('research_history',
        sa.Column('classification', sa.String(20), nullable=True))

def downgrade():
    op.drop_column('research_history', 'classification')
```

### 4.3 Cambio en el orquestador `/research` — Estado: Pendiente

- Insertar paso 1.5 entre yt-scraper y notebooklm-analyst
- Filtrar videos `irrelevant` antes de pasar al paso 2
- Registrar videos irrelevantes en `research_history` con `strategies_found=0` y `classification='irrelevant'`
- El resumen del pipeline incluye: `X videos encontrados, Y clasificados como strategy, Z descartados como irrelevant`

### 4.4 Cambio en la API — Estado: Pendiente

**`GET /api/research/{id}`**
- Incluir campo `classification` en los videos del detalle de una sesion

**`GET /api/dashboard/stats`**
- Anadir `irrelevant_videos_filtered` (total de videos descartados historicamente)

### 4.5 Cambio en el frontend — Estado: Pendiente

**Detalle de investigacion (`ResearchDetailPage.tsx`)**
- Mostrar que videos fueron descartados y por que (badge: verde=strategy, gris=irrelevant)
- Seccion colapsable con los videos irrelevantes

**Tipos TypeScript**
```typescript
interface ResearchVideo {
  // ... campos existentes
  classification: 'strategy' | 'irrelevant' | null;
}
```

## 5. Cambios tecnicos (resumen)

| Componente | Cambio | Detalle |
|------------|--------|---------|
| **BD** | Nueva columna | `research_history.classification` (varchar, nullable) |
| **Pipeline** | Nuevo step 1.5 | Skill `video-classifier` con Claude Haiku |
| **Pipeline** | Modificar orquestador | Insertar paso 1.5, filtrar irrelevantes |
| **API** | Modificar endpoints | Exponer `classification` en research detail y stats |
| **Frontend** | Modificar research detail | Mostrar clasificacion de videos, seccion de descartados |

### Orden de implementacion

```
1. BD (migracion) -> 2. video-classifier (skill) -> 3. orquestador /research -> 4. API -> 5. Frontend
```

## 6. Fuera de alcance

Se descarto lo siguiente del PRD original para simplificar:

| Descartado | Motivo |
|------------|--------|
| Categoria `knowledge` en clasificacion pre-filtro | Innecesario. Si un video no es estrategia, es irrelevante para el pipeline. No vale la pena gastar creditos de NotebookLM en "conocimiento general". |
| Clasificacion post-extraccion (idea vs knowledge) | Todo lo que NotebookLM extrae es una idea de estrategia. No necesitamos subcategorizar. |
| Campo `category` en tabla `strategies` | Sin la distincion idea/knowledge, no hace falta. |
| Contadores separados Ideas/Knowledge en dashboard | No aplica sin la categoria knowledge. |
| Filtro por categoria en `StrategiesPage` | No aplica sin la categoria knowledge. |
| Endpoint `GET /api/stats/classification` | Sobredimensionado para el alcance actual. Las stats basicas van en el endpoint existente de dashboard. |
