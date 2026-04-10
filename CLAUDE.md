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
.claude/agents/         Agentes con contexto propio (ver Agent Routing below)
  research-manager/     Orquestador del pipeline de investigación
  video-discovery/      Fetch y clasificación de videos YouTube
  strategy-extractor/   Extracción de estrategias con NotebookLM
  strategy-processor/   Purificar, variantes, traducir a JSON IBKR
  db-persistence/       Persistencia en PostgreSQL (compartido)
  simple-backtester/    Backtest rápido, 40+ métricas
  complete-backtester/  Backtest completo con trade log
  monte-carlo-analyst/  Simulación Monte Carlo, luck vs skill
  monkey-tester/        Test de monkey (random entry benchmark)
  stress-tester/        Parameter sweep, robustez
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
- Slash commands (`/notebooklm`) para skills individuales.
- Research and backtesting tasks are routed through agents (see "Agent Routing" section).

## Flujos de trabajo

### Research (dominio del proyecto)

Research tasks are routed through the CEO (see "Agent Routing" section below). The CEO classifies user intent and dispatches to the Research Manager agent, which orchestrates the pipeline:

```
CEO routes to Research Manager → sequences:
  1. Video Discovery        → fetch + classify videos
  2. Strategy Extractor     → NotebookLM analysis → Strategy[]
  3. Strategy Processor     → purify, variants, translate → Draft[]
  4. DB Persistence         → save with deduplication
```

Entry points: topic ("research futures"), URL (YouTube link), idea ("buy RSI < 30").
Early stop: `NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND` halt the pipeline.

### Desarrollo (cambios al código del repo)

Cuando el usuario pida cambios al código, features o refactors → usar SDD del global.
Las skills SDD ya están disponibles vía `~/.claude/CLAUDE.md`.

## Agent Routing (CEO)

The Claude Code main session acts as the CEO — it classifies user intent and routes to the appropriate agent. No separate routing agent exists; the rules below are executed inline by the main session.

### Intent Classification

| User Input Pattern | Route To | Entry Point |
|---|---|---|
| "research `<topic>`" or topic-like input | research-manager | topic |
| YouTube URL | research-manager | url |
| "idea:" or describes a trade setup | research-manager | idea |
| "backtest `<draft>`" or "simple backtest" | simple-backtester | direct |
| "full backtest" or "complete backtest" | complete-backtester | direct |
| "monte carlo" or "MC analysis" | monte-carlo-analyst | direct |
| "monkey test" | monkey-tester | direct |
| "stress test" | stress-tester | direct |
| "full analysis on `<draft>`" | Chain: complete -> MC -> monkey -> stress | chained |
| "save strategies" or DB operation | db-persistence | direct |

### How to Spawn Agents

```
Agent({
  description: "Research Manager",
  prompt: "Read and follow .claude/agents/research-manager/AGENT.md. Entry point: topic. Input: topic='futures'."
})
```

For backtesting agents, pass `draft_id` (and optionally `timeframe`):

```
Agent({
  description: "Simple Backtester",
  prompt: "Read and follow .claude/agents/simple-backtester/AGENT.md. Input: draft_id='ES_RSI_001'."
})
```

### Full Analysis Chain

When "full analysis" is requested, the CEO sequences 4 backtesting agents directly (no Backtesting Manager):

1. **Complete Backtester** -- get metrics + trade log
2. **Monte Carlo Analyst** -- assess luck vs skill
3. **Monkey Tester** -- judge statistical edge
4. **Stress Tester** -- check parameter robustness
5. **CEO synthesizes** results and presents a combined verdict

Each agent runs sequentially. The CEO collects all outputs and produces a unified assessment. If synthesis logic grows complex, promote to a dedicated Backtesting Manager agent.

### Ambiguous Input Handling

If the user's intent is unclear, ask: "Did you mean research, backtesting, or something else?" Do not guess -- route only when intent is confident.

### Agent Registry

| Agent | Domain | Purpose |
|---|---|---|
| research-manager | research | Orchestrate the full research pipeline (discovery -> extraction -> processing -> persistence) |
| video-discovery | research | Fetch and classify YouTube videos by topic |
| strategy-extractor | research | Extract trading strategies from videos using NotebookLM |
| strategy-processor | research | Purify, split, generate variants, translate to IBKR JSON, auto-fill TODOs |
| db-persistence | shared | Save strategies and drafts to PostgreSQL with deduplication |
| simple-backtester | backtesting | Quick backtest, interpret 40+ metrics |
| complete-backtester | backtesting | Full backtest with trade log and equity curve analysis |
| monte-carlo-analyst | backtesting | Monte Carlo simulation, luck vs skill assessment |
| monkey-tester | backtesting | Random entry benchmark, p-value and statistical edge |
| stress-tester | backtesting | Parameter sweep, robustness score, flag fragile params |

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
