# IRT (Ideas Research Team)

Pipeline de investigación de estrategias de trading. Monitorea canales de YouTube, extrae estrategias con NotebookLM, las traduce a formato IBKR y las persiste en PostgreSQL con un dashboard en tiempo real.

## Stack

- **Orquestador:** Claude Code CLI
- **Backend:** Python 3.12, FastAPI
- **Frontend:** React 18 + TypeScript + Tailwind CSS + Lucide React
- **Base de datos:** PostgreSQL 16
- **Scraping:** yt-dlp
- **Análisis:** NotebookLM (notebooklm-py)
- **Deploy:** Docker + Docker Compose

## Pipeline de investigación

```
preflight → yt-scraper → video-classifier → notebooklm-analyst → strategy-variants → strategy-translator → db-manager
```

0. **Preflight** — verifica autenticación con NotebookLM
1. **yt-scraper** — busca vídeos recientes en canales de trading registrados
2. **video-classifier** — filtra vídeos irrelevantes para el topic
3. **notebooklm-analyst** — analiza los vídeos y extrae estrategias estructuradas (YAML)
4. **strategy-variants** — purifica, split long/short, genera variantes
5. **strategy-translator** — traduce las estrategias a formato JSON IBKR
6. **db-manager** — guarda en PostgreSQL con deduplicación

Se lanza con `/research <topic>` desde Claude Code.

## Estructura del proyecto

```
api/                    FastAPI backend (puerto 8000)
  routers/              Endpoints REST
  models/               Modelos SQLAlchemy
  services/             Lógica de negocio
  alembic/              Migraciones de BD
frontend/               React dashboard (puerto 5173)
  src/                  Código fuente TypeScript
tools/                  Scripts Python del pipeline
  youtube/              Búsqueda y scraping (yt-dlp)
  db/                   Modelos ORM, repositorios, sesión (SQLAlchemy)
scripts/                Scripts auxiliares
config/                 Configuración global
data/                   Datos persistentes (channels, strategies)
openspec/               Artefactos SDD (cambios planificados)
docs/                   Documentación
.claude/skills/         Skills de Claude Code (9 skills: research, yt-scraper,
                        notebooklm, notebooklm-analyst, video-classifier,
                        strategy-variants, strategy-translator, db-manager, todo-fill)
```

## Requisitos

- Docker y Docker Compose
- Fichero `.env` con las variables necesarias (ver `.env.example`)

## Cómo ejecutar

```bash
# Levantar todos los servicios
docker compose up -d

# El dashboard estará en http://localhost:5173
# La API estará en http://localhost:8000

# Ejecutar el pipeline manualmente
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5

# Ver canales registrados
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```

## Servicios

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| `frontend` | 5173 | Dashboard React |
| `api` | 8000 | API FastAPI |
| `postgres` | 5432 | Base de datos |
| `pipeline` | — | Scripts del pipeline (bajo demanda) |
