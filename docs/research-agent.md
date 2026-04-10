# Research Agent — Arquitectura

## Estructura

```
IRT/
  .claude/
    skills/
      yt-scraper/SKILL.md              skill: fetch videos por topic
      video-classifier/SKILL.md        skill: clasifica videos (strategy vs no-strategy)
      notebooklm-analyst/SKILL.md      skill: extraer estrategias con NotebookLM
      strategy-variants/SKILL.md       skill: genera variantes de estrategias
      strategy-translator/SKILL.md     skill: traduce estrategias a formato DB
      db-manager/SKILL.md              skill: guardar en PostgreSQL con dedup
    agents/
      research-manager/
        AGENT.md                       Research Manager agent (new architecture)
      research/
        AGENT.md.archived              old monolith (archived)
```

## Flujo de ejecucion

```
  ORCHESTRATOR (conversacion principal)
       |
       |  Lee .claude/agents/research-manager/AGENT.md
       |  y lo inyecta como prompt del sub-agente
       |
       +---> Agent("general-purpose", prompt = AGENT.md + topic)
                |
                +- Step 0: Preflight Check
                |     Verifica autenticacion de NotebookLM
                |     STOP: AUTH_ERROR
                |
                +- Step 1: yt-scraper
                |     IN:  topic + channels.yaml
                |     OUT: lista de URLs de videos
                |     Filtra videos ya investigados (history_repo)
                |     STOP: NO_VIDEOS_FOUND / NO_NEW_VIDEOS
                |
                +- Step 1.5: video-classifier
                |     IN:  titulos de videos
                |     OUT: videos clasificados (strategy / no-strategy)
                |     Descarta videos sin contenido de estrategias
                |
                +- Step 2: notebooklm-analyst
                |     IN:  URLs de videos clasificados como strategy
                |     OUT: estrategias extraidas (YAML)
                |     STOP: NO_STRATEGIES_FOUND
                |
                +- Step 3: strategy-variants
                |     IN:  estrategias extraidas
                |     OUT: estrategias con variantes generadas
                |
                +- Step 4: strategy-translator
                |     IN:  estrategias con variantes
                |     OUT: estrategias en formato DB
                |
                +- Step 5: db-manager
                      IN:  estrategias traducidas
                      OUT: guardado en PostgreSQL con dedup

             Devuelve resumen al orchestrator


  ======================================
   PARALELISMO: el orchestrator puede
   lanzar N agentes research a la vez,
   cada uno con contexto limpio
  ======================================

    /research "futures scalping"    /research "options selling"
              |                               |
    +---------v----------+          +---------v----------+
    |  RESEARCH AGENT 1  |          |  RESEARCH AGENT 2  |
    |  (contexto limpio) |          |  (contexto limpio) |
    |  pipeline completo |          |  pipeline completo |
    +--------------------+          +--------------------+
```

## Contexto del agente

El agente research recibe un contexto **limpio**, sin:
- Reglas de orchestrator (CLAUDE.md global)
- Workflow SDD
- Otras instrucciones que no sean de research

Solo recibe:
- Su AGENT.md (pipeline + feedback acumulado)
- Acceso a las skills de cada paso

## Early Stop Signals

| Signal | Paso | Significado |
|--------|------|-------------|
| `AUTH_ERROR` | Preflight | NotebookLM no esta autenticado |
| `NO_VIDEOS_FOUND` | yt-scraper | No hay videos para el topic |
| `NO_NEW_VIDEOS` | yt-scraper | Todos los videos ya fueron investigados |
| `NO_STRATEGIES_FOUND` | notebooklm-analyst | No se encontraron estrategias en los videos |
| `ERROR` | Cualquiera | Error generico |

## Feedback

El fichero `AGENT.md` tiene una seccion `## Feedback` donde se acumula
feedback del usuario sobre las estrategias. Ejemplos:

- "No coger estrategias de Forex, solo futuros"
- "Descartar estrategias con mas de 3 indicadores custom"
- "Priorizar estrategias intraday sobre swing"

Esto permite que el agente aprenda sin contaminar el CLAUDE.md global.
