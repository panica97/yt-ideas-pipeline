---
name: notebooklm-analyst
description: Analyze YouTube videos with NotebookLM and extract all trading strategies as structured YAML with concrete entry/exit rules, recommended markets, and timeframe guidance
---

# NotebookLM Analyst

Uses NotebookLM to analyze YouTube videos and extract ALL possible trading strategies with enough detail for downstream translation into IBKR JSON drafts.

The downstream translator needs concrete, actionable rules — not summaries. Every strategy extracted here will be converted into trading engine conditions with specific indicators, comparisons, and thresholds. Vague descriptions like "uses RSI divergence" are not useful; the translator needs "buy when RSI(14) makes a higher low while price makes a lower low, with RSI below 70".

## Workflow

1. Create a notebook for the research topic
2. Add videos as sources (YouTube URLs)
3. Wait for sources to be processed
4. Ask the discovery question to identify ALL distinct strategies
5. For EACH strategy, run the extraction sequence (3 rounds of questions)
6. Structure strategies in YAML format
7. Return extracted strategies (cleanup is the orchestrator's responsibility)

## Tools

```bash
notebooklm create "Title" --json        # Create notebook (returns ID)
notebooklm source add "<url>" -n <id>   # Add source
notebooklm source wait <src_id> -n <id> # Wait for processing
notebooklm ask "<question>" -n <id>     # Query the notebook
```

## Rules

- Create ONE notebook for the entire analysis session
- Add ALL videos as sources and wait for them to be processed
- Use the `-n <notebook_id>` flag in all commands to avoid context issues
- Do NOT delete the notebook — cleanup is the orchestrator's responsibility

## Extraction Sequence

### Round 1: Discovery

Ask ONE broad question to map all strategies in the sources:

> "List ALL the distinct trading strategies, entry methods, or trading systems mentioned in these sources. For each one, give: (1) a short name, (2) which video/source it comes from, (3) a one-sentence summary of the core idea."

This gives you the list of strategies to extract individually.

### Round 2: Rules extraction (per strategy)

For EACH strategy identified in Round 1, ask this question:

> "For the strategy [NAME], give me the EXACT trading rules as if I needed to program them. I need:
> 1. ENTRY rules for LONG: what conditions must ALL be true to buy? Use specific indicators, thresholds, and comparisons (e.g., 'RSI(14) < 30' not just 'RSI is low')
> 2. ENTRY rules for SHORT: what conditions must ALL be true to sell short? (or say 'mirror of long' if it's symmetric)
> 3. EXIT rules: how does the position close? (e.g., opposite signal, after N bars, specific condition)
> 4. What INDICATORS are used? List each with its parameters (period, price source, etc.)
> 5. Are there any CONDITIONS that compare the CURRENT bar to a PREVIOUS bar? (e.g., 'current low is lower than previous low'). Be specific about which bars are compared."

The goal of question 5 is to surface temporal comparisons (shifts) that are easy to miss. Divergence patterns, crossovers, and "higher high / lower low" conditions all involve comparing values across bars.

### Round 3: Context extraction (per strategy)

For EACH strategy, ask this follow-up:

> "For the strategy [NAME]:
> 1. What MARKETS or asset classes does the author say it works on? (futures, forex, commodities, specific symbols like Feeder Cattle)
> 2. What MARKETS or conditions does the author say it does NOT work on or should be avoided?
> 3. What TIMEFRAMES does the author recommend? (e.g., daily, 4-hour, 360 minutes)
> 4. What TIMEFRAMES does the author say to AVOID? (e.g., 'does not work on 30-minute bars')
> 5. Any other relevant context: parameter optimization ranges, robustness notes, backtesting results mentioned?"

### Follow-up: Clarification

If any answer from Round 2 is vague (e.g., "uses momentum", "based on volume analysis"), ask a targeted follow-up:

> "You said [STRATEGY] uses [VAGUE CONCEPT]. Can you be more specific? What exact indicator, what threshold, what comparison? For example, is it 'volume > 2x average volume' or something else?"

Keep pushing until you get a concrete rule or confirm the source doesn't provide more detail. If the source genuinely doesn't specify, note it — the translator will mark it as `_TODO`.

## Output Format

```yaml
- name: "<strategy name>"
  description: "<1-2 sentence description>"
  source_channel: "<channel name>"
  source_videos:
    - "<video title>"
  parameters:
    - name: "<param_name>"
      description: "<what it controls>"
      type: "<int|float|string>"
      default: <value>
      range: [<min>, <max>]
  entry_rules:
    - "<concrete rule with indicator, threshold, comparison>"
  exit_rules:
    - "<concrete exit condition>"
  risk_management:
    - "<rule if mentioned, otherwise omit this field>"
  recommended_markets:
    - "<market or asset class>"
  recommended_timeframes:
    - "<timeframe>"
  avoid_timeframes:
    - "<timeframe to avoid>"
  avoid_markets:
    - "<market to avoid>"
  notes:
    - "<additional context, optimization ranges, robustness notes>"
```

Fields `recommended_markets`, `recommended_timeframes`, `avoid_timeframes`, `avoid_markets`, and `risk_management` are optional — only include them if the source material mentions them. Do not invent markets or timeframes that the source doesn't discuss.

If no strategies are found, return exactly: `NO_STRATEGIES_FOUND`

## Source Limits

Maximum sources per notebook depends on NotebookLM plan: Standard 50, Plus 100, Pro 300, Ultra 600. Keep video batches well under the limit to avoid errors.

## Error Handling

- `notebooklm create` fails: report authentication/connection error, do not continue
- Sources fail to process: retry once, then report and continue with those that did process
- No strategies found: return `NO_STRATEGIES_FOUND`
- Note: Notebook cleanup is handled by the orchestrator (AGENT.md), not by this skill
