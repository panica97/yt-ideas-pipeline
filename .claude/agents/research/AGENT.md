---
name: research
description: Research agent - executes the full trading strategy research pipeline with clean context
---

# Research Agent

Agent dedicado a investigar estrategias de trading. Ejecuta el pipeline completo:
yt-scraper -> notebooklm-analyst -> strategy-variants -> strategy-translator -> todo-review -> db-manager.

## Input

- `input` -- one of:
  - A topic slug (must exist in `data/channels/channels.yaml`) -- runs full pipeline
  - A YouTube video URL (https://youtube.com/watch?v=... or https://youtu.be/...) -- skips Steps 1 and 1.5
  - A raw idea string (anything else) -- skips Steps 1, 1.5, and 2
- `save_conversations` -- (optional, default false) si true, guardar el historial de conversaciones con NotebookLM antes del cleanup

## Entry Point Detection

Determine the entry point type from the input:

1. **URL**: input matches `youtube.com/watch` or `youtu.be/` -> VIDEO entry point
2. **Topic**: input matches a slug in `data/channels/channels.yaml` -> TOPIC entry point
3. **Idea**: anything else -> IDEA entry point

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

**VIDEO and IDEA entry points**: Skip this step entirely.
For VIDEO: extract metadata with `yt-dlp --print title --print channel --print channel_url <url>`.
For IDEA: no video metadata needed.

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
**Si hay videos nuevos**: Recoge las URLs para el Step 1.5.

### Step 1.5: Video Classifier

**VIDEO and IDEA entry points**: Skip this step entirely.

Clasifica los videos nuevos para filtrar los que no contienen estrategias de trading.

Clasifica cada titulo de video tu mismo, sin ejecutar ningun script. Para cada video, decide:

- `strategy`: el titulo sugiere una estrategia de trading concreta, sistema, metodo, backtest, algoritmo o setup con indicadores
- `irrelevant`: setup tours, Q&As, vlogs, gear reviews, historias personales, comentario de mercado sin estrategia accionable

**Regla conservadora**: en caso de duda, clasificar como `strategy`.

**Proceso**:
1. Tomar los videos del Step 1
2. Clasificar cada titulo como `strategy` o `irrelevant` con una razon breve
3. Separar videos en dos grupos: `strategy` e `irrelevant`
4. Para los videos `irrelevant`, registrarlos en el historial de investigacion:

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import add_history, _resolve_topic_id

with sync_session_ctx() as session:
    topic_id = _resolve_topic_id(session, "<topic_slug>")
    for video in irrelevant_videos:
        add_history(session, video_id=video["video_id"], url=video["url"],
                    channel_id=video.get("channel_id"), topic_id=topic_id,
                    strategies_found=0, classification="irrelevant")
```

5. Pasar solo los videos `strategy` al Step 2

**Si todos los videos son irrelevantes**: Para el pipeline y devuelve `NO_STRATEGIES_FOUND`.
**Si hay videos strategy**: Continuar al Step 2 con esos videos.

### Step 2: NotebookLM Analyst

**IDEA entry point**: Skip this step. Format the idea text as a strategy YAML and pass directly to Step 3.
**VIDEO entry point**: Use the single video URL as the only source.

Usa el skill `notebooklm-analyst` (leer `.claude/skills/notebooklm-analyst/SKILL.md` para el workflow detallado).

Comandos base:

```bash
notebooklm create "Research: <topic>" --json   # Crear notebook (guarda el ID)
notebooklm source add "<url>" -n <id> --json   # Anadir cada video como source
notebooklm source wait <src_id> -n <id>        # Esperar a que se procese cada source
notebooklm ask "<question>" -n <id>            # Consultar el notebook
```

El analyst ejecuta 3 rondas de preguntas:
1. **Discovery**: identificar TODAS las estrategias
2. **Rules extraction**: para cada estrategia, extraer entry/exit rules concretas con indicadores y thresholds exactos
3. **Context extraction**: mercados recomendados/a evitar, timeframes recomendados/a evitar

Output: lista de estrategias en formato YAML con campos `entry_rules`, `exit_rules`, `recommended_markets`, `recommended_timeframes`, `avoid_timeframes`, `avoid_markets`, `notes`.

**IMPORTANTE**: NO borrar el notebook todavia.

**Si no hay estrategias**: Borrar el notebook y devolver `NO_STRATEGIES_FOUND`.
**Si hay estrategias**: Continuar al Step 3.

### Step 3: Strategy Variants

Invocar skill: `/strategy-variants`

Input: el YAML completo del analyst (Step 2).

El skill:
1. **Purifica**: quita SL/TP y risk management, deja solo entrada/salida
2. **Separa direcciones**: si hay long+short, genera dos estrategias independientes
3. **Propone exit method**: usa lo que dice el source o propone num_bars con _TODO
4. **Propone variantes**: combina mercados y timeframes recomendados (max 5 por estrategia original)

Output: lista de variantes YAML, cada una con `variant_name`, `direction`, `symbol`, `timeframe`, `entry_rules`, `exit_rules`, `indicators_needed`, `notes`.

### Step 4: Strategy Translator

Invocar skill: `/strategy-translator`

Input: la lista de variantes del Step 3.

El translator traduce CADA variante a un JSON draft IBKR (1 variante = 1 JSON). Es una traduccion literal, sin decisiones creativas. Guarda los drafts en la BD con `upsert_draft()`.

### Step 4.5: TODO Auto-Resolution

After strategy-translator produces JSON drafts (Step 4), auto-fill resolvable `_TODO` fields before persisting to the database (Step 5/6).

Invocar skill: `/todo-review`

Input: the `strat_code` list from Step 4 (all newly translated drafts).

The skill resolves `_TODO` fields in three tiers:
1. **Instrument lookup**: exchange, multiplier, minTick, currency, secType from the Instruments DB
2. **Sensible defaults**: rolling_days, currency, secType, trading_hours
3. **Never auto-fill**: indicator params, condition thresholds, control_params (left for human review)

This reduces manual TODO work -- only genuinely ambiguous TODOs reach the user via todo-fill.

**Skip conditions**: NONE -- always run this step for all entry points (TOPIC, VIDEO, IDEA).

### Step 5: Cleanup y registro de historial

**IDEA entry point**: No notebook to delete, no history to record. Skip to Step 6.
**VIDEO entry point**: Record history with topic_id=None. channel_id is resolved if the channel exists in DB, otherwise None.

**Si `save_conversations` es true**, guardar el historial ANTES de borrar el notebook:

```bash
# Capturar el historial completo de la conversacion
notebooklm history -n <notebook_id>
```

Guardar la salida en `data/research/conversations/<topic_slug>_<YYYY-MM-DD>.md` con el formato:

```markdown
# Conversacion NotebookLM: <topic>
Fecha: <YYYY-MM-DD>
Notebook ID: <notebook_id>
Videos analizados: <lista de URLs>

---

<output del comando notebooklm history>
```

Crear el directorio `data/research/conversations/` si no existe.

**Despues**, borrar el notebook. SIEMPRE ejecutar el delete, incluso si los pasos anteriores fallan.

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

### Step 6: DB Manager

Guarda las estrategias padre y sus drafts variantes en PostgreSQL. Sigue el flujo definido en `.claude/skills/db-manager/SKILL.md`.

El proceso es:

1. **Group variants by `parent_strategy`** name from the strategy-variants output
2. **For each parent strategy**:
   a. Resolve `source_channel` name to `source_channel_id` using `get_channel_by_name()`
   b. Call `insert_strategy()` with `source_channel_id` in the data dict
   c. Capture the returned `Strategy.id`
3. **For each variant draft** of that parent:
   a. Call `upsert_draft()` with `strategy_id=parent.id` to link the draft

```python
from tools.db.session import sync_session_ctx
from tools.db.strategy_repo import insert_strategy
from tools.db.draft_repo import upsert_draft
from tools.db.channel_repo import get_channel_by_name

with sync_session_ctx() as session:
    # Group variants by parent_strategy name
    parents = {}
    for variant in all_variants:
        pname = variant["parent_strategy"]
        parents.setdefault(pname, []).append(variant)

    for parent_name, variants in parents.items():
        # Resolve channel name to ID if available
        source_channel_id = None
        ch_name = variants[0].get("source_channel")
        if ch_name:
            ch = get_channel_by_name(session, ch_name)
            if ch:
                source_channel_id = ch.id

        # Create/update parent strategy
        parent = insert_strategy(session, {
            "name": parent_name,
            "description": variants[0].get("description", ""),
            "source_channel_id": source_channel_id,
            "source_videos": variants[0].get("source_videos", []),
            "entry_rules": variants[0].get("entry_rules", []),
            "exit_rules": variants[0].get("exit_rules", []),
        })

        # Create drafts linked to parent
        for v in variants:
            upsert_draft(
                session,
                strat_code=v["strat_code"],
                strat_name=v["variant_name"],
                data=v["draft_json"],
                strategy_id=parent.id,
            )
```

### Step 7: Resumen

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

## Session Tracking

Session tracking is MANDATORY for ALL entry points when DATABASE_URL is set. Track progress in PostgreSQL so the frontend Live page can show real-time updates.

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import create_session, update_session_step, complete_session, error_session

# At pipeline start -- call create_session() based on entry point:
with sync_session_ctx() as session:
    # TOPIC entry point:
    research_session = create_session(session, topic_slug=topic)

    # VIDEO entry point:
    research_session = create_session(session, label=f"Video: {video_title or video_url}")

    # IDEA entry point:
    research_session = create_session(session, label=f"Idea: {idea_text[:100]}")

    session_id = research_session.id

# At each step (even if some steps are skipped):
with sync_session_ctx() as session:
    update_session_step(session, session_id, step=1, step_name="yt-scraper", channel="ChannelName", videos=["url1"])

# On completion -- always pass stats:
with sync_session_ctx() as session:
    complete_session(session, session_id,
        result_summary={"topic": topic_slug, "videos_processed": 5, "strategies_found": 2},
        strategies_found=<count>,
        drafts_created=<count>,
    )

# On error:
with sync_session_ctx() as session:
    error_session(session, session_id, error_detail="NotebookLM timeout after 120s")
```

If `DATABASE_URL` is not set, the pipeline still runs but without session tracking.

## Error Handling

- Si un paso falla, NO continuar al siguiente (excepto Step 5: cleanup)
- Step 5 (cleanup NotebookLM) se ejecuta SIEMPRE, incluso si Steps 2-4 fallan
- Reportar en que paso fallo y por que
