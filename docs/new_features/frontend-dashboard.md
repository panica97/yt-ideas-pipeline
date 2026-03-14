# PRD: Frontend Dashboard para Trading Research Pipeline

## 1. Titulo y resumen

**Frontend Dashboard** -- interfaz web para visualizar y gestionar los datos del pipeline de investigacion de trading (canales, estrategias, historial) y monitorizar en tiempo real el estado de las investigaciones lanzadas desde el CLI.

El dashboard NO lanza investigaciones. El flujo de research sigue siendo exclusivo de Claude Code CLI. El frontend es una ventana de lectura y gestion de datos sobre PostgreSQL, la unica fuente de verdad compartida entre el CLI y el dashboard.

---

## 2. Contexto y problema

Actualmente toda la interaccion con los datos del pipeline se hace via CLI o editando ficheros YAML/JSON a mano. Esto presenta varios problemas:

- **Visibilidad limitada**: no hay forma rapida de ver todas las estrategias, canales o el historial de investigacion sin abrir ficheros individuales.
- **Gestion de canales**: anadir o eliminar canales requiere editar `channels.yaml` manualmente, con riesgo de romper el formato.
- **Borradores JSON**: los drafts en `data/strategies/drafts/*.json` contienen campos `_TODO` que necesitan atencion del usuario, pero no hay forma facil de identificarlos.
- **Estado del research**: cuando el agente de investigacion esta corriendo, no hay feedback visual del progreso.
- **Concurrencia**: multiples agentes paralelos (estrategias de futuros, opciones, sync con Obsidian) pueden escribir datos simultaneamente, lo que causa conflictos en ficheros planos.

El dashboard resuelve estos problemas ofreciendo una interfaz web respaldada por PostgreSQL como unica fuente de verdad. Tanto el CLI como el backend leen y escriben a la misma base de datos, eliminando ficheros intermediarios y problemas de concurrencia.

---

## 3. Arquitectura

```
VPS (produccion) / Local (desarrollo)
  Claude Code CLI --> ejecuta research --> escribe a PostgreSQL
                                                |
  FastAPI backend --> lee/escribe PostgreSQL ----+
       |
       |-- REST API para gestion de datos
       |-- WebSocket para estado del research en tiempo real

  PostgreSQL 16 (postgres:16-alpine)
       |-- Unica fuente de verdad
       |-- Tablas: channels, strategies, drafts, history, research_sessions

Navegador del usuario
  React app --HTTP/WS--> FastAPI backend
```

### Principios clave

- **PostgreSQL como fuente de verdad**: no hay ficheros YAML/JSON intermedios. PostgreSQL 16 es la unica fuente de verdad para todos los datos (canales, estrategias, historial, estado del research).
- **Sin ficheros intermediarios**: el CLI escribe directamente a PostgreSQL, el backend lee directamente de PostgreSQL. No hay ficheros YAML que sincronizar.
- **Concurrencia segura**: PostgreSQL soporta escrituras concurrentes desde multiples agentes paralelos (futuros, opciones, sync con Obsidian) gracias a MVCC. No hay riesgo de corrupcion de ficheros ni race conditions.
- **Exportacion bajo demanda**: los formatos YAML/JSON se mantienen como opcion de exportacion desde el dashboard (boton de descarga), no como formato de almacenamiento.

### Justificacion de PostgreSQL sobre SQLite

- **Escrituras concurrentes**: multiples agentes de research pueden correr en paralelo (uno para futuros, otro para opciones, sync con Obsidian). SQLite usa write-ahead logging con un unico escritor concurrente; PostgreSQL soporta multiples escritores simultaneos via MVCC.
- **JSONB**: los borradores de estrategia (drafts) tienen estructura variable con campos como `_TODO` y metadatos flexibles. JSONB permite almacenar y consultar esta estructura sin esquema rigido.
- **Full-text search**: busqueda de estrategias por nombre y descripcion nativa con `tsvector/tsquery`, sin dependencias adicionales.
- **Ecosistema Docker**: PostgreSQL corre como servicio independiente en Docker Compose, sin acoplamiento al filesystem del host.

---

## 4. Stack tecnologico

| Capa | Tecnologia | Justificacion |
|------|------------|---------------|
| Frontend | React 18 + TypeScript | Ecosistema amplio, tipado estatico, componentes reutilizables |
| Estilos | Tailwind CSS | Utilidades, rapido de prototipar, coherente |
| Estado frontend | React Query (TanStack Query) | Cache, invalidacion automatica, polling sencillo |
| Build frontend | Vite | Rapido, soporte nativo de TypeScript |
| Backend | FastAPI (Python 3.12) | Asincrono, validacion con Pydantic, WebSocket nativo, mismo lenguaje que el pipeline |
| Base de datos | PostgreSQL 16 | Concurrencia MVCC, JSONB, full-text search. Imagen `postgres:16-alpine` |
| ORM | SQLAlchemy 2.0 | ORM async con soporte nativo de tipos Python, modelos declarativos |
| Migraciones | Alembic | Migraciones versionadas, autogenerate desde modelos SQLAlchemy |
| Driver async | asyncpg | Driver PostgreSQL asincrono de alto rendimiento para SQLAlchemy async |
| Validacion | Pydantic v2 | Modelos tipados para request/response |
| WebSocket | fastapi.websockets | Integrado en FastAPI |
| Despliegue | Docker Compose | Mismo compose que el pipeline existente |
| Proxy reverso | Caddy o Nginx | HTTPS automatico en VPS |

---

## 5. Funcionalidades

### 5.1 Gestion de canales (CRUD)

**Descripcion**: permite ver, anadir y eliminar canales de YouTube agrupados por topic. Opera sobre la tabla `channels` en PostgreSQL.

