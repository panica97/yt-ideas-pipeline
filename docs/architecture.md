# Arquitectura

## Vision general

IRT (Ideas Research Team) es un pipeline de investigacion de estrategias de trading. Monitorea canales de YouTube, extrae estrategias con NotebookLM, las clasifica y traduce, y las guarda en PostgreSQL para analisis. El frontend React permite gestionar y visualizar todo el flujo.

## Stack

| Componente | Tecnologia |
|------------|------------|
| Orquestador | Claude Code CLI |
| Backend API | Python 3.12 + FastAPI |
| Frontend | React 18 + TypeScript + Tailwind CSS |
| Base de datos | PostgreSQL 16 |
| Scripts | Python 3.12 (yt-dlp, SQLAlchemy) |
| Extraccion de estrategias | NotebookLM (notebooklm-py) |
| Contenedor | Docker Compose (api, frontend, postgres) |

## Data flow

```
YouTube
  |
  v
yt-scraper (fetch videos por topic)
  |
  v
video-classifier (filtra videos sin estrategias)
  |
  v
NotebookLM analyst (extrae estrategias)
  |
  v
strategy-variants (genera variantes)
  |
  v
strategy-translator (traduce a formato DB)
  |
  v
db-manager (guarda con deduplicacion)
  |
  v
PostgreSQL
  |
  v
FastAPI API (endpoints REST)
  |
  v
React dashboard (visualizacion y gestion)
```

## Estructura de directorios

```
IRT/
├── CLAUDE.md                     Contexto del proyecto para Claude Code
├── Dockerfile                    Imagen Python 3.12-slim
├── docker-compose.yml            Servicios: api, frontend, postgres
├── requirements.txt              Dependencias Python
├── .env                          Secrets (no versionado)
├── api/                          FastAPI backend
│   ├── routers/                  Endpoints REST
│   │   ├── strategies.py         CRUD estrategias + drafts
│   │   ├── channels.py           CRUD canales
│   │   ├── history.py            Historial de investigacion
│   │   ├── instruments.py        Tabla de referencia de instrumentos
│   │   ├── stats.py              Estadisticas del dashboard
│   │   ├── research.py           Sesiones de investigacion en curso
│   │   ├── topics.py             CRUD topics
│   │   ├── export.py             Exportacion de datos
│   │   └── health.py             Health check
│   ├── services/                 Logica de negocio
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
│       │   ├── layout/           Sidebar, header, theme toggle
│       │   ├── common/           Componentes reutilizables
│       │   ├── strategies/       Tabla, viewer, filtros de estrategias
│       │   ├── channels/         Gestion de canales
│       │   ├── history/          Historial de research
│       │   └── live/             Research en tiempo real
│       ├── pages/                9 paginas
│       │   ├── LoginPage.tsx
│       │   ├── DashboardPage.tsx
│       │   ├── ResearchPage.tsx
│       │   ├── ResearchDetailPage.tsx
│       │   ├── ChannelsPage.tsx
│       │   ├── HistoryPage.tsx
│       │   ├── StrategiesPage.tsx
│       │   ├── LivePage.tsx
│       │   └── InstrumentsPage.tsx
│       ├── services/             API client (Axios)
│       │   ├── api.ts            Configuracion base Axios
│       │   ├── strategies.ts
│       │   ├── channels.ts
│       │   ├── history.ts
│       │   ├── instruments.ts
│       │   ├── research.ts
│       │   └── stats.ts
│       └── hooks/                Custom hooks
│           ├── useTheme.ts
│           ├── useResearchStatus.ts
│           └── useWebSocket.ts
├── tools/                        Scripts Python ejecutables
│   ├── youtube/                  yt-dlp scraping
│   │   ├── search.py            Busqueda general en YouTube
│   │   ├── fetch_topic.py       Fetch videos de canales por topic
│   │   ├── channels.py          Gestion de la BD de canales
│   │   └── formatting.py        Formateo de resultados
│   ├── db/                       Base de datos (SQLAlchemy)
│   │   ├── models.py            Modelos ORM (Strategy, Draft, Channel, Instrument, etc.)
│   │   ├── session.py           Session factory y context manager
│   │   ├── base.py              Base declarativa + TimestampMixin
│   │   ├── strategy_repo.py     Repositorio de estrategias
│   │   ├── draft_repo.py        Repositorio de drafts (con deteccion de TODOs)
│   │   ├── channel_repo.py      Repositorio de canales
│   │   ├── instrument_repo.py   Repositorio de instrumentos
│   │   ├── history_repo.py      Repositorio de historial
│   │   └── research_repo.py     Repositorio de sesiones de research
│   ├── database/                 Migraciones y seeds
│   └── notebooklm/              Utilidades NotebookLM
├── .claude/
│   ├── skills/                   Pipeline skills (9 skills)
│   │   ├── research/            Orquestador del pipeline
│   │   ├── yt-scraper/          Fetch videos por topic
│   │   ├── video-classifier/    Clasifica videos (strategy vs no-strategy)
│   │   ├── notebooklm/          API completa de NotebookLM
│   │   ├── notebooklm-analyst/  Extraccion de estrategias
│   │   ├── strategy-variants/   Genera variantes de estrategias
│   │   ├── strategy-translator/ Traduce estrategias a formato DB
│   │   ├── db-manager/          Persistencia en PostgreSQL
│   │   └── todo-fill/           Rellena campos TODO en drafts
│   └── agents/
│       └── research/            Agente de investigacion (pipeline completo)
├── config/                       Configuracion global
│   └── settings.json
├── data/                         Datos persistentes
│   ├── channels/                Base de datos de canales YouTube (YAML)
│   ├── strategies/              Estrategias extraidas (YAML, legacy)
│   └── research/                Historial de research (YAML, legacy)
├── docs/                         Documentacion del proyecto
├── openspec/                     Artefactos SDD
└── planes/                       Planes y roadmap (gitignored)
```

