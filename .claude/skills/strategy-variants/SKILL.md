---
name: strategy-variants
description: Purify extracted strategies (remove SL/TP), split long/short, and propose market/timeframe variants. Called by the research agent between notebooklm-analyst and strategy-translator. Use when processing raw strategy YAML into pure entry/exit variants.
---

# Strategy Variants

Takes raw strategies extracted by the notebooklm-analyst and prepares them for translation into IBKR JSON drafts. The goal is to produce a set of pure, focused strategy variants — each with a single direction, a single exit method, a specific market, and a specific timeframe.

The downstream translator only converts text to JSON. All creative decisions about what variants to produce happen here.

## Input

A YAML list from the notebooklm-analyst containing one or more strategies. Each strategy has:

- `name`, `description`, `source_channel`, `source_videos`
- `entry_rules` — concrete entry conditions
- `exit_rules` — exit conditions (may be empty)
- `risk_management` — SL/TP rules (to be removed)
- `parameters` — indicator parameters
- `recommended_markets` — markets the source says work well (optional)
- `recommended_timeframes` — timeframes the source recommends (optional)
- `avoid_timeframes` — timeframes the source says to avoid (optional)
- `avoid_markets` — markets the source says don't work (optional)
- `notes` — additional context

## Process

Apply these four steps to EACH strategy in the input, in order.

### Step 1: Purify

Strip the strategy down to pure entry/exit logic:

- Remove all `risk_management` rules (SL, TP, trailing stops, breakeven, position sizing)
- If SL/TP was mentioned, capture what was removed in the notes (e.g., `"removed_sl_tp": "ATR-based SL at 1.5x, TP at 3x"`) — this is useful context for when risk management is added manually later
- Keep only `entry_rules` and `exit_rules`

### Step 2: Separate directions

If the strategy has both long AND short entry rules, split it into two independent strategies:

- **Long-only**: keeps the long entry rules, discards short entry rules
- **Short-only**: keeps the short entry rules, discards long entry rules

Name them clearly: `"RSI_Exhaustion"` becomes `"RSI_Exhaustion_Long"` and `"RSI_Exhaustion_Short"`.

If the short rules are described as "mirror of long" or "opposite signal", invert the conditions explicitly. For example:
- Long: "RSI(14) < 30" → Short: "RSI(14) > 70"
- Long: "price makes lower low" → Short: "price makes higher high"

If the strategy is inherently one-directional (long-only or short-only), keep it as-is.

### Step 3: Propose exit method

Each variant needs exactly ONE exit method. Every variant must be backtestable — it must have a way to close the position.

1. **Stop & Reverse** (only for bidirectional strategies): if the strategy has BOTH long and short conditions AND they are kept together (not split), SAR works because the opposite signal closes the current position. **SAR is NOT valid for unidirectional variants** (long-only or short-only) because there is no opposite signal to trigger the exit.
2. **Source specifies a concrete exit**: use it as-is (e.g., "exit after 20 bars", "RSI > 90")
3. **No valid exit or unidirectional SAR**: use `num_bars` exit with `_TODO` as the value and note that exit needs to be determined during backtesting

In practice, since Step 2 splits long/short into separate strategies, SAR is rarely valid. Most variants will need either a concrete exit condition or `num_bars`.

### Step 4: Propose variants

Combine the purified, direction-split strategies with market and timeframe options from the analyst data:

- Use `recommended_markets` to propose market variants. If a market is a futures contract, use the standard symbol (e.g., GF for Feeder Cattle, OJ for Orange Juice, ES for E-mini S&P)
- Use `recommended_timeframes` to propose timeframe variants
- Exclude any market in `avoid_markets` or timeframe in `avoid_timeframes`
- If no markets or timeframes are recommended, use `_TODO`

**Variant budget**: maximum 5 variants per original strategy (the long/short split counts toward this limit). Prioritize:
1. Markets explicitly mentioned as performing well
2. Timeframes explicitly recommended
3. Cross-combinations only if the budget allows

## Output Format

Return a YAML list. Each entry is a self-contained variant ready for the translator:

```yaml
- variant_name: "RSI_Exhaustion_Long_SAR_4h_GF"
  parent_strategy: "Hidden RSI Exhaustion Point Entry"
  direction: "long"
  symbol: "GF"
  timeframe: "4 hours"
  entry_rules:
    - "Price makes a lower low: LOW(1) < LOW(2)"
    - "RSI(14) makes a higher low: RSI(1) > RSI(2)"
    - "RSI(2) < 70"
  exit_rules:
    - "Stop & Reverse: opposite signal closes position"
  indicators_needed:
    - "PRICE: low, period 1"
    - "RSI: close, period 14"
  notes:
    source: "Kevin Davey - AI-Generated Trading Strategies"
    exit_method: "Stop & Reverse as described in source"
    removed_sl_tp: "No SL/TP in source (stop & reverse only)"
    market_rationale: "Feeder Cattle recommended by author"
```

### Naming convention

`<Indicator>_<Logic>_<Direction>_<Exit>_<Timeframe>_<Market>`

- Direction: `Long` or `Short` (omit if strategy is inherently both)
- Exit: `SAR` (stop & reverse), `TE20` (time exit 20 bars), `RSIexit` (specific condition)
- Timeframe: `4h`, `8h`, `1D`, `360m`
- Market: symbol like `GF`, `OJ`, `ES` (omit if `_TODO`)

Examples:
- `RSI_Exhaustion_Long_SAR_4h_GF`
- `VWAP_Reversal_Short_TE20_8h`
- `Shakeout_Long_SAR_1D_OJ`

## Rules

- Every variant must be pure: entry + exit only, no SL/TP
- Every variant must have exactly one direction (long or short), unless the strategy is inherently directionless
- Every variant must have exactly one exit method
- The `indicators_needed` field helps the translator know what to put in `ind_list` — derive it from the entry and exit rules
- If the source material is vague about a parameter, keep `_TODO` — do not invent values
- The notes should explain WHY each variant was proposed (market rationale, exit choice, what was removed)
