# Tools

Scripts Python en `tools/` que se ejecutan como modulos.

## YouTube (`tools/youtube/`)

### Busqueda por keyword

```bash
python -m tools.youtube.search "futures trading" --count 5 --months 3
```

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--count N` | 20 | Numero de resultados |
| `--months N` | 6 | Solo videos de los ultimos N meses |
| `--no-date-filter` | — | Sin filtro de fecha |

Devuelve: titulo, canal (subs), views, duracion, fecha, URL.

### Fetch por topic

```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml futures --days 14
```

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--db <path>` | — | Ruta a channels.yaml (requerido) |
| `--days N` | 7 | Solo videos de los ultimos N dias |
| `--count N` | 30 | Maximo de resultados |

Busca en paralelo (4 workers) en todos los canales del topic. Actualiza `last_fetched` automaticamente.

### Gestion de canales

```bash
python -m tools.youtube.channels --db data/channels/channels.yaml <comando>
```

| Comando | Descripcion |
|---------|-------------|
| `topics` | Lista todos los topics |
| `list [topic]` | Muestra canales (todos o por topic) |
| `add <topic> <url> [--name N]` | Anade canal a un topic |
| `remove <topic> <url>` | Elimina canal de un topic |

## Base de datos (`tools/db/`)

Capa de acceso a datos con SQLAlchemy 2.0 y PostgreSQL 16.

### Modelos ORM (`models.py`)

| Modelo | Tabla | Descripcion |
|--------|-------|-------------|
| `Topic` | `topics` | Topics de investigacion (slug, descripcion) |
| `Channel` | `channels` | Canales YouTube vinculados a un topic |
| `Strategy` | `strategies` | Estrategias extraidas (nombre, reglas, parametros en JSONB) |
| `Draft` | `drafts` | Borradores de estrategias con deteccion de TODOs |
| `Instrument` | `instruments` | Tabla de referencia de instrumentos (symbol, exchange, multiplier, min_tick) |
| `ResearchHistory` | `research_history` | Videos investigados (video_id + topic, unique) |
| `ResearchSession` | `research_sessions` | Sesiones de research en curso (status, step, progress) |

Todos los modelos con timestamps usan `TimestampMixin` (created_at, updated_at).

### Session management (`session.py`)

Provee `sync_session_ctx()`, un context manager para obtener sesiones sincronas:

```python
from tools.db.session import sync_session_ctx

with sync_session_ctx() as session:
    # operaciones con la BD
    pass
```

Requiere la variable de entorno `DATABASE_URL`.

### Repositorios

| Archivo | Funciones principales |
|---------|----------------------|
| `strategy_repo.py` | CRUD de estrategias, busqueda full-text |
| `draft_repo.py` | CRUD de drafts, deteccion de campos TODO, activacion/desactivacion |
| `channel_repo.py` | CRUD de canales por topic |
| `instrument_repo.py` | CRUD de instrumentos de referencia |
| `history_repo.py` | Registro de videos investigados, `get_researched_video_ids()` |
| `research_repo.py` | Gestion de sesiones de research (crear, actualizar paso, completar) |

## Slash commands

Los slash commands son la interfaz principal desde Claude Code:

### `/research`

Lanza el pipeline completo de investigacion para un topic. Ver `.claude/skills/research/SKILL.md`.

### `/notebooklm`

Referencia completa en `.claude/skills/notebooklm/SKILL.md`.

> **Nota:** Las operaciones de YouTube (busqueda, fetch por topic, gestion de canales) se ejecutan via `python -m tools.youtube.search`, `python -m tools.youtube.fetch_topic` y `python -m tools.youtube.channels` directamente, o a traves del skill `yt-scraper` dentro del pipeline de research. No existen como slash commands independientes.
