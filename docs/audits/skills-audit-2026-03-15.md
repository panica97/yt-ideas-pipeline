# Auditoria de Skills IRT - 2026-03-15

## Resumen ejecutivo

Se han auditado las 5 skills existentes en `.claude/skills/` y el agente de research en `.claude/agents/research/`. El proyecto CLAUDE.md menciona skills `yt-channels`, `yt-search` y `_shared` que **no existen** en el repositorio, lo cual es la primera inconsistencia detectada.

En general, las skills estan bien estructuradas y cubren el pipeline completo. Los problemas principales son: (1) inconsistencias entre la documentacion y el codigo real, (2) duplicacion entre el SKILL.md de research y el AGENT.md del agente, (3) el skill de notebooklm es desproporcionadamente grande para lo que se necesita en el pipeline, y (4) falta de skills que CLAUDE.md promete que existen.

---

## 1. Skill: research (`.claude/skills/research/SKILL.md`)

### Estado actual
Orquestador del pipeline. Describe 7 pasos (0-6) con session tracking en PostgreSQL. Contiene codigo de ejemplo para cada operacion de base de datos.

### Problemas encontrados

1. **Duplicacion con AGENT.md** (Alta): El SKILL.md y el AGENT.md describen el mismo pipeline pero con diferencias sutiles. El SKILL.md tiene 7 pasos (preflight + 6), el AGENT.md tiene 7 pasos (0-6). El SKILL.md menciona "translator" como paso 3, el AGENT.md lo desarrolla en detalle. Esto puede confundir a Claude sobre cual seguir.

2. **El SKILL.md no deberia existir en esta forma** (Alta): Segun la arquitectura, `/research` activa un agente (AGENT.md), no un skill. El SKILL.md de research actua como una segunda descripcion del mismo flujo, con enfasis en session tracking. Deberia fusionarse todo en el AGENT.md.

3. **Paso "translator" sin skill propio** (Media): El SKILL.md lista "translator" como step 3, pero no existe un skill `translator/SKILL.md`. El AGENT.md describe el paso en detalle inline. Esto funciona porque el agente ejecuta el paso directamente, pero el SKILL.md da a entender que es un skill separado.

4. **Codigo de ejemplo de DB verboso** (Baja): El SKILL.md incluye ~40 lineas de codigo Python para session tracking. Esto consume contexto innecesariamente. El agente deberia conocer la API, no necesitar el codigo completo.

### Recomendaciones

- **Eliminar el SKILL.md de research** o reducirlo a un trigger que diga "ejecuta el agente de research". Toda la logica del pipeline debe vivir en el AGENT.md.
- **Mover el session tracking a una seccion compacta** del AGENT.md con solo las firmas de funcion, no el codigo completo.
- Prioridad: **Alta**

---

## 2. Skill: yt-scraper (`.claude/skills/yt-scraper/SKILL.md`)

### Estado actual
Bien enfocado. Un unico comando, reglas claras, filtrado de videos ya investigados con dos caminos (PostgreSQL y YAML fallback).

### Problemas encontrados

1. **Uso de funcion privada `_resolve_topic_id`** (Media): El skill instruye al agente a importar `_resolve_topic_id` que es una funcion privada (prefijo `_`) de `research_repo.py`. No hay una API publica expuesta para esto. Si se refactoriza el repo, el skill se rompe silenciosamente.

2. **Codigo SQL inline** (Media): El skill contiene un bloque de codigo con imports de SQLAlchemy, select statements, etc. Un sub-agente de Claude deberia ejecutar esto literalmente, lo cual es fragil. Seria mejor tener una funcion de utilidad como `get_researched_video_ids(topic_slug)` en el repo.

3. **Inconsistencia en early stops** (Baja): El skill define `NO_VIDEOS_FOUND` y `NO_NEW_VIDEOS` como dos senales distintas. El SKILL.md de research solo menciona `NO_VIDEOS_FOUND`. El AGENT.md menciona ambas. El SKILL.md de research deberia listarlas todas.

4. **No menciona `--count` ni limites** (Baja): El comando `fetch_topic` probablemente acepta parametros de cantidad, pero el skill no los documenta. El agente siempre obtendra todos los videos disponibles.

### Recomendaciones

