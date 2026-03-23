# Conversacion NotebookLM: AI Algo Trading Entries - Kevin Davey
Fecha: 2026-03-23
Notebook ID: 8d8528fa-2dd7-4668-969d-7f030743ab33
Videos analizados: https://www.youtube.com/watch?v=wSYycTYCMFw

---

## Conversation Summary (10 rounds)

| # | Question | Topic |
|---|----------|-------|
| 1 | List ALL the distinct trading strategies | Discovery - identified 10 items |
| 2 | Volume Weighted Reversal rules extraction | VWAP > Previous Close logic |
| 3 | Shakeout Fake Out Entry rules extraction | Low == Lowest Low logic |
| 4 | Market Maker Stop Hunt rules extraction | Same as Shakeout (confirmed identical) |
| 5 | Hidden RSI Exhaustion Point Entry rules | Price lower low + RSI higher low divergence |
| 6 | RSI Exhaustion clarification on bar comparisons | Multi-bar structural pattern, not simple 1-bar |
| 7 | Volume Imbalance Reversal rules extraction | Vol > 2x Avg + small body < 0.2x ATR |
| 8 | Context extraction for all strategies | Markets (44 futures), timeframes, performance |
| 9 | RSI Exhaustion exact bar logic clarification | Confirmed multi-bar, tested thresholds 50-90 |
| 10 | VWAP Reversal ATR role clarification | ATR is entry filter/parameter, not SL |

## Key Findings

### Strategies Extracted (4 actionable)
1. **VWAP Reversal** - VWAP vs previous close, 37/44 markets
2. **Shakeout Stop Hunt** - Low == Lowest Low of N bars, 33/44 markets
3. **Hidden RSI Exhaustion** - Price/RSI divergence, 28/44 markets
4. **Volume Imbalance Reversal** - High vol + small body, 40/44 markets (best)

### Non-Actionable Items (skipped)
- Strategy Factory (meta-process)
- Stop and Reverse (exit method, not strategy)
- Exit After 20 Bars (exit method)
- Moving Average Crossover (mentioned as frequently failing)
- Limited Feasibility Testing (testing step)

### Market/Timeframe Notes
- Tested on 44 futures markets, 2019-2024 period
- Best timeframes: 240-360 minutes
- Avoid: 30min for most, 60min for VWAP Reversal time exit
- All exits tested as SAR or 20-bar time exit