## Skills

| Skill | Directorio | Funcion |
|-------|-----------|---------|
| research | `.claude/skills/research/` | Orquestador del pipeline de investigacion |
| yt-scraper | `.claude/skills/yt-scraper/` | Fetch de videos por topic desde canales registrados |
| video-classifier | `.claude/skills/video-classifier/` | Clasifica videos para filtrar los que no contienen estrategias |
| notebooklm | `.claude/skills/notebooklm/` | API completa de NotebookLM |
| notebooklm-analyst | `.claude/skills/notebooklm-analyst/` | Extraccion de estrategias de trading desde videos |
| strategy-variants | `.claude/skills/strategy-variants/` | Genera variantes de cada estrategia extraida |
| strategy-translator | `.claude/skills/strategy-translator/` | Traduce estrategias al formato de la BD |
| db-manager | `.claude/skills/db-manager/` | Persistencia en PostgreSQL con deduplicacion |
| todo-fill | `.claude/skills/todo-fill/` | Rellena campos TODO pendientes en drafts |

## Frontend

9 paginas con tema claro/oscuro y sidebar colapsable:

| Pagina | Ruta | Descripcion |
|--------|------|-------------|
| Login | `/login` | Autenticacion |
| Dashboard | `/` | Resumen general con estadisticas |
| Research | `/research` | Lanzar y ver sesiones de investigacion |
| Research Detail | `/research/:id` | Detalle de una sesion de research |
| Channels | `/channels` | Gestion de canales YouTube por topic |
| History | `/history` | Historial de videos investigados |
| Strategies | `/strategies` | Listado y viewer de estrategias/drafts |
| Live | `/live` | Research en tiempo real |
| Instruments | `/instruments` | Tabla de referencia de instrumentos |

## Configuracion

El archivo `config/settings.json` centraliza la configuracion:

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

## Flujo de desarrollo

Para cambios al codigo del propio repositorio (features, refactors, bugfixes) se usa el framework SDD (Spec-Driven Development) definido en la configuracion global de Claude Code (`~/.claude/CLAUDE.md`).