**Modelo de datos (PostgreSQL)**:
```sql
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) UNIQUE NOT NULL,       -- e.g. "futures"
    description TEXT
);

CREATE TABLE channels (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    url VARCHAR(255) NOT NULL,
    last_fetched TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(topic_id, url)
);
```

**Criterios de aceptacion**:

- [ ] Listar todos los topics con sus canales en vista de tarjetas agrupadas.
- [ ] Cada tarjeta de canal muestra: nombre, URL (enlace), fecha del ultimo fetch (o "Nunca" si es null).
- [ ] Boton "Anadir topic" en la cabecera de la pagina de canales: formulario con campos `slug` (identificador unico, lowercase, sin espacios) y `description`.
- [ ] Boton "Editar topic" para modificar la descripcion.
- [ ] Boton "Eliminar topic" con confirmacion. No permitir eliminar si el topic tiene canales asociados (debe vaciarse primero).
- [ ] Boton "Anadir canal" dentro de cada topic: formulario con campos `name` y `url`. Validar que la URL tiene formato de canal de YouTube (`https://www.youtube.com/@...` o `https://www.youtube.com/c/...` o `https://www.youtube.com/channel/...`).
- [ ] Boton "Eliminar canal" con confirmacion. No permitir eliminar si solo queda un canal en el topic (el topic quedaria sin canales).
- [ ] Al anadir un canal, el campo `last_fetched` se inicializa como `null`.
- [ ] Los cambios se persisten inmediatamente en PostgreSQL via la API.
- [ ] Mensajes de error claros si la API falla (conexion a BD perdida, constraint violation, etc.).
- [ ] No se puede anadir un canal con la misma URL que otro ya existente en el mismo topic (constraint UNIQUE en BD).

### 5.2 Historial de investigacion

**Descripcion**: visualiza los videos investigados desde la tabla `research_history` en PostgreSQL. Solo lectura.

**Modelo de datos (PostgreSQL)**:
```sql
CREATE TABLE research_history (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(20) NOT NULL,
    url VARCHAR(255) NOT NULL,
    channel_id INTEGER REFERENCES channels(id),
    topic_id INTEGER REFERENCES topics(id),
    researched_at TIMESTAMPTZ DEFAULT NOW(),
    strategies_found INTEGER DEFAULT 0,
    UNIQUE(video_id, topic_id)
);
```

**Criterios de aceptacion**:

- [ ] Tabla con columnas: video ID (enlace a YouTube), canal, topic, fecha, estrategias encontradas.
- [ ] Filtros: por topic (dropdown), por canal (dropdown, dependiente del topic seleccionado), por rango de fechas.
- [ ] Ordenacion por fecha (descendente por defecto), por canal o por numero de estrategias.
- [ ] Contador total de videos investigados visible en la cabecera.
- [ ] Si la lista esta vacia, mostrar mensaje "No se han investigado videos todavia".
- [ ] Paginacion o scroll infinito si hay mas de 50 entradas.

### 5.3 Visor de estrategias

**Descripcion**: visualiza las estrategias en dos formatos: las estrategias estructuradas (tabla `strategies`) y los borradores traducidos (tabla `drafts` con columna JSONB).

#### 5.3.1 Estrategias

**Modelo de datos (PostgreSQL)**:
```sql
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    source_channel_id INTEGER REFERENCES channels(id),
    source_videos TEXT[],               -- array de titulos/URLs
    parameters JSONB DEFAULT '[]',      -- flexible: nombre, tipo, default, rango
    entry_rules JSONB DEFAULT '[]',
    exit_rules JSONB DEFAULT '[]',
    risk_management JSONB DEFAULT '[]',
    notes JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Full-text search index
CREATE INDEX idx_strategies_fts ON strategies
    USING GIN (to_tsvector('english', name || ' ' || COALESCE(description, '')));
```

**Criterios de aceptacion**:

- [ ] Lista de estrategias con nombre, canal fuente y descripcion resumida.
- [ ] Al hacer clic en una estrategia, expandir o navegar a una vista de detalle con:
  - Descripcion completa
  - Parametros en tabla (nombre, tipo, default, rango)
  - Reglas de entrada como lista
  - Reglas de salida como lista
  - Gestion de riesgo como lista
  - Notas
  - Videos fuente (como enlaces a YouTube)
- [ ] Filtro por canal fuente.
- [ ] Busqueda por texto libre (busca en nombre y descripcion).

#### 5.3.2 Borradores (Drafts)

**Modelo de datos (PostgreSQL)**:
```sql
CREATE TABLE drafts (
    id SERIAL PRIMARY KEY,
    strat_code INTEGER UNIQUE NOT NULL,
    strat_name VARCHAR(255) NOT NULL,
    strategy_id INTEGER REFERENCES strategies(id),
    data JSONB NOT NULL,                -- el draft completo como JSONB
    todo_count INTEGER DEFAULT 0,       -- cache del conteo de _TODO
    todo_fields TEXT[] DEFAULT '{}',    -- cache de paths con _TODO
    active BOOLEAN DEFAULT FALSE,
    tested BOOLEAN DEFAULT FALSE,
    prod BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

- La columna `data` almacena el draft completo como JSONB, permitiendo consultas flexibles.
- Campos `_TODO` dentro de `data` indican valores que el usuario debe completar manualmente.
- Las columnas `todo_count` y `todo_fields` son caches que se actualizan al insertar/modificar el draft.

**Criterios de aceptacion**:

- [ ] Lista de borradores con: strat_code, strat_name, symbol, estado (active/tested/prod como badges).
- [ ] Vista de detalle renderizada de forma legible (NO mostrar JSON crudo):
  - Seccion "Instrumento": symbol, secType, exchange, currency, multiplier.
  - Seccion "Indicadores": tabla con indicador, parametros, timeframe.
  - Seccion "Condiciones Long": lista de condiciones con su tipo y codigo.
  - Seccion "Condiciones Short": igual.
  - Seccion "Stop Loss / Take Profit": configuracion renderizada.
  - Seccion "Parametros de control": tabla.
  - Seccion "Notas": contenido de `_notes`.
- [ ] **Campos `_TODO` resaltados** en rojo/naranja con un icono de atencion. Deben ser visualmente obvios.
- [ ] Contador de campos `_TODO` visible en la lista (por ejemplo "3 campos pendientes").
- [ ] Filtro para ver solo borradores con campos `_TODO` pendientes.

### 5.4 Estado del research en tiempo real

**Descripcion**: el agente de investigacion (CLI) escribe su estado en la tabla `research_sessions` en PostgreSQL. Cada ejecucion del pipeline crea una nueva fila, permitiendo multiples sesiones en paralelo. El backend lo sirve via WebSocket al frontend.

**Modelo de datos (PostgreSQL)**:
```sql
CREATE TABLE research_sessions (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) DEFAULT 'running',  -- running | completed | error
    topic_id INTEGER REFERENCES topics(id),
    step INTEGER DEFAULT 0,
    step_name VARCHAR(50),
    total_steps INTEGER DEFAULT 6,
    channel VARCHAR(100),
    videos_processing TEXT[] DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_detail TEXT,
    result_summary JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vista rapida de sesiones activas