- **Crear una funcion publica** `get_researched_video_ids(topic_slug: str) -> set[str]` en `research_repo.py` o `history_repo.py`, y referenciarla en el skill en vez de codigo SQL inline.
- **Documentar parametros opcionales** del comando `fetch_topic`.
- **Alinear las senales de parada** entre todos los skills.
- Prioridad: **Media**

---

## 3. Skill: notebooklm (`.claude/skills/notebooklm/SKILL.md`)

### Estado actual
Documentacion exhaustiva de la API completa de NotebookLM. Es el skill mas grande (~500 lineas). Cubre creacion de notebooks, gestion de sources, generacion de artefactos, descargas, idiomas, troubleshooting, etc.

### Problemas encontrados

1. **Contexto excesivo para el pipeline** (Alta): Este skill se carga cada vez que se usa cualquier comando `notebooklm`. Son ~500 lineas de contexto. Para el pipeline de research, solo se necesitan 5 comandos (`create`, `source add`, `source wait`, `ask`, `delete`). El resto (podcasts, videos, slides, mind maps, quizzes, idiomas, deep research) es irrelevante y consume tokens.

2. **Doble proposito sin separacion** (Media): El skill sirve tanto para uso interactivo del usuario ("crea un podcast sobre X") como para el pipeline de research (analisis automatizado). Estos son casos de uso muy diferentes que comparten el mismo bloque de contexto.

3. **Intent detection demasiado amplio** (Baja): "Summarize these URLs/documents", "Turn this into an audio overview" son triggers que podrian activar el skill cuando el usuario quiere algo mas simple. No causa problemas graves porque el skill tiene reglas de autonomia claras.

4. **Tabla de tiempos sin impacto real** (Baja): La tabla de "Processing times" (~15 lineas) con timeouts sugeridos es util para el usuario interactivo, pero consume contexto cuando se carga para el pipeline.

### Recomendaciones

- **No dividir el skill** (es una API externa con un CLI unico, dividirlo causaria mas problemas que beneficios). En su lugar, considerar si el AGENT.md de research puede listar los 5 comandos que necesita directamente sin cargar el skill completo.
- **Evaluar si el agente de research necesita cargar este skill**: El AGENT.md ya tiene los comandos de notebooklm-analyst que a su vez solo usa los 5 comandos basicos. Si el agente nunca necesita el skill completo, no deberia cargarse.
- Prioridad: **Media** (no rompe nada, pero afecta eficiencia de tokens)

---

## 4. Skill: notebooklm-analyst (`.claude/skills/notebooklm-analyst/SKILL.md`)

### Estado actual
Compacto y bien definido. 70 lineas. Workflow claro de 7 pasos, formato YAML de salida especificado, manejo de errores explicito.

### Problemas encontrados

1. **Conflicto con AGENT.md sobre borrar el notebook** (Alta): El SKILL.md dice "DELETE the notebook when done (always, even if errors occur)" (regla 7 y seccion "CRITICAL"). Sin embargo, el AGENT.md dice "IMPORTANTE: NO borrar el notebook todavia. El translator puede necesitarlo para consultas adicionales." Esto es una **contradiccion directa**. Si el agente carga este skill, el skill le dice que borre, pero el agente le dice que no borre.

2. **No menciona el flag `-n`** (Media): El skill muestra el flag `-n <id>` en los comandos de ejemplo, pero no lo lista como una regla obligatoria de forma prominente. La seccion "Rules" dice "Use the `-n <notebook_id>` flag in all commands", pero deberia estar mas destacado dado que es critico para evitar conflictos de contexto.

3. **Falta `source_channel` en el ejemplo de output** (Baja): El formato YAML incluye `source_channel` pero no explica de donde viene. Cuando un notebook tiene videos de multiples canales, el agente tiene que inferirlo del titulo del source.

4. **No menciona limites de sources** (Baja): No advierte sobre la cantidad maxima de videos que se pueden anadir como sources (depende del plan de NotebookLM).

### Recomendaciones

- **Resolver la contradiccion sobre el borrado**: Eliminar la instruccion de borrar del SKILL.md del analyst. El borrado es responsabilidad del orquestador (AGENT.md, step 4). El analyst solo extrae estrategias.
- **Anadir una nota** sobre el limite de sources de NotebookLM.
- Prioridad: **Alta** (la contradiccion sobre el borrado puede causar perdida de datos del notebook antes de completar la traduccion)

