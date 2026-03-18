# Propuesta de Scripts para Backtest

> Estado: propuesta. Aun no implementado.

## Modelo de ejecucion

Los scripts son herramientas independientes y deterministas. Cada uno hace UNA cosa, siempre de la misma manera. La inteligencia (interpretacion, sugerencias, contexto) la aporta el agente de backtest.

Hay dos formas de ejecutarlos:

1. **Via agente**: el usuario pide algo al agente y este invoca el script correspondiente mediante una skill.
2. **Directamente desde terminal**: el usuario ejecuta el script manualmente.

## Estructura de ficheros

```
tools/backtest/
├── validate.py     # Validar un draft: TODOs, campos requeridos
├── run.py          # Lanzar un backtest individual via subproceso del motor
├── stress.py       # Lanzar stress test (variaciones de parametros)
├── montecarlo.py   # Lanzar simulacion Monte Carlo
└── config.py       # Rutas compartidas y valores por defecto
```

## Uso via agente (flujo tipico)

El agente de backtest invoca cada script como una skill, igual que el agente de research invoca yt-scraper o notebooklm-analyst:

```
Agente backtest (orquestador, asistente manual)
  │
  ├── validate skill  →  python tools/backtest/validate.py 9001
  ├── run skill       →  python tools/backtest/run.py 9001 --start 2020-01-01 --end 2024-12-31
  ├── stress skill    →  python tools/backtest/stress.py 9001 ...
  └── montecarlo skill →  python tools/backtest/montecarlo.py 9001 ...
```

El usuario decide cada paso. El agente no encadena automaticamente.

## Uso directo desde terminal

### Validar una estrategia

```bash
python tools/backtest/validate.py 9001
```

### Backtest basico

```bash
python tools/backtest/run.py 9001 --start 2020-01-01 --end 2024-12-31
```

### Con parametros personalizados

```bash
python tools/backtest/run.py 9001 \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --equity 50000 \
  --sizing rpo \
  --risk 0.02
```

### Stress test

```bash
python tools/backtest/stress.py 9001 \
  --start 2020-01-01 \
  --end 2024-12-31
```

### Monte Carlo

```bash
python tools/backtest/montecarlo.py 9001 \
  --start 2020-01-01 \
  --end 2024-12-31
```

## Configuracion (`config.py`)

```python
WORKER_PATH = r"C:\Users\Pablo Nieto\ops-worker-v0.1.0"
PYTHON_EXE = rf"{WORKER_PATH}\.venv\Scripts\python.exe"
ENGINE_PATH = rf"{WORKER_PATH}\packages\backtest-engine"
HIST_DATA_PATH = r"C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros"

# Relativos a la raiz de IRT
DRAFTS_PATH = "data/strategies/drafts"
RESULTS_PATH = "data/backtest/results"
```

## Valores por defecto

| Parametro | Valor por defecto | Descripcion |
|-----------|-------------------|-------------|
| `equity` | 100.000 | Capital inicial en USD |
| `sizing` | `fixed` | Tipo de dimensionamiento |
| `volume` | 1 | Contratos (modo fixed) |
| `slippage` | 1.5 ticks | Deslizamiento simulado |
| `commission` | 0.62 por contrato | Comision por contrato |

## Descripcion de cada script

### `validate.py`

Valida que un draft este listo para backtesting:

- Comprueba que el fichero JSON existe.
- Verifica que no tiene campos `_TODO` pendientes.
- Valida campos requeridos por el motor.
- Devuelve un informe por stdout (OK o lista de problemas).

### `run.py`

Lanza un backtest individual contra el motor:

- Prepara directorio temporal con el JSON de la estrategia.
- Construye el comando subprocess con los argumentos adecuados.
- Ejecuta con `subprocess.run()` capturando stdout y stderr.
- Parsea los marcadores `###METRICS_JSON_START###` / `###METRICS_JSON_END###`.
- Imprime el JSON de metricas por stdout.
- Limpia el directorio temporal.
- Timeout configurable (por defecto 10 minutos).

### `stress.py`

Lanza un stress test (misma estrategia con variaciones de parametros como slippage, comisiones, etc.):

- Usa el modo `stress_test` del motor.
- Devuelve resultados comparativos por stdout.

### `montecarlo.py`

Lanza una simulacion Monte Carlo (simulaciones aleatorias sobre trades para medir robustez):

- Usa el modo `monte_carlo` del motor.
- Devuelve metricas de distribucion por stdout.

### `config.py`

Centraliza rutas y valores por defecto. Valida que las rutas existan al importar el modulo.

## Futuro (fuera de alcance actual)

- **Modo portfolio**: ejecutar varias estrategias y agregar resultados (job type `portfolio` del worker).
- **Integration test**: validacion end-to-end (job type `integration_test` del worker).
- **Integracion con frontend**: mostrar resultados en el dashboard de IRT.
