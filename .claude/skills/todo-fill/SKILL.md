---
name: todo-fill
description: Rellena los campos _TODO pendientes de drafts de estrategias aprobadas (validated), preguntando al usuario de forma interactiva. Usar cuando el usuario diga "rellenar todos", "completar campos", "/todo-fill", "revisar pendientes", "rellenar TODOs", o quiera completar datos que faltan en las estrategias.
---

# Todo Fill

Recorre los drafts validados que tienen campos `_TODO` pendientes y los rellena de forma conversacional, preguntando al usuario cada valor.

## Configuracion

- **API base:** `http://localhost:8000`
- **API key:** leer `DASHBOARD_API_KEY` del fichero `.env` del proyecto
- **Header de autenticacion:** `X-API-Key: <valor>`

## Flujo

### 1. Obtener drafts con TODOs pendientes

```
GET /api/strategies/drafts?has_todos=true&status=validated
Header: X-API-Key: <DASHBOARD_API_KEY>
```

Si la respuesta esta vacia o no hay drafts, informar: "No hay drafts con TODOs pendientes" y terminar.

### 2. Mostrar resumen inicial

Contar el total de TODOs sumando `todo_count` de cada draft. Mostrar:

> **X drafts con Y TODOs pendientes**

Listar brevemente los drafts afectados (strat_code + strat_name).

### 3. Agrupar TODOs por campo comun

Antes de preguntar, agrupar: si el mismo `path` (ej: `multiplier`) aparece como _TODO en varios drafts de la **misma estrategia base** (mismo prefijo de nombre antes del sufijo _Long/_Short), preguntar una sola vez y aplicar a todos los drafts que lo comparten.

### 4. Resolver campos de instrumento automaticamente

Los campos `multiplier`, `minTick`, `symbol`, `exchange`, `currency`, `secType` se pueden resolver desde la tabla de instrumentos. Cuando alguno de estos campos este como _TODO:

1. Consultar `GET /api/instruments` para obtener la lista de instrumentos disponibles
2. Preguntar al usuario que instrumento quiere usar (con AskUserQuestion, mostrando las opciones disponibles)
3. Consultar `GET /api/instruments/{symbol}` para obtener los datos del instrumento
4. Mapeo de campos del instrumento a campos del draft:
   - `instrument.multiplier` → path `multiplier`
   - `instrument.min_tick` → path `minTick`
   - `instrument.symbol` → path `symbol`
   - `instrument.exchange` → path `exchange`
   - `instrument.currency` → path `currency`
   - `instrument.sec_type` → path `secType`
5. Rellenar automaticamente SOLO los campos que esten como _TODO (no sobreescribir valores existentes)
6. Aplicar a todos los drafts del grupo que compartan esos TODOs

### 5. Para cada TODO restante, preguntar al usuario

Para los campos que no se hayan resuelto con el instrumento:

1. Mostrar el **nombre legible** del campo (ver mapeo abajo)
2. Indicar a que draft(s) pertenece: `strat_code` + `strat_name`
3. Preguntar el valor al usuario con AskUserQuestion
4. Si el usuario dice **"skip"**, **"saltar"** o **"pasar"**, saltar al siguiente TODO
5. Parsear el valor: si es numerico, enviarlo como numero; si no, como string

**Excepcion: `max_timePeriod`** — este campo se resuelve automaticamente sin preguntar. Es el mayor `timePeriod_1` de todos los indicadores del draft. Para calcularlo:
1. Obtener el draft completo via `GET /api/strategies/drafts/{strat_code}`
2. Recorrer todos los indicadores en `data.ind_list` (todos los timeframes)
3. Encontrar el mayor valor de `params.timePeriod_1` (ignorar los que sean `_TODO`)
4. Usar ese valor como `max_timePeriod`
5. Dejar este campo para el final, despues de haber resuelto los demas TODOs (por si algun `timePeriod` se acaba de rellenar)
6. Informar al usuario: "Periodo maximo calculado automaticamente: X"

### 6. Aplicar cada valor

Para cada draft afectado, llamar:

```
PATCH /api/strategies/drafts/{strat_code}/fill-todo
Header: X-API-Key: <DASHBOARD_API_KEY>
Body: {"path": "<campo>", "value": <valor parseado>}
```

Confirmar cada aplicacion o reportar errores individuales.

### 7. Resumen final

Al terminar todos los TODOs (o cuando el usuario indique que quiere parar), mostrar:

> **Completados X TODOs en Y drafts**
> Saltados: Z

## Mapeo de Paths a Nombres Legibles

Referencia para traducir paths tecnicos a nombres que entienda el usuario.

### Campos de nivel superior

| Path | Nombre legible |
|------|---------------|
| `multiplier` | Multiplicador del contrato |
| `minTick` | Tick minimo |
| `max_timePeriod` | Periodo maximo |
| `symbol` | Simbolo |
| `secType` | Tipo de instrumento |
| `exchange` | Exchange |
| `currency` | Moneda |

### Indicadores: `ind_list.TIMEFRAME[INDEX].params.PARAM`

Para resolver el nombre legible de un indicador, obtener el draft completo via:
```
GET /api/strategies/drafts/{strat_code}
```
Navegar `data.ind_list[TIMEFRAME][INDEX].params.indCode` para obtener el nombre del indicador.

| Param | Label |
|-------|-------|
| `timePeriod_1` | Periodo |
| `price_1` | Precio |
| `price_2` | Precio 2 |
| `price_3` | Precio 3 |
| `nbdevup` | Desviacion superior |
| `nbdevdn` | Desviacion inferior |
| `multiple` | Multiple |

Formato resultante: `"{indCode}: {label}"` (ej: "RSI_14_4H: Periodo").

### Control params: `control_params.CAMPO`

| Path | Nombre legible |
|------|---------------|
| `control_params.start_date` | Fecha inicio backtest |
| `control_params.end_date` | Fecha fin backtest |
| `control_params.timestamp` | Timestamp |
| `control_params.slippage_amount` | Slippage |
| `control_params.comm_per_contract` | Comision/contrato |
| `control_params.primary_timeframe` | Timeframe principal |

### Stop Loss / Take Profit

| Path pattern | Nombre legible |
|-------------|---------------|
| `stop_loss_init.indicator_params.multiple` | Stop Loss: Multiple |
| `take_profit_init.indicator_params.multiple` | Take Profit: Multiple |

### Fallback

Si el path no encaja en ningun patron, mostrar el path tal cual.

## Llamadas HTTP

Usar Bash con curl para las llamadas HTTP a la API local.

## Reglas

- Idioma: espanol (Espana). Tutear al usuario.
- Nunca inventar valores. Solo usar lo que el usuario proporciona.
- Los valores numericos se parsean como numero (int o float segun corresponda).
- Los valores de texto se envian como string.
- Si un PATCH falla, reportar el error y continuar con el siguiente TODO.
- Ser conversacional y claro: explicar que campo se esta rellenando y en que contexto.
- Si el usuario quiere parar antes de terminar, respetar y mostrar resumen parcial.

## Error Handling

- API no accesible: informar y terminar
- `.env` sin `DASHBOARD_API_KEY`: informar que falta la clave y terminar
- PATCH con error 4xx/5xx: reportar el campo y draft afectado, continuar con los demas