---

## 5. Skill: db-manager (`.claude/skills/db-manager/SKILL.md`)

### Estado actual
Compacto (68 lineas). Describe como guardar estrategias en PostgreSQL con deduplicacion. Tiene fallback a YAML.

### Problemas encontrados

1. **Funcion `insert_strategy` vs API real** (Media): El skill documenta la API como `insert_strategy(session, strategy_data)` que recibe un dict. El codigo real confirma que esto existe, pero internamente llama a `upsert_strategy` con parametros con nombre. El skill no menciona `upsert_strategy` que es la funcion real de deduplicacion. Si alguien mira el codigo y el skill, la desconexion puede confundir.

2. **No menciona drafts** (Media): El pipeline de research ahora incluye un paso de traduccion a JSON que genera borradores (drafts). Existe `draft_repo.py` con `upsert_draft()`. Sin embargo, el db-manager skill no menciona esta funcionalidad. El agente de research guarda drafts en ficheros locales (`data/strategies/drafts/`), pero tambien podria usar la DB.

3. **Output "saved/skipped" impreciso** (Baja): El output format dice "skipped" para duplicados, pero la implementacion hace upsert (actualiza). Deberia decir "updated" en vez de "skipped".

4. **Fallback YAML no refleja la realidad** (Baja): El skill dice que el fallback escribe a `data/strategies/strategies.yaml`, pero el AGENT.md no menciona este fichero. El pipeline parece haber migrado completamente a PostgreSQL, con el YAML como legacy.

### Recomendaciones

- **Anadir seccion de drafts**: Documentar como guardar borradores JSON usando `draft_repo.upsert_draft()`, o al menos mencionar que existe.
- **Corregir el output format**: Cambiar "skipped" a "updated" para duplicados.
- **Evaluar si el fallback YAML sigue siendo necesario**: Si el pipeline requiere PostgreSQL para session tracking, el fallback YAML de strategies tiene poco sentido.
- Prioridad: **Media**

---

## 6. Agente: research (`.claude/agents/research/AGENT.md`)

### Estado actual
Agente bien estructurado con 7 pasos secuenciales (0-6). Incluye preflight check, scraping, analisis, traduccion, cleanup, guardado y resumen. Referencia ficheros de soporte (schema.json, examples, translation-rules.md) que existen en el repo.

### Problemas encontrados

1. **Instruccion de leer SKILL.md de otros skills** (Alta): El AGENT.md dice "Lee las instrucciones de `.claude/skills/yt-scraper/SKILL.md`" y "Lee las instrucciones de `.claude/skills/notebooklm-analyst/SKILL.md`". Esto implica que el agente debe **leer esos ficheros durante la ejecucion**, lo cual consume tokens del contexto del agente. El agente deberia tener toda la informacion necesaria inline, o al menos los comandos concretos, sin necesidad de cargar skills adicionales.

2. **Step 3 (translator) es complejo y no tiene skill** (Media): El paso de traduccion es el mas complejo del pipeline (mapear lenguaje natural a JSON con schema, few-shot examples, y consultas de seguimiento a NotebookLM). Sin embargo, esta definido inline en el AGENT.md sin skill propio. Esto funciona pero hace el AGENT.md mas largo de lo necesario.

3. **Step 5 dice YAML pero el sistema usa PostgreSQL** (Media): "Lee las instrucciones de `.claude/skills/db-manager/SKILL.md` y guarda las estrategias en `data/strategies/strategies.yaml`". Esto es confuso porque el db-manager skill habla de PostgreSQL como principal y YAML como fallback. Deberia decir "guarda las estrategias en la base de datos".

4. **Seccion Feedback vacia** (Baja): La seccion de feedback tiene solo comentarios HTML de ejemplo. Esto es un placeholder correcto, pero consume unas lineas de contexto sin aportar.

5. **No documenta la relacion con el SKILL.md de research** (Baja): El agente no sabe que existe un SKILL.md de research que describe session tracking. Si el agente se ejecuta sin cargar el SKILL.md, pierde toda la funcionalidad de tracking de sesiones.

