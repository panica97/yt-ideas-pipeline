# Translation Rules

Reglas de mapeo aprendidas para traducir estrategias de lenguaje natural a JSON del motor de trading.
Estas reglas se acumulan con el feedback del usuario.

**Fuente de verdad**: `docs/STRATEGY_FILE_REFERENCE.md` — especificacion completa del motor IBKR. Leer SIEMPRE antes de generar drafts.

## Reglas de filtrado (skip)

- **Ideas sin logica concreta de entrada/salida** → skip (log como "too vague for translation")
  No se puede generar JSON si no hay condiciones claras de cuando entrar o salir.

- **Enfoques historicos o abandonados** → skip
  Si el video menciona que ya no usa esa estrategia o que era de hace anos, no traducir.

- **Meta-estrategias** → skip
  Gestion de portfolio, scaling de prop firms, psicologia de trading, money management generico.
  Solo traducir estrategias con reglas de entrada/salida accionables.

## Reglas de traduccion

- **Ante la duda sobre un valor de parametro** → usar `"_TODO"`, nunca inventar.
  Es mejor un draft incompleto que uno con valores inventados.

- **Preferir 2-4 variantes sobre 1 estrategia perfecta.**
  Explorar combinaciones de timeframe y metodo de salida.

- **Solo estrategias puras: entrada + salida. Sin SL/TP ni gestion de riesgo.**
  El translator genera SOLO la logica core: indicadores para condiciones, condiciones de entrada y condiciones de salida.
  `stop_loss_init`, `take_profit_init` y `stop_loss_mgmt` quedan en sus valores por defecto (todo `false`, params vacios).
  No crear indicadores dedicados a SL/TP (como ATR_SL, ATR_TP). La gestion de riesgo se anade manualmente despues.

- **Cada variante debe tener un `strat_name` descriptivo** que incluya la variacion.
  Formato sugerido: `"<Indicador>_<Logica>_<Exit>_<Timeframe>"`.
  Ejemplos: `"RSI_Divergence_SAR_360m"`, `"RSI_Divergence_TimeExit_240m"`, `"VWAP_Bounce_ATR_Daily"`.

## Reglas de mapeo (feedback del usuario)

- **El campo `cond` debe usar nombres de indicador bare (sin notacion de shift).**
  **Origen**: El translator genero `"LOW_6H(0) < LOW_6H(1)"` con shift notation dentro del cond string. Esto rompe el parser del engine que usa cond.split() para buscar columnas en el DataFrame.
  **Ejemplo correcto**: `"LOW_6H < LOW_6H"` con `"shift_1": 1, "shift_2": 2` — los shifts van en campos separados, no en el string.

- **NO usar `group` en `long_conds` ni `short_conds`.**
  **Origen**: El translator puso `"group": 1` en las tres entry conditions de una divergencia RSI. Las entry conditions son SIEMPRE ALL AND, los groups solo aplican a `exit_conds`.
  **Ejemplo**: `{"cond_type": "price_relation", "cond": "...", "group": 1}` → quitar `"group"`

- **Shift values deben ser >= 1, nunca 0.**
  **Origen**: Shift 0 no existe en el motor — la barra actual aun no se ha formado. El minimo es shift 1 (ultima barra completada).
  **Ejemplo**: `"shift_1": 0` → `"shift_1": 1`

- **Indicadores multi-output deben usar indCode con prefijo `MULT_`.**
  **Origen**: Documentacion del motor (`docs/STRATEGY_FILE_REFERENCE.md`).
  **Ejemplo**: BBANDS con `"indCode": "BB_20_2_1D"` → `"indCode": "MULT_1D"` (genera BBAND_upperband_1D, etc.)
