# IRT (Ideas Research Team)

Pipeline de investigación de estrategias de trading. Monitorea canales de YouTube, extrae estrategias con NotebookLM y las guarda para análisis.

## Stack

- Claude Code CLI como orquestador
- Python 3.12, FastAPI (backend API)
- React 18 + TypeScript + Tailwind CSS + Lucide React (frontend)
- PostgreSQL 16
- Docker + Docker Compose para desarrollo local y deploy en VPS
- NotebookLM (notebooklm-py) para extracción de estrategias
- yt-dlp para scraping de YouTube

## Estructura

```
api/                    FastAPI backend (puerto 8000)
  routers/              Endpoints REST
  models/               Modelos SQLAlchemy
  services/             Lógica de negocio
  alembic/              Migraciones de BD
frontend/               React dashboard (puerto 5173)
  src/                  Código fuente TypeScript
.claude/skills/         Skills del pipeline (cada una con SKILL.md)
  research/             Trigger del pipeline de investigación
  yt-scraper/           Fetch videos por topic desde canales registrados
  notebooklm/           API completa de NotebookLM
  notebooklm-analyst/   Extracción de estrategias desde videos
  video-classifier/     Filtrar videos irrelevantes
  strategy-variants/    Purificar, split long/short, variantes
  strategy-translator/  Traducción a JSON IBKR
  db-manager/           Persistencia en PostgreSQL con deduplicación
  todo-fill/            Rellenar TODOs pendientes en estrategias
.claude/agents/         Agentes con contexto propio
  research/             Agente de investigación (pipeline completo)
tools/                  Scripts Python ejecutables
  youtube/              Búsqueda y scraping (yt-dlp)
scripts/                Scripts auxiliares
config/                 Configuración global
data/                   Datos persistentes
  channels/             Base de datos de canales YouTube (YAML)
  strategies/           Estrategias extraídas (YAML)
openspec/               Artefactos SDD (cambios planificados)
docs/                   Documentación del proyecto
planes/                 Planes y roadmap (gitignored)
```

## Convenciones

- Scripts como módulos: `python -m tools.youtube.search "query"`
- Datos en YAML (channels, strategies).
- Slash commands (`/research`, `/notebooklm`) como interfaz principal.

## Flujos de trabajo

### Research (dominio del proyecto)

Cuando el usuario pida investigar estrategias de trading, usar `/research <topic>`.
Este flujo tiene su propio pipeline y NO pasa por SDD.
El skill `/research` actúa como orquestador de research, lanzando sub-agentes para cada paso:

```
/research <topic>
  0. Preflight            → notebooklm auth check
  1. yt-scraper           → videos recientes del topic
  1.5 video-classifier    → filtrar videos irrelevantes
  2. notebooklm-analyst   → extracción de estrategias (YAML)
  3. strategy-variants    → purificar, split long/short, variantes
  4. strategy-translator  → traducción a JSON IBKR
  5. db-manager           → guardar con deduplicación
```

Parada temprana: `NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND` detienen el pipeline.

### Desarrollo (cambios al código del repo)

Cuando el usuario pida cambios al código, features o refactors → usar SDD del global.
Las skills SDD ya están disponibles vía `~/.claude/CLAUDE.md`.

## Cómo ejecutar

```bash
# Levantar todos los servicios
docker compose up -d

# Dashboard: http://localhost:5173
# API:       http://localhost:8000

# Ejecutar el pipeline manualmente
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5

# Ver canales registrados
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```