CREATE INDEX idx_research_sessions_active ON research_sessions (status) WHERE status = 'running';
```

**Mecanismo de actualizacion en tiempo real (LISTEN/NOTIFY)**:

El sistema usa PostgreSQL LISTEN/NOTIFY en lugar de polling para actualizaciones en tiempo real:

1. El agente de investigacion (CLI) ejecuta `NOTIFY research_update, '<session_id>'` despues de cada UPDATE a `research_sessions`.
2. FastAPI mantiene una conexion persistente con `LISTEN research_update`.
3. Cuando llega una notificacion, FastAPI consulta la sesion actualizada y la envia via WebSocket a los clientes conectados.
4. Fallback: si se pierde una notificacion (por ejemplo, caida de conexion), el cliente puede solicitar el estado actual al reconectarse al WebSocket.

**Criterios de aceptacion**:

- [ ] Panel de estado mostrando todas las sesiones activas en paralelo (por ejemplo, futures en paso 4, options en paso 2).
- [ ] Cada sesion activa muestra su propio indicador visual:
  - `running`: indicador verde pulsante con nombre del paso actual.
  - `completed`: indicador verde estatico con resumen.
  - `error`: indicador rojo con detalle del error.
- [ ] Cuando no hay filas con `status='running'`, mostrar estado idle: indicador gris con "No hay investigacion en curso".
- [ ] Barra de progreso individual por sesion basada en `step` / `total_steps`.
- [ ] Detalle visible por sesion: topic, paso actual (nombre legible), canal siendo procesado, videos en proceso (como enlaces).
- [ ] Timestamp de inicio formateado ("hace 5 minutos" o similar) por sesion.
- [ ] Actualizacion via WebSocket usando PostgreSQL LISTEN/NOTIFY: el agente ejecuta `NOTIFY research_update, '<session_id>'` tras cada UPDATE; FastAPI escucha con `LISTEN research_update` y envia el estado actualizado via WebSocket.
- [ ] Al reconectar el WebSocket, el cliente recibe el estado actual de todas las sesiones activas.
- [ ] Cuando una sesion transiciona a `completed`, mostrar un resumen breve y enlace a la pagina de estrategias.

**Nombres legibles de los pasos**:

| step | step_name | Nombre en UI |
|------|-----------|-------------|
| 0 | preflight | Comprobacion de autenticacion |
| 1 | yt-scraper | Buscando videos |
| 2 | notebooklm-analyst | Extrayendo estrategias |
| 3 | translator | Traduciendo a JSON |
| 4 | cleanup | Limpieza |
| 5 | db-manager | Guardando en base de datos |
| 6 | summary | Resumen final |

### 5.5 Dashboard (pagina principal)

**Descripcion**: vista resumen con estadisticas globales y accesos directos.

**Criterios de aceptacion**:

- [ ] Tarjetas de resumen (stats cards):
  - Total de topics
  - Total de canales
  - Total de videos investigados
  - Total de estrategias (YAML)
  - Total de borradores JSON
  - Borradores con `_TODO` pendientes
- [ ] Seccion "Ultima investigacion": muestra el ultimo research completado (de la tabla `research_history`, el mas reciente por fecha).
- [ ] Seccion "Estado actual": mini-widget del estado del research (version compacta de la pagina Live).
- [ ] Enlaces rapidos a cada seccion.

### 5.6 Seguridad

**Descripcion**: autenticacion por API key para un solo usuario.

**Criterios de aceptacion**:

- [ ] API key configurada via variable de entorno `DASHBOARD_API_KEY` en `.env`.
- [ ] Toda peticion HTTP al backend debe incluir el header `X-API-Key`.
- [ ] Si la API key es invalida o falta, devolver `401 Unauthorized`.
- [ ] El frontend almacena la API key en localStorage despues de que el usuario la introduzca en un formulario de login.
- [ ] Pantalla de login: un unico campo "API Key" + boton "Entrar". No hay usuario/password.
- [ ] CORS configurado via variable de entorno `CORS_ORIGINS` (lista separada por comas).
- [ ] En produccion, el backend corre detras de un proxy reverso (Caddy/Nginx) que gestiona HTTPS.
- [ ] Endpoint `GET /api/health` publico (sin autenticacion) para health checks.

---

## 6. Paginas y vistas

### 6.1 Layout general

- **Sidebar izquierdo** fijo con navegacion:
  - Dashboard (icono home)
  - Canales
  - Historial
  - Estrategias
  - Live
- **Header superior** con titulo del proyecto y un indicador de estado del research (punto verde/rojo/gris).
- **Area de contenido** principal a la derecha del sidebar.
- Tema oscuro por defecto (los traders usan pantallas muchas horas).

### 6.2 Pagina Dashboard

```
+--------------------------------------------------+
| [Stats Cards - 6 tarjetas en grid 3x2]           |
|  Topics: 3  | Canales: 5  | Videos: 12           |
|  Estrategias: 8 | Drafts: 3 | TODOs: 2           |
+--------------------------------------------------+
| Estado actual          | Ultima investigacion    |
| [Mini widget Live]     | Topic: futures           |
|                        | Fecha: 2026-03-14        |
|                        | Videos: 3                |
|                        | Estrategias: 1           |
+--------------------------------------------------+
```

### 6.3 Pagina Canales

```
+--------------------------------------------------+
| Canales                          [+ Anadir topic] |
+--------------------------------------------------+
| > futures (2 canales)          [Editar] [Borrar]  |
|   Futures strategies                              |
|   +--------------------------------------------+ |
|   | Jacob Amaral     | @jacobamaral | 14/03/26 | |
|   |                                    [Borrar] | |
|   | NQ Scalper       | @nqscalper   | Nunca    | |
|   |                                    [Borrar] | |
|   +--------------------------------------------+ |
|   [+ Anadir canal]                               |
|                                                   |
| > trading (1 canal)           [Editar] [Borrar]  |
|   ...                                             |
+--------------------------------------------------+
```

- El boton [+ Anadir topic] abre un formulario con campos `slug` y `description`.
- El boton [Editar] del topic permite modificar la descripcion.
- El boton [Borrar] del topic solo esta habilitado si el topic no tiene canales asociados.

### 6.4 Pagina Historial

```
+--------------------------------------------------+
| Historial de investigacion       Total: 12 videos |
+--------------------------------------------------+
| Filtros: [Topic v] [Canal v] [Desde] [Hasta]      |
+--------------------------------------------------+
| Video ID    | Canal         | Topic   | Fecha     |
| G0c7GAg-FCY | Jacob Amaral | futures | 14/03/26  |
| a1b2c3d4    | QuantProgram | trading | 12/03/26  |
| ...                                               |
+--------------------------------------------------+
```

### 6.5 Pagina Estrategias

Dos pestanas: **YAML** y **Drafts JSON**.

**Pestana YAML**:
```
+--------------------------------------------------+
| Estrategias YAML                                  |
| [Buscar...____________]  [Canal: Todos v]         |
+--------------------------------------------------+
| > RTY Hybrid BB Monthly Governor Strategy         |
|   Jacob Amaral | 3 videos fuente                  |
|   Multi-mode futures trading strategy...          |
|   [Click para expandir detalle]                   |
+--------------------------------------------------+
```

**Pestana Drafts JSON**:
```
+--------------------------------------------------+
| Borradores JSON                [Solo con TODOs v] |
+--------------------------------------------------+
| 9001 | RTY_BB_MonthlyGov_1 | RTY | 5 TODOs      |
|       active: No | tested: No | prod: No         |
|   [Ver detalle]                                   |
+--------------------------------------------------+
```

**Vista detalle de draft**:
```
+--------------------------------------------------+
| 9001 - RTY_BB_MonthlyGov_1          [5 TODOs]    |
+--------------------------------------------------+
| Instrumento                                       |
|   Symbol: RTY | Tipo: FUT | Exchange: CME         |
|   Multiplier: 50 | Min Tick: 0.1                  |
+--------------------------------------------------+
| Indicadores (1 day)                               |
|   PRICE  | high, period=1        | HIGH_1D        |
|   BBANDS | close, period=20, 2.0 | BB_20_2_1D     |
|   ATR    | period=20             | ATR_20_1D_SL   |
+--------------------------------------------------+
| Condiciones Long                                  |
|   cross_ind_relation: HIGH_1D crosses_below ...   |
+--------------------------------------------------+
| Stop Loss                                         |
|   Tipo: indicator                                 |
|   multiple: [!] _TODO    <-- resaltado en rojo    |
|   col: ATR_20_1D_SL                               |
+--------------------------------------------------+
| Notas                                             |
|   monthly_governor: La logica del Monthly...      |
+--------------------------------------------------+
```

### 6.6 Pagina Live

Muestra todas las sesiones de research activas en paralelo. Cada sesion tiene su propio panel de progreso.

```
+--------------------------------------------------+
| Estado del Research en Tiempo Real                |
+--------------------------------------------------+
| Sesion #42 - futures                              |
|   [============================------] 4/6        |
|   Estado: EN CURSO (punto verde pulsante)         |
|   Paso: 4 - Limpieza                              |
|   Canal: Jacob Amaral                             |
|   Videos: G0c7GAg-FCY (enlace)                    |
|   Inicio: hace 12 minutos                         |
+--------------------------------------------------+
| Sesion #43 - options                              |
|   [============--------------------------] 2/6    |
|   Estado: EN CURSO (punto verde pulsante)         |
|   Paso: 2 - Extrayendo estrategias                |
|   Canal: OptionsPlay                              |
|   Videos: xK9f2a3b (enlace)                       |
|   Inicio: hace 3 minutos                          |
+--------------------------------------------------+
```

Cuando no hay sesiones activas (ninguna fila con `status='running'`):
```
+--------------------------------------------------+
|                                                   |
|   (punto gris)                                    |
|   No hay investigacion en curso                   |
|   Lanza una con /research <topic> en el CLI       |
|                                                   |
+--------------------------------------------------+
```

---

## 7. Estructura de ficheros

```
frontend/
  src/
    components/
      layout/
        Sidebar.tsx
        Header.tsx
        Layout.tsx
      common/
        StatsCard.tsx
        StatusBadge.tsx
        ConfirmDialog.tsx
        TodoBadge.tsx
        LoadingSpinner.tsx
      channels/
        ChannelCard.tsx
        ChannelForm.tsx
        TopicGroup.tsx
        TopicForm.tsx
      strategies/
        StrategyCard.tsx
        StrategyDetail.tsx
        DraftCard.tsx
        DraftDetail.tsx
        TodoHighlight.tsx
        IndicatorTable.tsx
        ConditionList.tsx
      history/
        HistoryTable.tsx
        HistoryFilters.tsx
      live/
        ResearchStatus.tsx
        ProgressBar.tsx
        StepIndicator.tsx
    pages/
      DashboardPage.tsx
      ChannelsPage.tsx
      HistoryPage.tsx
      StrategiesPage.tsx
      LivePage.tsx
      LoginPage.tsx
    services/
      api.ts              # Cliente HTTP con interceptor de API key
      topics.ts            # Llamadas a /api/topics
      channels.ts          # Llamadas a /api/channels
      strategies.ts        # Llamadas a /api/strategies
      history.ts           # Llamadas a /api/history
      research.ts          # WebSocket para estado live
    hooks/
      useWebSocket.ts      # Hook generico de WebSocket con reconexion
      useResearchStatus.ts # Hook especifico para estado del research
    types/
      channel.ts
      strategy.ts
      draft.ts
      history.ts
      research.ts
    App.tsx
    main.tsx
    router.tsx
  public/
  index.html
  package.json
  tsconfig.json
  tailwind.config.js
  vite.config.ts
  Dockerfile