6. **`strat_code` 9001+ para drafts** (Baja): El AGENT.md dice "Usar strat_code 9001+ para borradores (incrementando si ya existe)". Esto funciona para ficheros locales, pero con la DB (`draft_repo.upsert_draft`), deberia consultar el max strat_code existente para evitar conflictos.

### Recomendaciones

- **Eliminar las instrucciones de "leer SKILL.md"**: En su lugar, incluir los comandos necesarios directamente en el AGENT.md (son pocos y especificos). Esto evita cargar skills completos.
- **Integrar session tracking del SKILL.md en el AGENT.md**: Si el agente necesita session tracking, debe tenerlo en su propio fichero.
- **Corregir Step 5** para reflejar que el almacenamiento principal es PostgreSQL.
- **Evaluar crear un skill `translator`**: Si el paso de traduccion crece con mas reglas y feedback, merece su propio skill.
- Prioridad: **Alta** (la instruccion de leer otros SKILL.md duplica contexto)

---

## 7. Skills inexistentes mencionadas en CLAUDE.md

### Problema

El `CLAUDE.md` del proyecto lista estas skills en la estructura:
- `yt-channels/` - No existe
- `yt-search/` - No existe
- `_shared/` - No existe

Las skills reales en `.claude/skills/` son: `research`, `yt-scraper`, `notebooklm`, `notebooklm-analyst`, `db-manager`.

### Analisis

- `yt-channels` y `yt-search` probablemente fueron absorbidos por `yt-scraper`, que maneja tanto la busqueda como el acceso a canales.
- `_shared` (convenciones compartidas) nunca se creo. Las convenciones globales estan en `~/.claude/CLAUDE.md`, no a nivel de proyecto.

### Recomendaciones

- **Actualizar CLAUDE.md** para reflejar las skills reales.
- Prioridad: **Alta** (CLAUDE.md es el primer fichero que lee Claude para entender el proyecto)

---

## Problemas transversales

### A. Duplicacion de contexto entre SKILL.md y AGENT.md

El pipeline de research tiene documentacion en tres sitios:
1. `.claude/skills/research/SKILL.md` (session tracking + pipeline overview)
2. `.claude/agents/research/AGENT.md` (pipeline detallado)
3. `CLAUDE.md` del proyecto (pipeline overview)

Cuando el agente se ejecuta, potencialmente carga los tres. Recomendacion: **una unica fuente de verdad en AGENT.md**.

### B. Instrucciones de "leer otros SKILL.md" multiplican contexto

El AGENT.md dice "lee el SKILL.md de X" en 3 pasos. Si el agente carga los 3 SKILL.md, suma:
- yt-scraper: ~65 lineas
- notebooklm-analyst: ~70 lineas
- db-manager: ~68 lineas
- notebooklm (indirecto via analyst): ~500 lineas

Total potencial: ~700 lineas de contexto extra. Mejor: incluir los 3-5 comandos relevantes inline.

### C. PostgreSQL vs YAML: estado de transicion

El proyecto esta migrando de ficheros YAML a PostgreSQL. Algunos skills solo hablan de YAML (AGENT.md step 5), otros solo de PostgreSQL (research SKILL.md), y otros de ambos con fallback (yt-scraper, db-manager). Deberia definirse claramente cual es el almacenamiento principal y eliminar las referencias al que ya no se usa.

### D. Senales de parada no alineadas

| Senal | yt-scraper | research SKILL.md | AGENT.md |
|-------|-----------|-------------------|----------|
| NO_VIDEOS_FOUND | Si | Si | Si |
| NO_NEW_VIDEOS | Si | No | Si |
| NO_STRATEGIES_FOUND | No | Si | Si |
| AUTH_ERROR | No | No | Si |
| ERROR | No | No | Si |

Todas las senales deberian estar documentadas en todos los puntos donde se usan.

---

## Plan de accion priorizado

### Prioridad Alta

