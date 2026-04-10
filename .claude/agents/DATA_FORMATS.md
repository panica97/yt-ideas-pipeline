# Data Formats

Reference document for the data types passed between agents. These formats already exist in the codebase -- agents must conform to them, not invent new ones.

## Video

The output of the yt-scraper skill. A list of YouTube video URLs with metadata.

- **Produced by:** Video Discovery agent (via yt-scraper skill)
- **Consumed by:** Strategy Extractor agent
- **Format:** List of YouTube URLs (one per line), plus metadata from yt-dlp
- **Defined in:** `.claude/skills/yt-scraper/SKILL.md` (Output Format section)
- **Tool:** `python -m tools.youtube.fetch_topic --db data/channels/channels.yaml <topic>`

Each video has at minimum: URL, video_id, title, channel name.

## Strategy (Raw YAML)

The output of the notebooklm-analyst skill. Structured YAML with extracted trading strategies.

- **Produced by:** Strategy Extractor agent (via notebooklm-analyst skill)
- **Consumed by:** Strategy Processor agent (via strategy-variants skill)
- **Format:** YAML list of strategy objects
- **Defined in:** `.claude/skills/notebooklm-analyst/SKILL.md` (Output Format section)
- **Example in codebase:** `data/strategies/strategies.yaml`

Key fields per strategy:
```yaml
- name: "Strategy Name"
  description: "..."
  source_channel: "Channel Name"
  source_videos: ["video title"]
  parameters: [{name, description, type, default, range}]
  entry_rules: ["concrete rule with indicator and threshold"]
  exit_rules: ["concrete exit condition"]
  risk_management: ["rule if mentioned"]        # optional
  recommended_markets: ["market"]               # optional
  recommended_timeframes: ["timeframe"]         # optional
  avoid_timeframes: ["timeframe"]               # optional
  avoid_markets: ["market"]                     # optional
  notes: ["additional context"]                 # optional
```

## Variant (Intermediate YAML)

The output of the strategy-variants skill. Purified, direction-split, market-specific variants ready for translation.

- **Produced by:** Strategy Processor agent (via strategy-variants skill)
- **Consumed by:** Strategy Processor agent (via strategy-translator skill)
- **Format:** YAML list of variant objects
- **Defined in:** `.claude/skills/strategy-variants/SKILL.md` (output section)

Key fields per variant:
```yaml
- variant_name: "Strategy_Long_ES_1D"
  parent_strategy: "Strategy Name"
  direction: long | short
  symbol: "ES"
  timeframe: "1 day"
  entry_rules: ["purified entry conditions"]
  exit_rules: ["single exit method"]
  indicators_needed: [{indicator, params}]
  notes: {source_channel, removed_sl_tp, rationale}
```

## Draft (IBKR JSON)

The output of the strategy-translator skill. A complete JSON file ready for the IBKR trading engine.

- **Produced by:** Strategy Processor agent (via strategy-translator skill)
- **Consumed by:** DB Persistence agent, Backtesting agents
- **Format:** JSON file conforming to the strategy schema
- **Defined in:** `.claude/skills/strategy-translator/SKILL.md` (Translation Process section)
- **Schema:** `.claude/skills/strategy-translator/schema.json`
- **Field reference:** `docs/STRATEGY_FILE_REFERENCE.md`
- **Examples:** `.claude/skills/strategy-translator/examples/*.json`
- **Stored in DB:** via `tools.db.draft_repo.upsert_draft()`
- **Local examples:** `data/strategies/drafts/*.json`

Key top-level fields: `strat_code`, `strat_name`, `symbol`, `secType`, `exchange`, `ind_list`, `long_conds`, `short_conds`, `exit_conds`.

## Backtesting Results

Backtesting agents produce structured results from the API. These formats are defined by the backend API response payloads.

- **Metrics{}** -- 40+ performance metrics from simple/complete backtests (defined by API response)
- **Trade[]** -- Individual trade records from complete backtests (defined by API response)
- **MCResult{}** -- Monte Carlo simulation results with confidence intervals (defined by API response)
- **MonkeyResult{}** -- Random entry benchmark with p-value (defined by API response)
- **StressResult{}** -- Parameter sweep robustness analysis (defined by API response)

These formats will be documented in detail when backtesting agents are fully designed (Phase 6).
