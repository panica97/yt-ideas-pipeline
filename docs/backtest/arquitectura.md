# Arquitectura del Backtest Local

## Contexto: Worker de Operations-Platform

El worker es un paquete standalone descargado desde Railway (Operations-Platform) en formato ZIP. Se encuentra descomprimido en:

```
C:\Users\Pablo Nieto\ops-worker-v0.1.0\
```

En produccion, este worker sondea la API de Railway buscando jobs pendientes. Para el backtest local **ignoramos esa logica por completo** y llamamos directamente al motor.

### Estructura relevante del worker

```
ops-worker-v0.1.0/
├── .venv/
│   └── Scripts/
│       └── python.exe          ← Python con TA-Lib, polars, etc.
├── packages/
│   ├── backtest-engine/
│   │   ├── main.py             ← Punto de entrada del motor
│   │   └── logs_backtest/      ← Resultados cuando se usa --save
│   └── ibkr-core/
│       ├── strategies/         ← Loader de estrategias
│       ├── schema/             ← Esquema de validacion
│       └── indicators/         ← Libreria de indicadores
```

El `.venv` del worker ya tiene instaladas todas las dependencias necesarias (TA-Lib, polars, numpy, etc.), asi que no necesitas instalar nada adicional.

## Invocacion del motor

El backtest-engine se ejecuta como subproceso desde los scripts de IRT:

```bash
<ruta_worker>\.venv\Scripts\python.exe <ruta_worker>\packages\backtest-engine\main.py \
  --mode single \
  --strategy <ID> \
  --start YYYY-MM-DD \
  --end YYYY-MM-DD \
  --equity 100000 \
  --sizing fixed \
  --volume 1 \
  --risk 0.02 \
  --hist-data-path "C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros" \
  --strategies-path <directorio_con_jsons> \
  --save \
  --metrics-json
```

### Argumentos del motor

| Argumento | Descripcion | Ejemplo |
|-----------|-------------|---------|
| `--mode` | Modo de ejecucion | `single` |
| `--strategy` | Codigo de la estrategia | `9001` |
| `--start` | Fecha de inicio | `2020-01-01` |
| `--end` | Fecha de fin | `2024-12-31` |
| `--equity` | Capital inicial | `100000` |
| `--sizing` | Tipo de dimensionamiento | `fixed`, `rpo`, `half_kelly` |
| `--volume` | Numero de contratos (modo fixed) | `1` |
| `--risk` | Riesgo por operacion (modo rpo) | `0.02` |
| `--hist-data-path` | Ruta a datos historicos | `C:\...\data_futuros` |
| `--strategies-path` | Directorio con JSONs de estrategias | `<temp_dir>` |
| `--save` | Guardar resultados en disco | (flag) |
| `--metrics-json` | Emitir metricas en formato JSON por stdout | (flag) |

### Tipos de job del worker

| Tipo | Descripcion | Estado |
|------|-------------|--------|
| `single` | Backtest de una estrategia | Disponible |
| `stress_test` | Misma estrategia con variaciones de parametros (slippage, comisiones, etc.) | Disponible |
| `monte_carlo` | Simulaciones aleatorias sobre trades para medir robustez | Disponible |
| `portfolio` | Varias estrategias juntas | FUTURO, fuera de alcance |
| `integration_test` | Validacion end-to-end | FUTURO, fuera de alcance |

### Lectura de resultados

Con `--metrics-json`, el motor emite los resultados por stdout entre marcadores:

```
###METRICS_JSON_START###
{"total_trades": 142, "win_rate": 0.58, "sharpe": 1.23, ...}
###METRICS_JSON_END###
```

Los scripts de IRT parsean ese bloque para obtener las metricas.

Con `--save`, los resultados se guardan en:

```
packages/backtest-engine/logs_backtest/{strategy_id}/{YYYYMMDD_XXX}/
├── trades.parquet
├── metrics.json
└── candles.parquet
```

## Integracion con IRT

### Patron: agente + scripts

El backtest en IRT sigue el mismo patron que el pipeline de research: un **agente orquestador** que invoca **scripts independientes** mediante skills. El agente es un asistente manual — el usuario decide que paso ejecutar y cuando.

```
Agente backtest (orquestador, asistente manual)
  │
  ├── validate skill  →  python tools/backtest/validate.py <strategy_id>
  ├── run skill       →  python tools/backtest/run.py <strategy_id> --start ... --end ...
  ├── stress skill    →  python tools/backtest/stress.py <strategy_id> ...
  └── montecarlo skill →  python tools/backtest/montecarlo.py <strategy_id> ...
```

Mismo patron que el agente de research:

```
Agente research (orquestador)
  ├── yt-scraper skill       →  python -m tools.youtube.search ...
  ├── notebooklm-analyst skill →  notebooklm CLI
  └── db-manager skill       →  python -m tools.db ...
```

### Flujo tipico (el usuario decide cada paso)

1. El usuario pide: "valida la estrategia 9001" → el agente ejecuta `validate.py`
2. El usuario revisa → "lanza un backtest de la 9001 desde 2020" → el agente ejecuta `run.py`
3. El usuario ve resultados, decide → "hazle un stress test" → el agente ejecuta `stress.py`
4. El usuario decide → "lanza monte carlo" → el agente ejecuta `montecarlo.py`

El agente **no encadena pasos automaticamente**. El usuario tiene el control.

### Principio de diseno: scripts deterministas, agente inteligente

- **Scripts**: independientes, hacen UNA cosa, siempre de la misma manera. Deterministas.
- **Agente**: aporta inteligencia (interpretacion de resultados, sugerencias, contexto). No aporta logica de ejecucion.

### Pasos detallados (dentro de cada script)

1. **Preparar estrategia**: Copiar el JSON del draft a un directorio temporal que el motor pueda leer como `--strategies-path`.
2. **Construir comando**: Montar la linea de comandos con los argumentos adecuados, usando el Python del `.venv` del worker.
3. **Ejecutar subproceso**: Lanzar `subprocess.run()` capturando stdout y stderr.
4. **Parsear resultados**: Buscar los marcadores `###METRICS_JSON_START###` / `###METRICS_JSON_END###` en stdout y extraer el JSON.
5. **Devolver resultados**: Imprimir por stdout para que el agente (o el usuario) los recoja.

### Consideraciones

- El directorio temporal de estrategias se limpia despues de cada ejecucion.
- Si el draft tiene campos `_TODO`, la validacion fallara. Hay que resolverlos antes de lanzar un backtest.
- El motor usa el `.venv` del worker, asi que no interfiere con el entorno de IRT.
