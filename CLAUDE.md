# Jarvis — Multi-Agent Trading Research Pipeline

## What is this project?

Sistema multi-agente orquestado por Claude Code con dos áreas:

- **Research Quant** — monitorea canales de YouTube de trading, extrae estrategias usando NotebookLM y las prepara para backtesting en Strategy Quant
- **Code** — desarrollo, revisión y testing del proyecto

## Stack

- Claude Code CLI como motor de agentes
- Python para herramientas y scripts
- Docker para desarrollo local y deploy en VPS
- NotebookLM (vía skill) para extracción de estrategias

## Project structure

```
agents/          Agentes especializados (cada uno con su CLAUDE.md)
  research/      Pipeline de investigación quant
  code/          Agentes de desarrollo
tools/           Scripts Python ejecutables
  youtube/       Búsqueda y scraping de YouTube (yt-dlp)
  notebooklm/    Integración con NotebookLM
  database/      Gestión de datos YAML
config/          Configuración global
data/            Datos persistentes
  channels/      Base de datos de canales YouTube
  strategies/    Estrategias extraídas
  backtests/     Resultados de backtests
queue/           Cola de tareas entre agentes
.claude/         Skills y commands de Claude Code
```

## Conventions

- Scripts se ejecutan como módulos: `python -m tools.youtube.search "query"`
- Datos en YAML (channels, strategies). Resultados de backtest en JSON/CSV.
- Cada agente tiene su propio `CLAUDE.md` con su rol e instrucciones.
- Los slash commands (`/yt-search`, `/yt-channels`, `/notebooklm`) son la interfaz principal.

## How to run

```bash
docker compose build
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```
