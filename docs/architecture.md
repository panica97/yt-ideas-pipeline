# Arquitectura

## Vision general

Trading Research Pipeline es un sistema orquestado por Claude Code CLI que monitorea canales de YouTube, extrae estrategias de trading con NotebookLM y las guarda para analisis. El trabajo se delega a sub-agentes especializados definidos como skills.

```
                    +-------------------------------------+
                    |           Claude Code CLI            |
                    |       (orquestador principal)        |
                    +------------------+------------------+
                                       |
                          /research <topic>
                                       |
            +-------------+------------+-------------+
            |              |                          |
       yt-scraper   notebooklm-analyst          db-manager
       (skill)         (skill)                   (skill)
            |              |                          |
    tools/youtube/   notebooklm CLI         data/strategies/
    fetch_topic.py   (notebooklm-py)        strategies.yaml
```

## Pipeline de investigacion

Flujo principal activado con `/research <topic>`. Los pasos se ejecutan secuencialmente; cada uno depende del anterior.

```
1. yt-scraper             Busca videos recientes por topic en canales
   |                      registrados (data/channels/channels.yaml).
   |                      Herramienta: python -m tools.youtube.fetch_topic
   |
2. notebooklm-analyst     Crea notebook en NotebookLM, anade videos como
   |                      fuentes, extrae estrategias via chat.
   |                      Herramienta: notebooklm CLI (notebooklm-py)
   |
3. db-manager             Guarda estrategias en YAML con deduplicacion
                           por nombre (case-insensitive).
                           Destino: data/strategies/strategies.yaml
```

Parada temprana: `NO_VIDEOS_FOUND` o `NO_STRATEGIES_FOUND` detienen el pipeline.

## Skills

Las skills viven en `.claude/skills/` y cada una tiene un `SKILL.md` con instrucciones para el sub-agente.

| Skill | Directorio | Funcion |
|-------|-----------|---------|
| research | `.claude/skills/research/` | Orquestador del pipeline de investigacion |
| yt-scraper | `.claude/skills/yt-scraper/` | Fetch de videos por topic desde canales registrados |
| notebooklm | `.claude/skills/notebooklm/` | API completa de NotebookLM (crear notebooks, fuentes, generar artefactos, descargar) |
| notebooklm-analyst | `.claude/skills/notebooklm-analyst/` | Extraccion de estrategias de trading desde videos |
| db-manager | `.claude/skills/db-manager/` | Persistencia de estrategias en YAML con deduplicacion |

## Stack

| Componente | Tecnologia |
|------------|------------|
| Orquestador | Claude Code CLI |
| Scripts | Python 3.12 |
| Busqueda YouTube | yt-dlp |
| Extraccion de estrategias | NotebookLM (notebooklm-py) |
| Datos | YAML (channels, strategies) |
| Contenedor | Docker (Python 3.12 slim) |
| Deploy | Docker Compose + VPS |

## Estructura de directorios

```
yt-ideas-pipeline/
├── CLAUDE.md                  Contexto del proyecto para Claude Code
├── Dockerfile                 Imagen Python 3.12-slim
├── docker-compose.yml         Servicio pipeline con volumenes (data/, config/)
├── requirements.txt           Dependencias Python
├── .env                       Secrets (no versionado)
├── .gitignore
├── .claude/
│   ├── settings.local.json    Configuracion local de Claude Code
│   └── skills/
│       ├── research/          Orquestador del pipeline
│       ├── yt-scraper/        Fetch videos por topic
│       ├── notebooklm/        API completa de NotebookLM
│       ├── notebooklm-analyst/  Extraccion de estrategias
│       └── db-manager/        Persistencia en YAML
├── tools/                     Scripts Python ejecutables
│   └── youtube/               search, fetch_topic, channels, formatting
│       ├── __init__.py
│       ├── search.py          Busqueda general en YouTube
│       ├── fetch_topic.py     Fetch videos de canales por topic
│       ├── channels.py        Gestion de la BD de canales
│       └── formatting.py      Formateo de resultados
├── config/
│   └── settings.json          Configuracion global (YouTube, NotebookLM, rutas)
├── data/
│   ├── channels/
│   │   └── channels.yaml      Base de datos de canales YouTube
│   ├── strategies/
│   │   └── strategies.yaml    Estrategias extraidas
│   └── backtests/             Resultados de backtests (CSV/JSON, gitignored)
├── docs/                      Documentacion del proyecto
│   ├── architecture.md        Este archivo
│   ├── data-schemas.md        Esquemas de datos YAML
│   ├── docker.md              Instrucciones Docker
│   └── tools.md               Documentacion de herramientas
└── planes/                    Planes y roadmap (gitignored)
```

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

## Docker

Imagen basada en `python:3.12-slim`. El servicio `pipeline` monta `data/` y `config/` como volumenes para persistencia entre ejecuciones.

```bash
docker compose build
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```

## Flujo de desarrollo

Para cambios al codigo del propio repositorio (features, refactors, bugfixes) se usa el framework SDD (Spec-Driven Development) definido en la configuracion global de Claude Code (`~/.claude/CLAUDE.md`).