| # | Accion | Impacto |
|---|--------|---------|
| 1 | **Resolver contradiccion de borrado de notebook** entre notebooklm-analyst SKILL.md y AGENT.md. Eliminar la instruccion de borrado del analyst; el orquestador maneja el cleanup. | Evita perdida de datos del notebook antes de la traduccion |
| 2 | **Fusionar research SKILL.md en AGENT.md**. El SKILL.md se reduce a un trigger de 5 lineas: "Ejecuta el agente de research para el topic dado". Toda la logica (incluido session tracking) va al AGENT.md. | Elimina duplicacion y contradicciones |
| 3 | **Eliminar "lee el SKILL.md de X" del AGENT.md**. Incluir los comandos necesarios directamente (son ~5 por skill). | Reduce contexto del agente en ~700 lineas |
| 4 | **Actualizar CLAUDE.md** del proyecto: eliminar skills inexistentes (yt-channels, yt-search, _shared), anadir translator como concepto inline del agente. | CLAUDE.md refleja la realidad |

### Prioridad Media

| # | Accion | Impacto |
|---|--------|---------|
| 5 | **Crear funcion publica `get_researched_video_ids()`** en history_repo.py para eliminar el SQL inline del yt-scraper SKILL.md. | Codigo mas robusto y mantenible |
| 6 | **Anadir seccion de drafts al db-manager SKILL.md** o crear skill separado para gestion de drafts. | Pipeline de traduccion documentado end-to-end |
| 7 | **Resolver ambiguedad PostgreSQL vs YAML**: Definir en CLAUDE.md que PostgreSQL es el almacenamiento principal y YAML es solo fallback para desarrollo sin DB. Actualizar el AGENT.md step 5 en consecuencia. | Elimina confusion sobre donde se guardan los datos |
| 8 | **Evaluar si el skill completo de notebooklm se carga innecesariamente**: Si el agente de research no necesita las ~500 lineas del skill de notebooklm (porque usa directamente los 5 comandos basicos), asegurarse de que no se carga. | Ahorro significativo de tokens |

### Prioridad Baja

| # | Accion | Impacto |
|---|--------|---------|
| 9 | Corregir output format de db-manager: "skipped" a "updated" para duplicados. | Precision en reportes |
| 10 | Documentar parametros opcionales de `fetch_topic` en yt-scraper. | Completitud |
| 11 | Alinear senales de parada en todos los skills (tabla de referencia unica). | Consistencia |
| 12 | Limpiar seccion Feedback vacia del AGENT.md. | Limpieza menor |
| 13 | Anadir nota sobre limites de sources de NotebookLM en notebooklm-analyst. | Prevencion de errores en lotes grandes |

---

## Checklist de verificacion

Cada item tiene un criterio concreto que un agente puede comprobar. Estado: `[ ]` pendiente, `[x]` corregido.

### Prioridad Alta

- [x] **AUDIT-001**: Contradiccion borrado notebook *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/notebooklm-analyst/SKILL.md`
  - **Verificar**: El fichero NO contiene instrucciones de borrar el notebook ("delete", "DELETE", "borra", "borrar", "cleanup"). El borrado es responsabilidad exclusiva del orquestador (AGENT.md step 4).
  - **Comando**: `grep -i -E "(delete|borra|borrar|cleanup)" .claude/skills/notebooklm-analyst/SKILL.md` debe devolver 0 coincidencias o solo referencias a que NO se debe borrar.

- [x] **AUDIT-002**: Duplicacion research SKILL.md / AGENT.md *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/research/SKILL.md`
  - **Verificar**: El SKILL.md tiene maximo 20 lineas y solo actua como trigger/redirect al agente. No contiene logica de pipeline, session tracking ni codigo Python.
  - **Comando**: `wc -l .claude/skills/research/SKILL.md` debe devolver <= 20. `grep -c "import\|def \|session" .claude/skills/research/SKILL.md` debe devolver 0.

- [x] **AUDIT-003**: Context bloat por "lee el SKILL.md de X" *(corregido 2026-03-15)*
  - **Fichero**: `.claude/agents/research/AGENT.md`
  - **Verificar**: El AGENT.md NO contiene instrucciones de leer otros SKILL.md. Los comandos necesarios estan incluidos inline.
  - **Comando**: `grep -c "SKILL.md" .claude/agents/research/AGENT.md` debe devolver 0.

- [x] **AUDIT-004**: CLAUDE.md referencia skills inexistentes *(corregido 2026-03-15)*
  - **Fichero**: `CLAUDE.md`
  - **Verificar**: No menciona `yt-channels/`, `yt-search/`, ni `_shared/` como directorios de skills. La estructura listada coincide con los directorios reales en `.claude/skills/`.
  - **Comando**: `grep -E "(yt-channels|yt-search|_shared)" CLAUDE.md` debe devolver 0 coincidencias.

