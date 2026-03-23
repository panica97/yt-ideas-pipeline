# Conversacion NotebookLM: Single Video Research
Fecha: 2026-03-23
Notebook ID: 601e738f-8304-4428-b8db-bbdaff464c01
Videos analizados: https://www.youtube.com/watch?v=wSYycTYCMFw
Video Title: These AI Influenced Algo Trading Entries Actually Work - Supported By Thorough Test Data!
Channel: Kevin Davey

---

## Round 1: Discovery

**Q:** List ALL the distinct trading strategies, entry methods, or trading systems mentioned in these sources.

**A:** 4 concrete strategies + 1 process framework identified:

1. **Volume Weighted Reversal** - Uses VWAP logic, simplified to Close > Previous Close for long, Close < Previous Close for short.
2. **Shakeout Fake Out / Market Maker Stop Hunt** - Uses lookback length to identify when Low = Lowest Low (buy) or High = Highest High (sell short). Theory: market makers run stops before reversal.
3. **Hidden RSI Exhaustion Point Entry** - RSI divergence: RSI makes higher low while price makes lower low (long). Mirror for short.
4. **Volume Imbalance Reversal** - Detects large players via bars with high volume (> 2x average) but narrow range (|Close-Open| < 0.2*ATR).
5. **The Strategy Factory** - Development process, not a strategy (skipped).

Exit methods: Stop and Reverse (SAR, always in market) and Timed Exit (close after 20 bars).

## Round 2: Rules Extraction

### Volume Weighted Reversal
- **Long:** Close(current bar) > Close(previous bar)
- **Short:** Mirror - Close(current) < Close(previous)
- **Exit SAR:** Always in market, opposite signal closes
- **Exit TE:** Close after 20 bars
- **Indicators:** VWAP (conceptual), ATR (length optimized across 7 iterations)
- **Note:** ATR role unclear from source. Entry was simplified from original VWAP/ATR AI code that didn't generate trades.

### Shakeout Fake Out
- **Long:** Low == Lowest Low of N bars (buy, expecting reversal)
- **Short:** High == Highest High of N bars (sell short)
- **Exit SAR:** Opposite signal
- **Exit TE:** 20 bars
- **Indicators:** Lowest Low / Highest High with lookback length
- **Lookback optimized:** 9 values (5,10,15,20,25,30,35,40,45)
- **Note:** Code checks Low == Lowest Low (not <) because if lowest low includes current bar, < is impossible.

### Hidden RSI Exhaustion
- **Long:** Price lower low + RSI higher low + RSI below threshold
- **Short:** Mirror - Price higher high + RSI lower high + RSI above threshold
- **Exit SAR/TE:** Same as above
- **Indicators:** RSI (period unclear, likely 14). Threshold optimized: 50,60,70,80,90
- **Note:** The two lows/highs being compared are sequential in a divergence pattern. Exact bar distance not specified.

### Volume Imbalance Reversal
- **Conditions:** Volume > 2x Average Volume AND |Close - Open| < 0.2 * ATR
- **Direction:** Original AI code was directionless (abs value). Davey added symmetric long/short logic but exact directional filter NOT specified in transcript.
- **Indicators:** Volume, Average Volume (length optimized, 9 values), ATR
- **Exit:** SAR or TE20

## Round 3: Context Extraction

### Markets
- Tested on 44 futures markets
- Mentioned: ES, Euro currency, Crude Oil, Heating Oil, Coffee, Wheat, Soybeans, Rough Rice (slippage warning), Feeder Cattle, Live Cattle, OJ
- "Don't work everywhere" - few entries work regardless of market/bar size

### Markets Passed (backtesting)
- Volume Imbalance Reversal: 40 markets (best)
- Volume Weighted Reversal: 37 markets
- Shakeout Fake Out: 33 markets
- Hidden RSI Exhaustion: 28 markets

### Timeframes
- Tested: 1440 (daily), 720, 360, 240, 180, 120, 60, 30 minutes
- Sweet spot: 240-360 minutes
- Shakeout best at 360m
- Volume Imbalance best at 360m
- Avoid 30 min (especially for RSI Exhaustion)
- 30-60 min didn't work for VWAP Reversal Version 2 (TE20)

### Robustness
- Small optimization iterations (5-9 values) to avoid overfitting
- AI failure rate lower than author's manual entry picks
- All 4 entries passed initial robustness tests
- All symmetric long/short