api/
  main.py                  # App FastAPI, CORS, middleware de auth
  config.py                # Settings (DB URL, API key, CORS)
  dependencies.py          # Dependency injection (auth, DB session)
  database.py              # SQLAlchemy engine, async session factory
  routers/
    topics.py              # CRUD topics
    channels.py            # CRUD canales
    strategies.py          # Lectura estrategias + drafts
    history.py             # Lectura historial
    research.py            # WebSocket estado live
    health.py              # Health check
    export.py              # Exportacion YAML/JSON bajo demanda
  services/
    topic_service.py       # Logica de negocio de topics
    channel_service.py     # Logica de negocio de canales
    strategy_service.py    # Logica de negocio de estrategias y drafts
    history_service.py     # Logica de negocio de historial
    research_watcher.py    # LISTEN/NOTIFY de research_sessions para WebSocket
    export_service.py      # Generacion de YAML/JSON para descarga
    import_service.py      # Importacion one-time de YAML existentes a PostgreSQL
  models/
    db/                    # SQLAlchemy ORM models
      base.py              # Base declarativa
      channel.py           # Topic + Channel
      strategy.py          # Strategy
      draft.py             # Draft (con JSONB)
      history.py           # ResearchHistory
      research.py          # ResearchSession (multi-session)
    schemas/               # Pydantic schemas (request/response)
      channel.py
      strategy.py
      draft.py
      history.py
      research.py
      export.py
  alembic/                 # Migraciones de base de datos
    alembic.ini
    env.py
    versions/
      001_initial_schema.py
  requirements.txt
  Dockerfile
