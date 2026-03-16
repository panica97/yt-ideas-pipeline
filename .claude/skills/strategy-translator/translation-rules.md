# Translation Rules

Reglas de mapeo aprendidas para traducir estrategias de lenguaje natural a JSON del motor de trading.
Estas reglas se acumulan con el feedback del usuario.

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
  Explorar combinaciones de timeframe, metodo de salida y filtros.

- **Cada variante debe tener un `strat_name` descriptivo** que incluya la variacion.
  Formato sugerido: `"<Indicador>_<Logica>_<Exit>_<Timeframe>"`.
  Ejemplos: `"RSI_Divergence_SAR_360m"`, `"RSI_Divergence_TimeExit_240m"`, `"VWAP_Bounce_ATR_Daily"`.

## Reglas de mapeo (feedback del usuario)

<!-- Se iran anadiendo reglas aqui a medida que el usuario corrija propuestas -->
<!-- Formato: -->
<!-- - **Regla**: descripcion clara -->
<!--   **Origen**: que correccion del usuario la genero -->
<!--   **Ejemplo**: antes → despues -->
