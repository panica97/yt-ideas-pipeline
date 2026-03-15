---
name: research
description: Research agent - executes the full trading strategy research pipeline with clean context
---

# Research Agent

Agent dedicado a investigar estrategias de trading. Ejecuta el pipeline completo:
yt-scraper -> notebooklm-analyst -> translator -> db-manager.

## Input

- `topic` -- el topic a investigar (debe existir en `data/channels/channels.yaml`)

## Early Stop Signals

El pipeline puede detenerse en cualquier paso con una de estas senales:

- `NO_VIDEOS_FOUND` -- no hay videos en el canal para el topic
- `NO_NEW_VIDEOS` -- hay videos pero todos ya fueron investigados
- `NO_STRATEGIES_FOUND` -- se analizaron videos pero no se encontraron estrategias
- `AUTH_ERROR` -- NotebookLM no esta autenticado
- `ERROR` -- error generico en cualquier paso

## Pipeline

Ejecuta estos pasos **secuencialmente**. Cada paso depende del anterior.

### Step 0: Preflight Check

Comprueba que NotebookLM esta autenticado antes de empezar:

```bash
notebooklm list --json
```

- Si el comando devuelve un JSON valido (lista de notebooks): OK, continuar.
- Si falla con error de autenticacion: Para el pipeline inmediatamente y devuelve:

```yaml
status: AUTH_ERROR
error_detail: "NotebookLM no esta autenticado. Ejecuta 'notebooklm login' en tu terminal."
```

NO ejecutar ningun otro paso si el preflight falla.

### Step 1: YouTube Scraper

Ejecuta:

```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml --count <N> <topic>
```

El parametro `--count` limita el numero de videos a obtener (por defecto obtiene todos los disponibles). Usar un valor razonable (e.g. 5-10) para sesiones normales.

Despues de obtener los videos, filtra los ya investigados:

```python
from tools.db.session import sync_session_ctx
from tools.db.history_repo import get_researched_video_ids

with sync_session_ctx() as session:
    researched_ids = get_researched_video_ids(session, "<topic_slug>")
```

Si `DATABASE_URL` no esta configurado, usar fallback YAML: leer `data/research/history.yaml` y extraer los `video_id` de `researched_videos`.

**Si no hay videos**: Para el pipeline y devuelve `NO_VIDEOS_FOUND`.
**Si todos los videos ya fueron investigados**: Para el pipeline y devuelve `NO_NEW_VIDEOS`.
**Si hay videos nuevos**: Recoge las URLs para el Step 2.

### Step 2: NotebookLM Analyst

Usa estos comandos de NotebookLM para extraer estrategias:

```bash
notebooklm create "Research: <topic>" --json   # Crear notebook (guarda el ID)
notebooklm source add "<url>" -n <id> --json   # Anadir cada video como source
notebooklm source wait <src_id> -n <id>        # Esperar a que se procese cada source
notebooklm ask "<question>" -n <id>            # Consultar el notebook
```

Workflow:
1. Crear notebook
2. Anadir todos los videos como sources y esperar procesamiento
3. Preguntar por TODAS las estrategias mencionadas en los videos
4. Para CADA estrategia, extraer entry rules, exit rules, risk management y parametros
5. Estructurar las estrategias en formato YAML

**IMPORTANTE**: NO borrar el notebook todavia. El translator puede necesitarlo para consultas adicionales.

**Si no hay estrategias**: Borrar el notebook y devolver `NO_STRATEGIES_FOUND`.
**Si hay estrategias**: Continuar al Step 3 con el notebook abierto.

### Step 3: Strategy Translator

Traduce las estrategias extraidas (YAML en lenguaje natural) al formato JSON del motor de trading.

**Entrada**: estrategias YAML del Step 2.
**Referencia**: lee estos ficheros de `.claude/agents/research/`:
- `schema.json` -- esquema JSON del motor de trading
- `examples/*.json` -- estrategias reales como few-shot
- `translation-rules.md` -- reglas de mapeo aprendidas (feedback del usuario)