```

---

## 8. API endpoints

### Base URL

- Desarrollo: `http://localhost:8000/api`
- Produccion: `https://tu-dominio.com/api`

### Autenticacion

Todas las rutas (excepto `/api/health`) requieren header:
```
X-API-Key: <valor de DASHBOARD_API_KEY>
```

### 8.1 Health Check

```
GET /api/health
```

**Respuesta** `200`:
```json
{
  "status": "ok",
  "database": "connected",
  "tables": {
    "topics": true,
    "channels": true,
    "strategies": true,
    "drafts": true,
    "research_history": true,
    "research_sessions": true
  }
}
```

### 8.2 Topics y canales

#### Crear un topic

```
POST /api/topics
Content-Type: application/json

{
  "slug": "options",
  "description": "Options strategies"
}
```

**Validaciones**:
- `slug`: string no vacio, lowercase, sin espacios, max 50 caracteres.
- No puede existir otro topic con el mismo `slug` (constraint UNIQUE en BD).

**Respuesta** `201`:
```json
{
  "id": 1,
  "slug": "options",
  "description": "Options strategies"
}
```

**Respuesta** `409`: `{"detail": "Topic 'options' ya existe"}`.

#### Editar un topic

```
PUT /api/topics/{slug}
Content-Type: application/json

{
  "description": "Updated description"
}
```

**Respuesta** `200`: topic actualizado.
**Respuesta** `404`: `{"detail": "Topic 'xxx' no encontrado"}`.

#### Eliminar un topic

```
DELETE /api/topics/{slug}
```

**Validaciones**:
- No se puede eliminar si el topic tiene canales asociados (debe vaciarse primero).

**Respuesta** `204`: sin cuerpo.
**Respuesta** `404`: topic no encontrado.
**Respuesta** `409`: `{"detail": "No se puede eliminar un topic con canales asociados"}`.

#### Listar todos los topics y canales

```
GET /api/channels
```

**Respuesta** `200`:
```json
{
  "topics": {
    "futures": {
      "description": "Futures strategies",
      "channels": [
        {
          "name": "Jacob Amaral",
          "url": "https://www.youtube.com/@jacobamaral",
          "last_fetched": "2026-03-14"
        }
      ]
    }
  }
}
```

#### Obtener canales de un topic

```
GET /api/channels/{topic}
```

**Respuesta** `200`: objeto del topic con su descripcion y array de canales.
**Respuesta** `404`: `{"detail": "Topic 'xxx' no encontrado"}`.

#### Anadir canal a un topic

