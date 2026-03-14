---
name: yt-scraper
description: Fetch recent videos from monitored YouTube channels by topic using yt-dlp
---

# YouTube Scraper

Fetches recent videos from channels registered in the database for a given topic. Never searches YouTube freely.

## Tool

```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml <topic>
```

Note: If `DATABASE_URL` is set, channels are read from PostgreSQL automatically (YAML is fallback).

## Rules

- ONLY use the command above to get videos
- NEVER search YouTube freely -- only use channels from the DB
- Extract all video URLs from the command output

## Filtrado de videos ya investigados

Despues de obtener los videos del comando, filtra los que ya fueron investigados:

### Si DATABASE_URL esta configurado (preferido):

```python
from tools.db.session import sync_session_ctx
from tools.db.research_repo import _resolve_topic_id
from tools.db.models import ResearchHistory
from sqlalchemy import select

with sync_session_ctx() as session:
    topic_id = _resolve_topic_id(session, "<topic_slug>")
    stmt = select(ResearchHistory.video_id).where(ResearchHistory.topic_id == topic_id)
    researched_ids = set(session.execute(stmt).scalars().all())
```

Luego filtra los videos cuyo `video_id` ya exista en `researched_ids`.

### Si DATABASE_URL NO esta configurado (fallback YAML):

1. Lee `data/research/history.yaml`
2. Extrae los `video_id` de la lista `researched_videos`
3. Para cada video obtenido, extrae su `video_id` de la URL (el parametro `v=`)
4. Descarta los videos cuyo `video_id` ya exista en el historial
5. Devuelve solo los videos NUEVOS (no investigados previamente)

## Output Format

```
https://youtube.com/watch?v=xxx
https://youtube.com/watch?v=yyy
```

- Si no hay videos en el canal: devolver exactamente `NO_VIDEOS_FOUND`
- Si hay videos pero TODOS ya fueron investigados: devolver exactamente `NO_NEW_VIDEOS`

## Error Handling

- Command fails (exit code != 0): report the error, return `NO_VIDEOS_FOUND`
- Topic doesn't exist in the DB: report available topics, return `NO_VIDEOS_FOUND`
- No recent videos: return `NO_VIDEOS_FOUND`
- Database connection error: fall back to YAML history check