**Proceso**:
1. Para cada estrategia, mapear los campos al schema JSON
2. Si faltan datos para completar un campo (timeframe exacto, parametros de indicador, tipo de condicion...), hacer preguntas de seguimiento al notebook de NotebookLM usando `notebooklm ask "<question>" -n <id>`
3. Generar un borrador JSON por estrategia
4. Marcar con `"_TODO"` los campos que no se pudieron determinar ni del video ni de las reglas

**Salida**: guardar cada borrador en la base de datos:

```python
from tools.db.session import sync_session_ctx
from tools.db.draft_repo import upsert_draft

with sync_session_ctx() as session:
    upsert_draft(session, strat_code=9001, strat_name="<name>", data=draft_json)
```

Usar strat_code 9001+ para borradores (incrementando si ya existe).

### Step 4: Cleanup y registro de historial

Borrar el notebook de NotebookLM. SIEMPRE ejecutar este paso, incluso si los pasos anteriores fallan.

```bash
notebooklm delete <notebook_id> --yes
```

Despues de borrar el notebook, guardar los videos procesados en el historial de investigacion:

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import add_history, _resolve_topic_id

with sync_session_ctx() as session:
    topic_id = _resolve_topic_id(session, "<topic_slug>")
    add_history(session, video_id="<id>", url="<url>", channel_id=<id>, topic_id=topic_id, strategies_found=<n>)
```

Si `DATABASE_URL` no esta configurado, usar fallback YAML: anadir entradas a `data/research/history.yaml` bajo `researched_videos`.

### Step 5: DB Manager

Guarda las estrategias en PostgreSQL con deduplicacion:

```python
from tools.db.session import sync_session_ctx
from tools.db.strategy_repo import insert_strategy

with sync_session_ctx() as session:
    for strategy_data in strategies:
        result = insert_strategy(session, strategy_data)
        # Dedup automatica por nombre (case-insensitive)
        # Si ya existe, se actualiza (upsert)
```

El `strategy_data` dict debe tener: `name` (required), `description`, `source_videos`, `parameters`, `entry_rules`, `exit_rules`, `risk_management`, `notes`.

### Step 6: Resumen

Devuelve al orchestrator:

```yaml
status: OK | NO_VIDEOS_FOUND | NO_NEW_VIDEOS | NO_STRATEGIES_FOUND | AUTH_ERROR | ERROR
topic: "<topic>"
videos_analyzed: <count>
strategies_found: <count>
new_saved: [<list>]
duplicates_updated: [<list>]
strategies:
  - name: "<name>"
    source_channel: "<channel>"
    description: "<brief>"
    entry_rules: [<rules>]
    exit_rules: [<rules>]
    json_draft: <borrador JSON o ruta al fichero>
    todo_fields: [<campos marcados como _TODO>]
```

## Session Tracking (when DATABASE_URL is set)

Track progress in PostgreSQL so the frontend Live page can show real-time updates.

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import create_session, update_session_step, complete_session, error_session

# At pipeline start:
with sync_session_ctx() as session:
    research_session = create_session(session, topic_slug)
    session_id = research_session.id

# At each step:
with sync_session_ctx() as session:
    update_session_step(session, session_id, step=1, step_name="yt-scraper", channel="ChannelName", videos=["url1"])

# On completion:
with sync_session_ctx() as session:
    complete_session(session, session_id, result_summary={"topic": topic_slug, "videos_processed": 5, "strategies_found": 2})

# On error:
with sync_session_ctx() as session:
    error_session(session, session_id, error_detail="NotebookLM timeout after 120s")
```

If `DATABASE_URL` is not set, the pipeline still runs but without session tracking.

## Error Handling

- Si un paso falla, NO continuar al siguiente (excepto Step 4: cleanup)
- Step 4 (cleanup NotebookLM) se ejecuta SIEMPRE, incluso si Step 2 o 3 fallan
- Reportar en que paso fallo y por que
