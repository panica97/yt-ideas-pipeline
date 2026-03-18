# Esquema de Estrategia JSON

Formato completo que espera el backtest-engine. Los drafts generados por IRT (codigos 9001+) siguen este esquema, aunque pueden tener campos con marcadores `_TODO` que requieren revision manual.

## Estructura general

```json
{
  "strat_code": 9001,
  "strat_name": "Nombre de la estrategia",
  "active": true,
  "tested": false,
  "prod": false,

  "symbol": "MES",
  "secType": "FUT",
  "exchange": "CME",
  "currency": "USD",
  "multiplier": 5,
  "minTick": 0.25,
  "rolling_days": 5,

  "process_freq": "1H",
  "UTC_tz": "US/Eastern",
  "trading_hours": { "start": "09:30", "end": "16:00" },

  "ind_list": { ... },
  "long_conds": [ ... ],
  "short_conds": [ ... ],
  "exit_conds": [ ... ],

  "max_shift": 5,
  "max_timePeriod": 20,

  "stop_loss_init": { ... },
  "take_profit_init": { ... },
  "stop_loss_mgmt": { ... },

  "order_params": { ... },
  "control_params": { ... }
}
```

## Campos de identificacion

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `strat_code` | int | Codigo unico. Drafts de IRT usan 9001+ |
| `strat_name` | string | Nombre descriptivo |
| `active` | bool | Si la estrategia esta activa |
| `tested` | bool | Si ha sido validada con backtest |
| `prod` | bool | Si esta en produccion |

## Instrumento

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `symbol` | string | Simbolo del futuro (MES, MNQ, ES, NQ, GC, MGC) |
| `secType` | string | Tipo de contrato (`FUT`) |
| `exchange` | string | Exchange (CME, COMEX) |
| `currency` | string | Divisa (`USD`) |
| `multiplier` | float | Multiplicador del contrato |
| `minTick` | float | Tick minimo del instrumento |
| `rolling_days` | int | Dias antes del vencimiento para hacer roll |

## Temporalidad

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `process_freq` | string | Frecuencia de procesado (1H, 4H, 8H, 1D, 1W) |
| `UTC_tz` | string | Zona horaria |
| `trading_hours` | object | Horario de trading con `start` y `end` (HH:MM) |

## Indicadores (`ind_list`)

Agrupados por timeframe. Cada indicador tiene nombre, parametros y opcionalmente un campo `custom`.

```json
{
  "ind_list": {
    "1H": [
      {
        "name": "EMA",
        "params": { "timePeriod": 20, "source": "close" }
      },
      {
        "name": "ATR",
        "params": { "timePeriod": 14 }
      },
      {
        "name": "CustomIndicator",
        "params": { "timePeriod": 10 },
        "custom": true
      }
    ],
    "1D": [
      {
        "name": "SMA",
        "params": { "timePeriod": 200, "source": "close" }
      }
    ]
  }
}
```

- La clave de primer nivel es el timeframe (`1H`, `4H`, `1D`, etc.).
- `name`: nombre del indicador tal como lo reconoce ibkr-core.
- `params`: parametros especificos del indicador.
- `custom`: si es `true`, indica un indicador personalizado definido en ibkr-core.

## Condiciones de entrada y salida

Las condiciones se definen en tres listas: `long_conds`, `short_conds` y `exit_conds`. Cada condicion tiene esta estructura:

```json
{
  "cond_type": "indicator",
  "cond": "EMA_20_1H > SMA_200_1D",
  "condCode": "ema20_above_sma200",
  "shift_1": 0,
  "shift_2": 0,
  "group": 1,
  "mode": "all"
}
```

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `cond_type` | string | Tipo de condicion (`indicator`, `price`, `time`, `custom`) |
| `cond` | string | Expresion de la condicion |
| `condCode` | string | Codigo unico de la condicion |
| `shift_1` | int | Desplazamiento temporal del primer operando (0 = vela actual) |
| `shift_2` | int | Desplazamiento temporal del segundo operando |
| `group` | int | Grupo logico (condiciones del mismo grupo se evaluan con AND) |
| `mode` | string | `all` (todas las del grupo) o `any` (alguna del grupo) |

## Shifts maximos

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `max_shift` | int | Mayor shift usado en las condiciones |
| `max_timePeriod` | int | Mayor timePeriod de los indicadores |

Estos valores los usa el motor para saber cuantas velas necesita cargar antes de empezar a operar.

## Stop Loss y Take Profit iniciales

### Basado en indicador

```json
{
  "stop_loss_init": {
    "type": "indicator",
    "indicator": "ATR",
    "timeframe": "1H",
    "multiple": 2.0
  }
}
```

### Basado en pips

```json
{
  "stop_loss_init": {
    "type": "pips",
    "value": 20
  }
}
```

### Basado en porcentaje

```json
{
  "take_profit_init": {
    "type": "percent",
    "value": 0.02
  }
}
```

## Gestion del Stop Loss (`stop_loss_mgmt`)

```json
{
  "stop_loss_mgmt": {
    "breakeven": {
      "enabled": true,
      "trigger": 1.0,
      "offset": 0.1
    },
    "trailing": {
      "enabled": true,
      "type": "indicator",
      "indicator": "ATR",
      "timeframe": "1H",
      "multiple": 1.5
    }
  }
}
```

- **breakeven**: Mueve el SL a breakeven cuando el precio alcanza `trigger` x ATR de beneficio. `offset` anade un colchon.
- **trailing**: Trailing stop que se actualiza en cada vela. Puede ser por indicador, pips o porcentaje.

## Parametros de orden (`order_params`)

```json
{
  "order_params": {
    "max_rpo": 0.02,
    "min_volume": 1000
  }
}
```

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `max_rpo` | float | Riesgo maximo por operacion (fraccion del equity) |
| `min_volume` | int | Volumen minimo requerido para entrar |

## Parametros de control (`control_params`)

```json
{
  "control_params": {
    "min_win_rate": 0.45,
    "min_sharpe": 1.0,
    "max_drawdown": 0.15,
    "min_trades": 30
  }
}
```

Estos parametros no afectan la ejecucion del backtest, pero sirven como umbrales de validacion post-backtest.

## Marcadores _TODO en drafts de IRT

Los drafts generados por el strategy-translator (codigos 9001+) pueden contener campos con el sufijo `_TODO` cuando el traductor no pudo resolver el valor automaticamente:

```json
{
  "stop_loss_init_TODO": "El video menciona 'stop ajustado' pero no da valor concreto",
  "trading_hours_TODO": "No se especifica horario de trading"
}
```

Estos campos deben resolverse manualmente antes de lanzar el backtest. El motor fallara si encuentra campos requeridos sin valor.