```
POST /api/channels/{topic}
Content-Type: application/json

{
  "name": "NQ Scalper",
  "url": "https://www.youtube.com/@nqscalper"
}
```

**Validaciones**:
- `name`: string no vacio, max 100 caracteres.
- `url`: debe ser URL valida de canal de YouTube.
- No puede existir otro canal con la misma `url` en el mismo topic.

**Respuesta** `201`:
```json
{
  "name": "NQ Scalper",
  "url": "https://www.youtube.com/@nqscalper",
  "last_fetched": null
}
```

**Respuesta** `409`: `{"detail": "Canal con URL 'xxx' ya existe en topic 'futures'"}`.
**Respuesta** `422`: error de validacion.

#### Eliminar canal de un topic

```
DELETE /api/channels/{topic}/{channel_name}
```

**Validaciones**:
- El topic debe existir.
- El canal debe existir dentro del topic.
- No se puede eliminar si es el unico canal del topic.

**Respuesta** `204`: sin cuerpo.
**Respuesta** `404`: topic o canal no encontrado.
**Respuesta** `409`: `{"detail": "No se puede eliminar el unico canal del topic"}`.

### 8.3 Historial

#### Listar historial de investigacion

```
GET /api/history?topic=futures&channel=Jacob+Amaral&from=2026-03-01&to=2026-03-31&sort=date&order=desc&page=1&limit=50
```

Todos los query params son opcionales.

**Respuesta** `200`:
```json
{
  "total": 12,
  "page": 1,
  "limit": 50,
  "items": [
    {
      "video_id": "G0c7GAg-FCY",
      "url": "https://youtube.com/watch?v=G0c7GAg-FCY",
      "channel": "Jacob Amaral",
      "topic": "futures",
      "researched_at": "2026-03-14",
      "strategies_found": 1
    }
  ]
}
```

#### Obtener estadisticas del historial

```
GET /api/history/stats
```

**Respuesta** `200`:
```json
{
  "total_videos": 12,
  "total_strategies_found": 8,
  "by_topic": {
    "futures": {"videos": 5, "strategies": 3},
    "trading": {"videos": 7, "strategies": 5}
  },
  "by_channel": {
    "Jacob Amaral": {"videos": 3, "strategies": 2}
  },
  "last_research": {
    "topic": "futures",
    "date": "2026-03-14",
    "videos": 2,
    "strategies": 1
  }
}
```

### 8.4 Estrategias

#### Listar estrategias YAML

```
GET /api/strategies?channel=Jacob+Amaral&search=bollinger
```

Query params opcionales: `channel`, `search` (busca en nombre y descripcion).

**Respuesta** `200`:
```json
{
  "total": 1,
  "strategies": [
    {
      "name": "RTY Hybrid BB Monthly Governor Strategy",
      "description": "A multi-mode futures...",
      "source_channel": "Jacob Amaral",
      "source_videos": ["Building an RTY..."],
      "parameters": [...],
      "entry_rules": [...],
      "exit_rules": [...],
      "risk_management": [...],
      "notes": [...]
    }
  ]
}
```

#### Obtener una estrategia YAML por nombre

```
GET /api/strategies/{strategy_name}
```

**Respuesta** `200`: objeto completo de la estrategia.
**Respuesta** `404`: no encontrada.

#### Listar borradores JSON (drafts)

```
GET /api/strategies/drafts?has_todos=true
```

Query param opcional: `has_todos` (boolean, filtrar solo los que tienen campos `_TODO`).

**Respuesta** `200`:
```json
{
  "total": 1,
  "drafts": [
    {
      "strat_code": 9001,
      "strat_name": "RTY_BB_MonthlyGov_1",
      "symbol": "RTY",
      "active": false,
      "tested": false,
      "prod": false,
      "todo_count": 5,
      "todo_fields": [
        "stop_loss_init.indicator_params.multiple",
        "take_profit_init.indicator_params.multiple",
        "control_params.start_date",
        "control_params.end_date",
        "control_params.timestamp"
      ]
    }
  ]
}
```

#### Obtener un borrador JSON por strat_code

```
GET /api/strategies/drafts/{strat_code}
```

**Respuesta** `200`: el JSON completo del borrador, con un campo adicional `_todo_summary`:
```json
{
  "strat_code": 9001,
  "strat_name": "RTY_BB_MonthlyGov_1",
  "...": "...(todos los campos del JSON original)...",
  "_todo_summary": {
    "count": 5,
    "fields": [
      {"path": "stop_loss_init.indicator_params.multiple", "context": "Stop Loss - multiple de ATR"},
      {"path": "take_profit_init.indicator_params.multiple", "context": "Take Profit - multiple de ATR"},
      {"path": "control_params.start_date", "context": "Fecha de inicio del backtest"},
      {"path": "control_params.end_date", "context": "Fecha de fin del backtest"},
      {"path": "control_params.timestamp", "context": "Timestamp de creacion"}
    ]
  }
}
```

**Respuesta** `404`: borrador no encontrado.

### 8.5 Estado del research (WebSocket)

```
WS /api/research/status
```

**Protocolo**:

1. El cliente abre la conexion WebSocket.
2. El servidor envia el estado actual inmediatamente: un array con todas las sesiones activas (filas con `status='running'` en `research_sessions`).
3. El servidor escucha notificaciones via `LISTEN research_update` en PostgreSQL.
4. Cuando el agente ejecuta `NOTIFY research_update, '<session_id>'`, FastAPI consulta la sesion actualizada y envia el nuevo estado via WebSocket.
5. Si no hay sesiones con `status='running'`, envia `{"sessions": []}`.
6. Fallback: al reconectar, el cliente recibe el estado actual completo de todas las sesiones activas.

