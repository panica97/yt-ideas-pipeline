# Architecture

## Overview

IRT (Ideas Research Team) is a trading strategy research pipeline. It monitors YouTube channels, extracts strategies using NotebookLM, classifies and translates them, and persists them in PostgreSQL for analysis. The React frontend provides a real-time dashboard for managing the entire workflow.

## Stack

| Component | Technology |
|-----------|-----------|
| Orchestrator | Claude Code CLI |
| Backend API | Python 3.12 + FastAPI |
| Frontend | React 18 + TypeScript + Tailwind CSS + Lucide React |
| Database | PostgreSQL 16 |
| Scripts | Python 3.12 (yt-dlp, SQLAlchemy) |
| Strategy extraction | NotebookLM (notebooklm-py) |
| Container | Docker Compose (api, frontend, postgres) |

## Data flow

```
YouTube
  |
  v
yt-scraper (fetch videos by topic)
  |
  v
video-classifier (filter non-strategy videos)
  |
  v
NotebookLM analyst (extract strategies)
  |
  v
strategy-variants (generate variants)
  |
  v
strategy-translator (translate to DB format)
  |
  v
db-manager (persist with deduplication)
  |
  v
PostgreSQL
  |
  v
FastAPI API (REST endpoints)
  |
  v
React dashboard (visualization and management)
```

## Directory structure

```
IRT/
├── CLAUDE.md                     Project context for Claude Code
├── Dockerfile                    Python 3.12-slim image
├── docker-compose.yml            Services: api, frontend, postgres
├── requirements.txt              Python dependencies
├── .env                          Secrets (not versioned)
├── api/                          FastAPI backend
│   ├── routers/                  REST endpoints
│   │   ├── strategies.py         CRUD strategies + drafts (list, detail, data update, TODO fill)
│   │   ├── channels.py           CRUD channels by topic
│   │   ├── history.py            Research history + stats
│   │   ├── instruments.py        Instrument reference table CRUD
│   │   ├── stats.py              Dashboard statistics
│   │   ├── research.py           Active research sessions
│   │   ├── topics.py             CRUD topics
│   │   ├── export.py             Data export (channels, strategies, drafts)
│   │   └── health.py             Health check
│   ├── services/                 Business logic
│   │   ├── strategy_service.py
│   │   ├── channel_service.py
│   │   ├── history_service.py
│   │   ├── instrument_service.py
│   │   ├── research_session_service.py
│   │   ├── research_watcher.py
│   │   ├── stats_service.py
│   │   ├── topic_service.py
│   │   ├── export_service.py
│   │   └── import_service.py
│   └── models/
│       └── schemas/              Pydantic schemas
├── frontend/                     React dashboard
│   └── src/
│       ├── components/
│       │   ├── layout/           Sidebar, Header, Layout, theme toggle
│       │   ├── common/           ConfirmDialog, LoadingSpinner, StatsCard, StatusBadge, TodoBadge
│       │   ├── strategies/       Draft viewer, strategy cards, indicator table, TODO highlighting
│       │   │   └── draft-sections/  Section panels: Instrument, Indicators, Conditions, Risk, Backtest, Notes
│       │   ├── channels/         Channel cards, forms, topic groups
│       │   ├── history/          History table and filters
│       │   └── live/             Real-time research (progress bar, step indicator)
│       ├── pages/                9 pages (see Frontend section)
│       ├── services/             API client (Axios): api, strategies, channels, history, instruments, research, stats
│       └── hooks/                useTheme, useResearchStatus, useWebSocket
├── tools/                        Executable Python scripts
│   ├── youtube/                  yt-dlp scraping
│   │   ├── search.py            General YouTube search
│   │   ├── fetch_topic.py       Fetch videos from channels by topic
│   │   ├── channels.py          Channel database management
│   │   └── formatting.py        Result formatting
│   ├── db/                       Database layer (SQLAlchemy)
│   │   ├── models.py            ORM models (Strategy, Draft, Channel, Instrument, etc.)
│   │   ├── session.py           Session factory and context manager
│   │   ├── base.py              Declarative base + TimestampMixin
│   │   ├── strategy_repo.py     Strategy repository
│   │   ├── draft_repo.py        Draft repository (with TODO detection)
│   │   ├── channel_repo.py      Channel repository
│   │   ├── instrument_repo.py   Instrument repository
│   │   ├── history_repo.py      Research history repository
│   │   └── research_repo.py     Research session repository
│   └── __init__.py
├── .claude/
│   ├── skills/                   Pipeline skills (9 skills)
│   │   ├── research/            Pipeline orchestrator
│   │   ├── yt-scraper/          Fetch videos by topic
│   │   ├── video-classifier/    Classify videos (strategy vs non-strategy)
│   │   ├── notebooklm/          Full NotebookLM API
│   │   ├── notebooklm-analyst/  Strategy extraction
│   │   ├── strategy-variants/   Generate strategy variants
│   │   ├── strategy-translator/ Translate strategies to DB format
│   │   ├── db-manager/          PostgreSQL persistence
│   │   └── todo-fill/           Fill TODO fields in drafts
│   └── agents/
│       └── research/            Research agent (full pipeline)
├── config/                       Global configuration
│   └── settings.json
├── data/                         Persistent data
│   ├── channels/                YouTube channel database (YAML)
│   ├── strategies/              Extracted strategies (YAML, legacy)
│   ├── research/                Research history (YAML, legacy)
│   └── backtests/               Placeholder for future backtesting
├── docs/                         Project documentation
├── openspec/                     SDD artifacts
└── planes/                       Plans and roadmap (gitignored)
```

