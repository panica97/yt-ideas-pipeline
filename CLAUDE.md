# IRT (Ideas Research Team)

Pipeline de investigación de estrategias de trading. Monitorea canales de YouTube, extrae estrategias con NotebookLM y las guarda para análisis.

## Stack

- Claude Code CLI como orquestador
- Python 3.12 para herramientas y scripts
- Docker para desarrollo local y deploy en VPS
- NotebookLM para extracción de estrategias

## Estructura

```
.claude/skills/         Skills del pipeline (cada una con SKILL.md)
  research/             Trigger del pipeline de investigación
  yt-scraper/           Fetch videos por topic desde canales registrados
  notebooklm/           API completa de NotebookLM
  notebooklm-analyst/   Extracción de estrategias desde videos
  db-manager/           Persistencia en PostgreSQL con deduplicación
.claude/agents/         Agentes con contexto propio
  research/             Agente de investigación (pipeline completo)
tools/                  Scripts Python ejecutables
  youtube/              Búsqueda y scraping (yt-dlp)
config/                 Configuración global
data/                   Datos persistentes
  channels/             Base de datos de canales YouTube (YAML)
  strategies/           Estrategias extraídas (YAML)
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
  1. yt-scraper         → videos recientes del topic
  2. notebooklm-analyst → extracción de estrategias (YAML)
  3. db-manager         → guardar con deduplicación
```

Parada temprana: `NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND` detienen el pipeline.

### Desarrollo (cambios al código del repo)

Cuando el usuario pida cambios al código, features o refactors → usar SDD del global.
Las skills SDD ya están disponibles vía `~/.claude/CLAUDE.md`.

## Cómo ejecutar

```bash
docker compose build
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```