### Prioridad Media

- [x] **AUDIT-005**: Funcion publica get_researched_video_ids *(corregido 2026-03-15)*
  - **Fichero**: `tools/db/repos/history_repo.py`
  - **Verificar**: Existe una funcion publica (sin prefijo `_`) que devuelve los IDs de videos ya investigados para un topic.
  - **Comando**: `grep -c "def get_researched_video_ids" tools/db/repos/history_repo.py` debe devolver >= 1.

- [x] **AUDIT-006**: db-manager documenta drafts *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/db-manager/SKILL.md`
  - **Verificar**: El fichero menciona drafts y la funcion `upsert_draft` o equivalente.
  - **Comando**: `grep -c -i "draft" .claude/skills/db-manager/SKILL.md` debe devolver >= 1.

- [x] **AUDIT-007**: PostgreSQL como almacenamiento principal *(corregido 2026-03-15)*
  - **Ficheros**: `.claude/agents/research/AGENT.md`, `CLAUDE.md`
  - **Verificar**: No hay instrucciones de guardar estrategias en YAML como paso principal. YAML solo se menciona como fallback o legacy si acaso.
  - **Comando**: `grep -c "strategies.yaml" .claude/agents/research/AGENT.md` debe devolver 0.

- [x] **AUDIT-008**: Skill notebooklm no se carga innecesariamente *(corregido 2026-03-15)*
  - **Fichero**: `.claude/agents/research/AGENT.md`
  - **Verificar**: El AGENT.md no instruye a cargar `.claude/skills/notebooklm/SKILL.md`. Los comandos de notebooklm necesarios estan inline o en el skill de notebooklm-analyst.
  - **Comando**: `grep -c "skills/notebooklm/SKILL.md" .claude/agents/research/AGENT.md` debe devolver 0.

### Prioridad Baja

- [x] **AUDIT-009**: Output format db-manager corregido *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/db-manager/SKILL.md`
  - **Verificar**: Para duplicados, el formato de salida dice "updated" (no "skipped").
  - **Comando**: `grep -c "skipped" .claude/skills/db-manager/SKILL.md` debe devolver 0 (o referirse solo a videos, no a estrategias).

- [x] **AUDIT-010**: Parametros documentados en yt-scraper *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/yt-scraper/SKILL.md`
  - **Verificar**: El skill documenta el parametro `--count` o equivalente para limitar videos.
  - **Comando**: `grep -c -i "count\|limit\|cantidad" .claude/skills/yt-scraper/SKILL.md` debe devolver >= 1.

- [x] **AUDIT-011**: Senales de parada alineadas *(corregido 2026-03-15)*
  - **Ficheros**: `.claude/skills/research/SKILL.md`, `.claude/skills/yt-scraper/SKILL.md`, `.claude/agents/research/AGENT.md`
  - **Verificar**: Las 5 senales (NO_VIDEOS_FOUND, NO_NEW_VIDEOS, NO_STRATEGIES_FOUND, AUTH_ERROR, ERROR) estan documentadas en el punto de entrada del pipeline (AGENT.md o research SKILL.md).
  - **Comando**: `grep -c "NO_VIDEOS_FOUND\|NO_NEW_VIDEOS\|NO_STRATEGIES_FOUND\|AUTH_ERROR" .claude/agents/research/AGENT.md` debe devolver >= 4.

- [x] **AUDIT-012**: Seccion Feedback limpia en AGENT.md *(corregido 2026-03-15)*
  - **Fichero**: `.claude/agents/research/AGENT.md`
  - **Verificar**: No hay bloques de comentarios HTML vacios o placeholders sin contenido.
  - **Comando**: `grep -c "<!--" .claude/agents/research/AGENT.md` debe devolver 0.

- [x] **AUDIT-013**: Limites de sources documentados *(corregido 2026-03-15)*
  - **Fichero**: `.claude/skills/notebooklm-analyst/SKILL.md`
  - **Verificar**: Menciona el limite maximo de sources por notebook.
  - **Comando**: `grep -c -i "limit\|limite\|maximo\|max" .claude/skills/notebooklm-analyst/SKILL.md` debe devolver >= 1.
