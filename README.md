# YT Ideas Pipeline

Pipeline que extrae ideas y estrategias de trading desde canales de YouTube, las analiza con NotebookLM, y las almacena como reglas parametrizables en una base de datos local.

## Flujo de trabajo

```
1. channels.yaml        Base de canales YouTube organizados por tema
        |
2. /yt-search --topic   Busca los últimos vídeos de un tema
        |
3. NotebookLM           Añade los vídeos como fuentes y extrae estrategias
        |
4. strategies.yaml      Almacena estrategias con reglas y parámetros configurables
```

## Requisitos

```bash
pip install yt-dlp pyyaml notebooklm-py
```

Autenticación de NotebookLM (una sola vez):

```bash
notebooklm login
```

## Uso rápido

Desde Claude Code:

```
# Buscar vídeos recientes de un tema
/yt-search --topic futures --days 90 --count 3

# Gestionar canales
/yt-channels list
/yt-channels add futures https://www.youtube.com/@canal --name "Canal"

# Crear cuaderno en NotebookLM y extraer estrategia
/notebooklm
```

## Bases de datos

### channels.yaml

Canales de YouTube organizados por tema. Cada tema agrupa canales relacionados.

**Estructura:**

```yaml
topics:
  <topic-id>:
    description: Descripción del tema
    channels:
      - name: Nombre del canal
        url: https://www.youtube.com/@handle
        last_fetched: null  # se actualiza automáticamente al buscar
```

**Temas actuales:**

| Topic | Descripción | Canales |
|-------|-------------|---------|
| `ai-agents` | AI agent frameworks and autonomous systems | AI Jason, Matt Williams |
| `trading` | Algorithmic and quantitative trading | QuantProgram |
| `futures` | Futures strategies | Jacob Amaral |

### strategies.yaml

Estrategias de trading extraídas de vídeos, con reglas totalmente parametrizables.

**Estructura:**

```yaml
strategies:
  - name: Nombre de la estrategia
    description: Descripción general
    source_channel: Canal de origen
    source_videos:
      - "Título del vídeo 1"
      - "Título del vídeo 2"
    parameters:
      - name: nombre_param
        description: Qué controla
        type: int|float|string|bool
        default: valor por defecto
        range: rango permitido
    entry_rules:
      - "Regla de entrada 1 (referencia parámetros por nombre)"
    exit_rules:
      - "Regla de salida 1"
    risk_management:
      - "Regla de gestión de riesgo 1"
    notes:
      - "Observaciones relevantes"
```

**Estrategias actuales:**

| Estrategia | Instrumento | Canal | Parámetros |
|------------|-------------|-------|------------|
| RTY Hybrid BB Monthly Governor | RTY (Russell 2000 futures) | Jacob Amaral | 9 params: ticker, timeframe, BB period/std, targets long/short, stop mensual, contratos, ciclo optimización |

## Estructura del proyecto

```
yt-ideas-pipeline/
  channels.yaml             # Base de datos de canales
  strategies.yaml           # Base de datos de estrategias
  yt-search-skill-setup.md  # Docs de setup de las skills
  README.md                 # Este archivo
```

## Skills de Claude Code

Este proyecto usa dos skills personalizadas documentadas en `yt-search-skill-setup.md`:

- `/yt-search` — Busca vídeos por keyword o por tema (topic mode)
- `/yt-channels` — CRUD para la base de datos de canales
- `/notebooklm` — Automatización de NotebookLM (crear cuadernos, añadir fuentes, extraer contenido)
