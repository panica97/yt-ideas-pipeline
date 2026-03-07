# Research Quant Agent

Orquesta el pipeline de investigación: YouTube → NotebookLM → Estrategia → Backtest.

## Sub-agentes

- `youtube_scraper/` — Busca y descarga vídeos de canales monitoreados
- `notebooklm/` — Extrae estrategias de los vídeos usando NotebookLM
- `db_manager/` — Gestiona las bases de datos de canales y estrategias
- `backtester/` — Prepara y ejecuta backtests en Strategy Quant
