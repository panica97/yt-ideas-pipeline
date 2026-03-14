---
name: research
description: Orchestrate the research pipeline for a given topic with PostgreSQL session tracking
---

# Research Orchestrator

Orchestrates the full research pipeline for a given topic, tracking progress in PostgreSQL via research sessions.

## Pipeline Steps

```
0. preflight       → Comprobacion de autenticacion
1. yt-scraper       → Buscando videos
2. notebooklm-analyst → Extrayendo estrategias
3. translator       → Traduciendo a JSON
4. cleanup          → Limpieza
5. db-manager       → Guardando en base de datos
6. summary          → Resumen final
```

## Session Tracking (when DATABASE_URL is set)

Track progress in PostgreSQL so the frontend Live page can show real-time updates.

### At pipeline start:

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import create_session

with sync_session_ctx() as session:
    research_session = create_session(session, topic_slug)
    session_id = research_session.id
```

### At each step:

```python
from tools.db.research_repo import update_session_step

with sync_session_ctx() as session:
    update_session_step(session, session_id, step=1, step_name="yt-scraper", channel="ChannelName", videos=["url1", "url2"])
```

### On completion:

```python
from tools.db.research_repo import complete_session

with sync_session_ctx() as session:
    complete_session(session, session_id, result_summary={
        "topic": topic_slug,
        "videos_processed": 5,
        "strategies_found": 2,
        "drafts_created": 1
    })
```

### On error:

```python
from tools.db.research_repo import error_session

with sync_session_ctx() as session:
    error_session(session, session_id, error_detail="NotebookLM timeout after 120s")
```

### Saving history:

After processing each video, record it in research history:

```python
from tools.db.research_repo import add_history

with sync_session_ctx() as session:
    add_history(session, video_id="G0c7GAg-FCY", url="https://youtube.com/watch?v=G0c7GAg-FCY", channel_id=1, topic_id=1, strategies_found=2)
```

## Pipeline Flow

1. **preflight** (step 0): Verify NotebookLM auth, check topic exists
2. **yt-scraper** (step 1): Fetch videos via `/yt-scraper`, update session with channel/videos
3. **notebooklm-analyst** (step 2): Extract strategies from videos
4. **translator** (step 3): Translate YAML strategies to JSON drafts
5. **cleanup** (step 4): Clean up NotebookLM resources
6. **db-manager** (step 5): Save strategies to DB, save history
7. **summary** (step 6): Generate final summary, complete session

## Early Stops

- `NO_VIDEOS_FOUND` at step 1 → complete session with empty summary
- `NO_STRATEGIES_FOUND` at step 2 → complete session with empty summary

## Fallback

If `DATABASE_URL` is not set, the pipeline still runs but without session tracking.
The sub-agents (yt-scraper, notebooklm-analyst, db-manager) each have their own fallback behavior.