**Mensaje del servidor**:
```json
{
  "sessions": [
    {
      "id": 42,
      "status": "running",
      "topic": "futures",
      "step": 4,
      "step_name": "cleanup",
      "step_display": "Limpieza",
      "total_steps": 6,
      "channel": "Jacob Amaral",
      "videos_processing": ["G0c7GAg-FCY"],
      "started_at": "2026-03-14T10:30:00",
      "error_detail": null
    },
    {
      "id": 43,
      "status": "running",
      "topic": "options",
      "step": 2,
      "step_name": "notebooklm-analyst",
      "step_display": "Extrayendo estrategias",
      "total_steps": 6,
      "channel": "OptionsPlay",
      "videos_processing": ["xK9f2a3b"],
      "started_at": "2026-03-14T10:39:00",
      "error_detail": null
    }
  ]
}
```

**Autenticacion WebSocket**: la API key se pasa como query param:
```
ws://localhost:8000/api/research/status?api_key=<key>
```

### 8.6 Estadisticas globales (Dashboard)

```
GET /api/stats
```

**Respuesta** `200`:
```json
{
  "total_topics": 3,
  "total_channels": 5,
  "total_videos_researched": 12,
  "total_strategies": 8,
  "total_drafts": 3,
  "drafts_with_todos": 2,
  "last_research": {
    "topic": "futures",
    "date": "2026-03-14",
    "strategies_found": 1
  }
}
```

---

## 9. Seguridad

### Autenticacion

- **Mecanismo**: API key estatica, configurada via variable de entorno `DASHBOARD_API_KEY`.
- **Header HTTP**: `X-API-Key: <key>`.
- **WebSocket**: query param `api_key=<key>` (los WebSockets no soportan headers custom en el handshake desde el navegador).
- **Respuesta no autenticada**: `401 Unauthorized` con body `{"detail": "API key invalida o no proporcionada"}`.

### CORS

- Variable de entorno `CORS_ORIGINS`: lista separada por comas de origenes permitidos.
- Ejemplo desarrollo: `CORS_ORIGINS=http://localhost:5173`
- Ejemplo produccion: `CORS_ORIGINS=https://dashboard.tu-dominio.com`

### HTTPS

- En produccion, el backend NO gestiona TLS directamente.
- Un proxy reverso (Caddy recomendado por su auto-HTTPS con Let's Encrypt) se encarga del TLS.
- El backend escucha en `0.0.0.0:8000` sin TLS.
- El proxy redirige `https://dashboard.tu-dominio.com` -> `http://api:8000`.
- El frontend se sirve como ficheros estaticos desde el mismo proxy o un servidor Nginx.

### Fichero .env

```env
DASHBOARD_API_KEY=tu-api-key-segura-aqui
CORS_ORIGINS=http://localhost:5173
DATABASE_URL=postgresql+asyncpg://irt:irt_dev_password@localhost:5432/irt
POSTGRES_PASSWORD=irt_dev_password
```

Este fichero esta en `.gitignore`. Se incluye un `.env.example` en el repositorio con valores placeholder.

### Proteccion de datos

- El backend solo accede a la base de datos PostgreSQL via `DATABASE_URL`.
- No expone ficheros del sistema ni de configuracion del pipeline.
- Las queries usan SQLAlchemy ORM (no SQL crudo) para prevenir inyeccion SQL.
- El usuario de PostgreSQL (`irt`) solo tiene permisos sobre la base de datos `irt`.

---

## 10. Despliegue (Docker Compose)

### docker-compose.yml actualizado

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: irt
      POSTGRES_USER: irt
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-irt_dev_password}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U irt"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  pipeline:
    build: .
    volumes:
      - ./config:/app/config
      - ./tools:/app/tools
    environment:
      - DATABASE_URL=postgresql+asyncpg://irt:${POSTGRES_PASSWORD:-irt_dev_password}@postgres:5432/irt
    depends_on:
      postgres:
        condition: service_healthy
    # Servicio existente del pipeline

  api:
    build: ./api
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://irt:${POSTGRES_PASSWORD:-irt_dev_password}@postgres:5432/irt
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "5173:80"
    depends_on:
      - api
    restart: unless-stopped

  # Produccion: anadir servicio de proxy reverso
  # caddy:
  #   image: caddy:2
  #   ports:
  #     - "80:80"
  #     - "443:443"
  #   volumes:
  #     - ./Caddyfile:/etc/caddy/Caddyfile
  #     - caddy_data:/data

volumes:
  pgdata:
    name: irt_pgdata
```

### Volumenes clave

El named volume `pgdata` persiste los datos de PostgreSQL entre reinicios del contenedor. Tanto `pipeline` como `api` se conectan a la misma instancia de PostgreSQL via `DATABASE_URL`. No hay ficheros compartidos en el filesystem: PostgreSQL es el unico punto de contacto entre servicios.

### Dockerfile del API (`api/Dockerfile`)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Ejecutar migraciones de Alembic y arrancar el servidor
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
```

### Dockerfile del Frontend (`frontend/Dockerfile`)

```dockerfile
# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### Desarrollo local

```bash
# PostgreSQL (si no se usa Docker Compose)
docker run -d --name irt-postgres -p 5432:5432 \
  -e POSTGRES_DB=irt -e POSTGRES_USER=irt -e POSTGRES_PASSWORD=irt_dev_password \
  -v irt_pgdata:/var/lib/postgresql/data \
  postgres:16-alpine