## Skills

| Skill | Directory | Purpose |
|-------|-----------|---------|
| research-manager | `.claude/agents/research-manager/` | Research pipeline orchestrator (agent, not skill) |
| yt-scraper | `.claude/skills/yt-scraper/` | Fetch videos by topic from registered channels |
| video-classifier | `.claude/skills/video-classifier/` | Filter out videos that don't contain strategies |
| notebooklm | `.claude/skills/notebooklm/` | Full NotebookLM API |
| notebooklm-analyst | `.claude/skills/notebooklm-analyst/` | Extract trading strategies from videos |
| strategy-variants | `.claude/skills/strategy-variants/` | Generate variants for each extracted strategy |
| strategy-translator | `.claude/skills/strategy-translator/` | Translate strategies to DB format |
| db-manager | `.claude/skills/db-manager/` | PostgreSQL persistence with deduplication |
| todo-fill | `.claude/skills/todo-fill/` | Fill pending TODO fields in drafts |

## Frontend

9 pages with light/dark theme and collapsible sidebar:

| Page | Route | Description |
|------|-------|-------------|
| Login | `/login` | Authentication |
| Dashboard | `/` | Overview with statistics |
| Research | `/research` | Launch and view research sessions |
| Research Detail | `/research/:id` | Research session detail |
| Channels | `/channels` | Manage YouTube channels by topic |
| History | `/history` | History of researched videos |
| Strategies | `/strategies` | Strategy and draft listing with detail viewer |
| Live | `/live` | Real-time research monitoring |
| Instruments | `/instruments` | Instrument reference table (CRUD) |

### Draft viewer

The draft detail view is organized into collapsible section panels:

- **Instrument** -- Shows symbol (dropdown selector from instrument reference table), secType badge, exchange, currency, multiplier, and minTick. Selecting a different instrument auto-fills all related fields.
- **Indicators** -- Table layout showing indicator name, parameters, timeframe, and alias. TODO fields are highlighted inline.
- **Conditions** -- Entry and exit rules displayed as structured lists.
- **Risk** -- Risk management parameters (stop loss, take profit, position sizing).
- **Backtest** -- Backtesting configuration and notes.
- **Notes** -- Free-form notes section.

An inline JSON editor toggle lets users view and edit the raw draft data. TODO values (`_TODO`) are highlighted in both the structured view and the JSON editor. Saves persist via `PUT /drafts/{strat_code}/data`.

## API endpoints

### Strategies (`/api/strategies`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all strategies (with filters) |
| GET | `/{name}` | Get strategy by name |
| GET | `/{name}/drafts` | Get drafts for a strategy |
| PATCH | `/{name}/status` | Update strategy status |

### Drafts (`/api/strategies/drafts`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all drafts |
| GET | `/{strat_code}` | Get draft detail |
| PUT | `/{strat_code}/data` | Update draft data (full JSON replace) |
| PATCH | `/{strat_code}/fill-todo` | Fill TODO fields with AI-generated values |

### Channels (`/api/channels`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all channels grouped by topic |
| GET | `/{topic}` | Get channels for a topic |
| POST | `/{topic}` | Add channel to a topic |
| DELETE | `/{topic}/{channel_name}` | Remove channel |

### Topics (`/api/topics`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Create topic |
| PUT | `/{slug}` | Update topic |
| DELETE | `/{slug}` | Delete topic |

### Instruments (`/api/instruments`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all instruments |
| GET | `/{symbol}` | Get instrument by symbol |
| POST | `/` | Create instrument |
| PUT | `/{symbol}` | Update instrument |
| DELETE | `/{symbol}` | Delete instrument |

### Other

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/research/sessions` | List research sessions |
| GET | `/api/research/sessions/{id}` | Get research session detail |
| GET | `/api/history` | Research history (with filters) |
| GET | `/api/history/stats` | History statistics |
| GET | `/api/export/channels` | Export channels |
| GET | `/api/export/strategies` | Export strategies |
| GET | `/api/export/drafts/{strat_code}` | Export single draft |
| GET | `/api/health` | Health check |

## Configuration

`config/settings.json` centralizes configuration:

```json
{
  "youtube": {
    "default_search_count": 20,
    "default_months_filter": 6,
    "fetch_workers": 4
  },
  "notebooklm": {
    "language": "es"
  },
  "paths": {
    "channels_db": "data/channels/channels.yaml",
    "strategies_db": "data/strategies/strategies.yaml",
    "backtests_dir": "data/backtests"
  }
}
```

## Development workflow

Code changes to this repository (features, refactors, bugfixes) use the SDD (Spec-Driven Development) framework defined in the global Claude Code configuration (`~/.claude/CLAUDE.md`).
