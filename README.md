# IRT (Ideas Research Team)

Trading strategy research pipeline. Monitors YouTube channels, extracts strategies with NotebookLM, translates them to IBKR format, and persists them in PostgreSQL with a real-time dashboard.

## Stack

- **Orchestrator:** Claude Code CLI
- **Backend:** Python 3.12, FastAPI
- **Frontend:** React 18 + TypeScript + Tailwind CSS + Lucide React
- **Database:** PostgreSQL 16
- **Scraping:** yt-dlp
- **Analysis:** NotebookLM (notebooklm-py)
- **Deploy:** Docker + Docker Compose

## Research pipeline

```
preflight -> yt-scraper -> video-classifier -> notebooklm-analyst -> strategy-variants -> strategy-translator -> db-manager
```

0. **Preflight** -- verify NotebookLM authentication
1. **yt-scraper** -- fetch recent videos from registered trading channels
2. **video-classifier** -- filter out irrelevant videos
3. **notebooklm-analyst** -- analyze videos and extract structured strategies (YAML)
4. **strategy-variants** -- purify, split long/short, generate variants
5. **strategy-translator** -- translate strategies to IBKR JSON format
6. **db-manager** -- persist to PostgreSQL with deduplication

Launch by telling the CEO what you want to research from Claude Code (e.g., "research futures strategies").

## Project structure

```
api/                    FastAPI backend (port 8000)
  routers/              REST endpoints
  models/               SQLAlchemy models
  services/             Business logic
  alembic/              DB migrations
frontend/               React dashboard (port 5173)
  src/                  TypeScript source
tools/                  Pipeline Python scripts
  youtube/              Search and scraping (yt-dlp)
  db/                   ORM models, repositories, session (SQLAlchemy)
scripts/                Auxiliary scripts
config/                 Global configuration
data/                   Persistent data (channels, strategies)
openspec/               SDD artifacts (planned changes)
docs/                   Documentation
.claude/skills/         Claude Code skills (9 skills: research, yt-scraper,
                        notebooklm, notebooklm-analyst, video-classifier,
                        strategy-variants, strategy-translator, db-manager, todo-fill)
```

## Requirements

- Docker and Docker Compose
- `.env` file with required variables (see `.env.example`)

## How to run

```bash
# Start all services
docker compose up -d

# Dashboard: http://localhost:5173
# API:       http://localhost:8000

# Run pipeline manually
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5

# View registered channels
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `frontend` | 5173 | React dashboard |
| `api` | 8000 | FastAPI API |
| `postgres` | 5432 | Database |
| `pipeline` | -- | Pipeline scripts (on demand) |