# Backend
cd api && pip install -r requirements.txt
alembic upgrade head   # Aplicar migraciones
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install
npm run dev   # Vite dev server en puerto 5173
```

---

## 11. Fuera de alcance

Las siguientes funcionalidades NO estan incluidas en esta version y se consideran trabajo futuro:

- **Edicion de borradores JSON desde el frontend**: los campos `_TODO` se visualizan pero no se editan. La edicion se hace manualmente en los ficheros o via CLI.
- **Lanzar investigaciones desde el frontend**: el research sigue siendo exclusivo de Claude Code CLI. El dashboard solo muestra el estado.
- **Sistema de autenticacion con usuarios**: no hay registro, login con password ni roles. Solo API key unica.
- **Diseno responsive/movil**: el dashboard esta pensado para uso en escritorio. La adaptacion movil es trabajo futuro.
- **Notificaciones push**: cuando una investigacion termina, no se envia notificacion al navegador. El usuario debe estar en la pagina Live.
- **Historial de cambios/audit log**: no se registra quien hizo que cambio en los canales.
- **Exportacion a CSV/Excel**: se ofrece exportacion a YAML/JSON (formatos nativos del pipeline), no a CSV/Excel.
- **Tests E2E del frontend**: los tests unitarios son recomendados pero no obligatorios en la primera iteracion.

---

## 12. Dependencias con el pipeline existente

### 12.1 Dependencia critica: migracion del pipeline a PostgreSQL

Esta es la **dependencia principal** del frontend: el dashboard lee datos de PostgreSQL, por lo que el pipeline CLI debe escribir a PostgreSQL primero. Sin esta migracion, el frontend no tiene datos reales.

**Componentes afectados:**

1. **`tools/youtube/` scripts**: actualmente leen canales desde YAML (`data/channels/channels.yaml`). Deben leer de PostgreSQL (`SELECT` de la tabla `channels`).
2. **`db-manager` skill** (`.claude/skills/db-manager/`): actualmente escribe estrategias a ficheros YAML en `data/strategies/`. Debe hacer `INSERT INTO strategies` e `INSERT INTO drafts` via SQLAlchemy.
3. **Research orchestrator** (`.claude/skills/research/`): debe hacer INSERT/UPDATE a `research_sessions` en cada paso del pipeline y ejecutar `NOTIFY research_update` tras cada UPDATE.
4. **Strategy translator**: actualmente escribe JSON drafts a `data/strategies/drafts/`. Debe hacer `INSERT INTO drafts` con JSONB.
5. **Nueva dependencia compartida**: modulo `tools/db/` con modelos SQLAlchemy y session factory, compartido entre los scripts del pipeline y la API FastAPI.

**Orden de implementacion recomendado:**

1. Crear modelos SQLAlchemy compartidos (`tools/db/models.py`, `tools/db/session.py`)
2. Migrar lectura de canales (`tools/youtube/` → PostgreSQL)
3. Migrar escritura de estrategias (`db-manager` → PostgreSQL)
4. Migrar escritura de drafts (`strategy-translator` → PostgreSQL)
5. Implementar tracking de research sessions
6. Script de importacion one-time de YAML existentes

**Nota para SDD**: Esta migracion puede ejecutarse en paralelo con la construccion del frontend (React), ya que son independientes. Ambas convergen cuando el frontend necesita datos reales de PostgreSQL. Se recomienda planificar como dos tracks paralelos:
- **Track A**: Migracion pipeline → PostgreSQL (prerequisito para datos reales)
- **Track B**: Frontend React (puede usar datos seed/mock inicialmente)

### 12.2 Cambios al research agent

El agente de research debe crear una nueva sesion al inicio y actualizarla durante el pipeline. Ya no hay fila singleton: cada ejecucion es una fila independiente en `research_sessions`.

```
Al iniciar el pipeline:
  INSERT INTO research_sessions (status, topic_id, step, step_name)
    VALUES ('running', <topic_id>, 0, 'preflight')
    RETURNING id;
  -- Guardar el id retornado como session_id para el resto del pipeline
  NOTIFY research_update, '<session_id>';

Al empezar cada paso:
  UPDATE research_sessions SET step=<numero>, step_name=<nombre>,
    channel=<canal si aplica>, videos_processing=<ids>,
    updated_at=NOW() WHERE id=<session_id>;
  NOTIFY research_update, '<session_id>';

Al completar el pipeline:
  UPDATE research_sessions SET status='completed', completed_at=NOW(),
    result_summary=<jsonb>, updated_at=NOW() WHERE id=<session_id>;
  NOTIFY research_update, '<session_id>';

Si ocurre un error:
  UPDATE research_sessions SET status='error', error_detail=<detalle>,
    updated_at=NOW() WHERE id=<session_id>;
  NOTIFY research_update, '<session_id>';
```

No hay paso de "reset a idle". Las sesiones completadas o con error permanecen en la tabla como historial. El estado idle se determina por la ausencia de filas con `status='running'`.

### 12.3 Migracion inicial de datos YAML existentes

Se proporciona un script de importacion one-time (`api/services/import_service.py`) que:

1. Lee los ficheros YAML/JSON existentes en `data/` (channels.yaml, strategies.yaml, history.yaml, drafts/*.json).
2. Los inserta en las tablas correspondientes de PostgreSQL.
3. Maneja deduplicacion (si un canal o estrategia ya existe, lo omite).
4. Se ejecuta una sola vez en el primer setup.

```bash
# Importar datos existentes a PostgreSQL
docker compose run api python -m services.import_service
```

Despues de la importacion, los ficheros YAML/JSON originales se pueden mantener como backup pero ya no son la fuente de verdad.

### 12.4 Exportacion YAML/JSON desde el dashboard

El dashboard ofrece botones de exportacion en las paginas de canales y estrategias:

- **Exportar canales** (`GET /api/export/channels?format=yaml`): genera un `channels.yaml` con la misma estructura que el fichero original.
- **Exportar estrategias** (`GET /api/export/strategies?format=yaml`): genera un `strategies.yaml`.
- **Exportar draft** (`GET /api/export/drafts/{strat_code}?format=json`): genera el JSON del draft.

Estos endpoints generan el fichero al vuelo desde PostgreSQL y lo devuelven como descarga. No se persisten en disco.
