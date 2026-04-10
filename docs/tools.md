# Tools

Python scripts in `tools/` executed as modules.

## YouTube (`tools/youtube/`)

### Keyword search

```bash
python -m tools.youtube.search "futures trading" --count 5 --months 3
```

| Flag | Default | Description |
|------|---------|-------------|
| `--count N` | 20 | Number of results |
| `--months N` | 6 | Only videos from the last N months |
| `--no-date-filter` | -- | No date filter |

Returns: title, channel (subs), views, duration, date, URL.

### Fetch by topic

```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml futures --days 14
```

| Flag | Default | Description |
|------|---------|-------------|
| `--db <path>` | -- | Path to channels.yaml (required) |
| `--days N` | 7 | Only videos from the last N days |
| `--count N` | 30 | Max results |

Searches in parallel (4 workers) across all channels for the topic. Automatically updates `last_fetched`.

### Channel management

```bash
python -m tools.youtube.channels --db data/channels/channels.yaml <command>
```

| Command | Description |
|---------|-------------|
| `topics` | List all topics |
| `list [topic]` | Show channels (all or by topic) |
| `add <topic> <url> [--name N]` | Add channel to a topic |
| `remove <topic> <url>` | Remove channel from a topic |

## Database (`tools/db/`)

Data access layer with SQLAlchemy 2.0 and PostgreSQL 16.

### ORM models (`models.py`)

| Model | Table | Description |
|-------|-------|-------------|
| `Topic` | `topics` | Research topics (slug, description) |
| `Channel` | `channels` | YouTube channels linked to a topic |
| `Strategy` | `strategies` | Extracted strategies (name, rules, JSONB parameters) |
| `Draft` | `drafts` | Strategy drafts with TODO detection |
| `Instrument` | `instruments` | Instrument reference table (symbol, exchange, multiplier, min_tick) |
| `ResearchHistory` | `research_history` | Researched videos (video_id + topic, unique) |
| `ResearchSession` | `research_sessions` | Active research sessions (status, step, progress) |

All models with timestamps use `TimestampMixin` (created_at, updated_at).

### Session management (`session.py`)

Provides `sync_session_ctx()`, a context manager for synchronous sessions:

```python
from tools.db.session import sync_session_ctx

with sync_session_ctx() as session:
    # database operations
    pass
```

Requires the `DATABASE_URL` environment variable.

### Repositories

| File | Main functions |
|------|---------------|
| `strategy_repo.py` | Strategy CRUD, full-text search |
| `draft_repo.py` | Draft CRUD, TODO field detection, activate/deactivate |
| `channel_repo.py` | Channel CRUD by topic |
| `instrument_repo.py` | Instrument reference CRUD |
| `history_repo.py` | Researched video tracking, `get_researched_video_ids()` |
| `research_repo.py` | Research session management (create, update step, complete) |

## Slash commands

Slash commands are the primary interface from Claude Code:

### Research

Research is handled by the agent architecture (CEO routing in `CLAUDE.md` dispatches to `.claude/agents/research-manager/AGENT.md`). There is no standalone `/research` slash command — tell the CEO what you want to research and it routes to the appropriate agents.

### `/notebooklm`

Full reference in `.claude/skills/notebooklm/SKILL.md`.

> **Note:** YouTube operations (search, fetch by topic, channel management) are run via `python -m tools.youtube.search`, `python -m tools.youtube.fetch_topic`, and `python -m tools.youtube.channels` directly, or through the `yt-scraper` skill within the research pipeline. They do not exist as standalone slash commands.
