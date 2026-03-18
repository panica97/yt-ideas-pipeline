# Backtest Local - Documentacion

Modulo de backtesting local para IRT. Proporciona scripts independientes que el agente de backtest (o el usuario directamente) puede invocar para validar y ejecutar backtests usando el motor incluido en el worker de Operations-Platform.

## Que hace

1. Valida las estrategias draft generadas por IRT (codigos 9001+)
2. Invoca el backtest-engine como subproceso usando el entorno del worker
3. Lanza stress tests y simulaciones Monte Carlo para medir robustez
4. Parsea los resultados y los devuelve al agente o los muestra por consola

## Modelo de ejecucion

Los scripts son invocados por un **agente de backtest** (orquestador manual) mediante skills, siguiendo el mismo patron que el agente de research con yt-scraper, notebooklm-analyst, etc. El usuario decide que paso ejecutar y cuando — el agente simplemente ejecuta los scripts cuando se le pide.

El usuario tambien puede ejecutar los scripts directamente desde la terminal si lo prefiere.

## Documentacion

- [Arquitectura](arquitectura.md) - Como se integra el worker con IRT
- [Esquema de estrategia](esquema-estrategia.md) - Formato JSON que espera el motor
- [Datos historicos](datos-historicos.md) - Configuracion de datos de mercado
- [Propuesta de scripts](cli-propuesta.md) - Estructura de scripts y uso propuesto

## Estado

En fase de diseno. Los scripts aun no estan implementados.
