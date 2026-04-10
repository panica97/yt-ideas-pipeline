# Research Pipeline Documentation

Complete reference for the IRT (Ideas Research Team) research pipeline. This document covers every step from raw YouTube video discovery to persisted strategy drafts in the database.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Entry Points](#2-entry-points)
3. [Pipeline Steps (Detailed)](#3-pipeline-steps-detailed)
4. [Data Flow](#4-data-flow)
5. [Database Schema](#5-database-schema)
6. [Strategy JSON Format](#6-strategy-json-format)
7. [Session Tracking](#7-session-tracking)
8. [Frontend Integration](#8-frontend-integration)
9. [YouTube Channel Database](#9-youtube-channel-database)
10. [Configuration](#10-configuration)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Overview

### What is the Research Pipeline

The research pipeline is an automated system that discovers, extracts, and structures trading strategies from YouTube videos. It monitors curated YouTube channels, uses AI (Google NotebookLM) to analyze video content, extracts concrete trading rules, translates them into machine-readable JSON formats compatible with the IBKR trading engine, and stores everything in a PostgreSQL database.

### What Problem It Solves

Trading strategy research is labor-intensive. Traders spend hours watching YouTube videos, manually noting entry/exit rules, and translating vague descriptions into actionable trading logic. This pipeline automates the entire workflow:

- **Discovery**: Finds new videos from monitored channels by topic
- **Filtering**: Classifies videos to skip irrelevant content (setup tours, vlogs, Q&As)
- **Extraction**: Uses NotebookLM to analyze video content and extract precise trading rules
- **Structuring**: Splits strategies by direction (long/short), proposes market/timeframe variants
- **Translation**: Converts human-readable rules into IBKR trading engine JSON format
- **Persistence**: Stores strategies and drafts in PostgreSQL with deduplication

### High-Level Architecture

```
                           IRT Research Pipeline
  ================================================================

  User Input                Pipeline Engine              Storage
  ----------                ---------------              -------

  research <topic>     -->  [0] Preflight Check     -->  NotebookLM Auth
        |                        |
        |                   [1] YouTube Scraper      <-- channels.yaml / DB
        |                        |
        |                   [1.5] Video Classifier       (inline, no API)
        |                        |
        |                   [2] NotebookLM Analyst   <-> NotebookLM API
        |                        |
        |                   [3] Strategy Variants        (inline processing)
        |                        |
        |                   [4] Strategy Translator  -->  drafts DB
        |                        |
        |                   [4.5] TODO Auto-Resolution <-> Instruments API
        |                        |
        |                   [5] Cleanup & History    -->  research_history DB
        |                        |
        v                   [6] DB Manager           -->  strategies + drafts DB
                                 |
                            [7] Summary              -->  research_sessions DB

  ================================================================

  Frontend Dashboard (React)
  --------------------------
  History Page       <-- GET /api/research/sessions
  Strategies Page    <-- GET /api/strategies
  Live Status        <-- WebSocket /api/research/status
```

### Key Components

| Component | Location | Role |
|-----------|----------|------|
| Research Manager | `.claude/agents/research-manager/AGENT.md` | Main orchestrator, executes full pipeline |
| CEO Routing | `CLAUDE.md` (routing rules) | Intent detection routes to Research Manager |
| yt-scraper | `.claude/skills/yt-scraper/SKILL.md` | YouTube video fetching |
| video-classifier | `.claude/skills/video-classifier/SKILL.md` | Title-based filtering |
| notebooklm-analyst | `.claude/skills/notebooklm-analyst/SKILL.md` | Strategy extraction via AI |
| strategy-variants | `.claude/skills/strategy-variants/SKILL.md` | Purification and variant generation |
| strategy-translator | `.claude/skills/strategy-translator/SKILL.md` | JSON draft translation |
| todo-review | `.claude/skills/todo-review/SKILL.md` | Auto-fill _TODO fields in drafts |
| db-manager | `.claude/skills/db-manager/SKILL.md` | Database persistence |
| FastAPI Backend | `api/` | REST API + WebSocket for frontend |
| React Frontend | `frontend/` | Dashboard for viewing results |

---

## 2. Entry Points

The pipeline supports three entry points, each skipping different steps depending on the input type.

### 2.1 Topic-Based Research (topic input)

**Example**: "research futures" (CEO routes to Research Manager)

Runs the full pipeline. The topic slug must exist in the channel database (`data/channels/channels.yaml` or the `topics` table in PostgreSQL).

**Steps executed**: 0, 1, 1.5, 2, 3, 4, 4.5, 5, 6, 7

**Session label**: Uses `topic_slug` directly (e.g., `topic_id` is resolved from the slug).

### 2.2 Video URL Research (URL input)

**Example**: "research https://www.youtube.com/watch?v=abc123" (CEO routes to Research Manager)

Skips YouTube scraping and video classification. Goes directly to NotebookLM analysis with the single video URL.

**Steps executed**: 0, 2, 3, 4, 4.5, 5, 6, 7 (Steps 1 and 1.5 skipped)

**Metadata extraction**: Uses `yt-dlp --print title --print channel --print channel_url <url>` to get video title and channel info.

**Session label**: `"Video: <video_title or video_url>"`

**History recording**: `topic_id=None`, `channel_id` is resolved if the channel exists in the DB, otherwise `None`.

### 2.3 Raw Idea Research (idea input)

**Example**: "research Buy when RSI(14) < 30 and price is above 200 SMA, exit after 20 bars" (CEO routes to Research Manager)

Skips YouTube scraping, video classification, AND NotebookLM analysis. The idea text is formatted as a strategy YAML and passed directly to the strategy-variants step.

**Steps executed**: 0, 3, 4, 4.5, 6, 7 (Steps 1, 1.5, 2, and 5 skipped)

**Session label**: `"Idea: <idea_text[:100]>"`

**No notebook to clean up**: Step 5 (cleanup) is skipped entirely.

### 2.4 Entry Point Detection Logic

The agent determines the entry point by examining the input string:

1. **URL**: Input matches `youtube.com/watch` or `youtu.be/` -- classified as **VIDEO** entry point
2. **Topic**: Input matches a slug in `data/channels/channels.yaml` -- classified as **TOPIC** entry point
3. **Idea**: Anything else -- classified as **IDEA** entry point

### 2.5 Steps Skipped by Entry Point

| Step | TOPIC | VIDEO | IDEA |
|------|-------|-------|------|
| 0 - Preflight | Yes | Yes | Yes |
| 1 - YouTube Scraper | Yes | **Skip** | **Skip** |
| 1.5 - Video Classifier | Yes | **Skip** | **Skip** |
| 2 - NotebookLM Analyst | Yes | Yes | **Skip** |
| 3 - Strategy Variants | Yes | Yes | Yes |
| 4 - Strategy Translator | Yes | Yes | Yes |
| 4.5 - TODO Auto-Resolution | Yes | Yes | Yes |
| 5 - Cleanup & History | Yes | Yes (topic_id=None) | **Skip** |
| 6 - DB Manager | Yes | Yes | Yes |
| 7 - Summary | Yes | Yes | Yes |

---

## 3. Pipeline Steps (Detailed)

### Step 0: Preflight Check

**What it does**: Verifies that the NotebookLM CLI is authenticated before starting any pipeline work. This prevents wasting time on Steps 1-1.5 only to fail at Step 2.

**Skill/Agent**: Handled inline by the research agent.

**Tool used**: `notebooklm list --json`

**Input**: None.

**Output**: Either OK (continue) or AUTH_ERROR (stop).

**Logic**:
- If the command returns valid JSON (a list of notebooks): authentication is valid, proceed.
- If it fails with an authentication error: stop immediately.

**Error handling**:
- On auth failure, returns:
  ```yaml
  status: AUTH_ERROR
  error_detail: "NotebookLM is not authenticated. Run 'notebooklm login' in your terminal."
  ```
- No other steps are executed if preflight fails.

**Early stop signal**: `AUTH_ERROR`

---

### Step 1: YouTube Scraping (yt-scraper)

**What it does**: Fetches recent videos from monitored YouTube channels for a given topic, then filters out videos that have already been researched.

**Skill**: `.claude/skills/yt-scraper/SKILL.md`

**Tool used**:
```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml --count <N> <topic>
```

**Input**: A topic slug (e.g., `"futures"`, `"trading"`).

**Output**: A list of new (not previously researched) YouTube video URLs.

**Process**:
1. Runs `fetch_topic` to get recent videos from all channels registered under the topic
2. Queries the database for previously researched video IDs:
   ```python
   from tools.db.history_repo import get_researched_video_ids
   researched_ids = get_researched_video_ids(session, "<topic_slug>")
   ```
3. Filters out videos whose `video_id` already exists in `researched_ids`
4. Returns only new, unresearched video URLs

**Database fallback**: If `DATABASE_URL` is not set, reads `data/research/history.yaml` and extracts `video_id` values from the `researched_videos` list.

**Channel source**: If `DATABASE_URL` is set, channels are read from PostgreSQL. Otherwise, the YAML file at `data/channels/channels.yaml` is the fallback.

**Error handling**:
| Condition | Signal |
|-----------|--------|
| Command fails (non-zero exit) | `NO_VIDEOS_FOUND` |
| Topic doesn't exist in DB | `NO_VIDEOS_FOUND` (reports available topics) |
| No recent videos found | `NO_VIDEOS_FOUND` |
| All videos already researched | `NO_NEW_VIDEOS` |
| Database connection error | Falls back to YAML history check |

**Early stop signals**: `NO_VIDEOS_FOUND`, `NO_NEW_VIDEOS`

**Example output**:
```
https://youtube.com/watch?v=abc123
https://youtube.com/watch?v=def456
https://youtube.com/watch?v=ghi789
```

---

### Step 1.5: Video Classification (video-classifier)

**What it does**: Classifies YouTube video titles to determine if they likely contain a trading strategy worth analyzing. This is a cost-saving filter -- NotebookLM analysis is expensive, so irrelevant videos are skipped.

**Skill**: `.claude/skills/video-classifier/SKILL.md`

**Tool used**: None (the agent performs classification directly by reading titles -- no external API or script).

**Input**: List of videos with titles and metadata from Step 1.

**Output**: Two groups -- `strategy` videos (forwarded to Step 2) and `irrelevant` videos (recorded in history and skipped).

**Classification criteria**:

**strategy** (proceed to analysis):
- Specific trading strategies or systems
- Backtesting results of a method
- Step-by-step trading approaches
- Indicator-based setups with clear rules
- Price action patterns presented as a method
- Algorithmic or automated trading methods

**irrelevant** (skip):
- Q&A sessions, interviews (unless about a specific strategy)
- Vlogs, day-in-the-life content
- Trading desk/setup tours
- General market commentary or predictions
- Motivational or mindset content
- Broker/platform reviews, gear reviews
- News recaps, personal stories

**Conservative rule**: When in doubt, classify as `strategy`. Better to waste NotebookLM time than miss a real strategy.

**Irrelevant video recording**: Videos classified as irrelevant are still recorded in the research history with `classification="irrelevant"` and `strategies_found=0`:
```python
add_history(session, video_id=video["video_id"], url=video["url"],
            channel_id=video.get("channel_id"), topic_id=topic_id,
            strategies_found=0, classification="irrelevant")
```

**Error handling**:
- If ALL videos are classified as irrelevant: pipeline stops with `NO_STRATEGIES_FOUND`
- If some videos are classified as strategy: only those proceed to Step 2

**Example output**:
```
- video_id: "abc123" | title: "Building an RTY Breakout Strategy" | classification: strategy | reason: Describes building a specific trading strategy
- video_id: "def456" | title: "My Trading Desk Setup Tour 2026" | classification: irrelevant | reason: Setup tour, no strategy content

Classification complete: 5 videos -- 3 strategy, 2 irrelevant
```

---

### Step 2: Strategy Extraction (notebooklm-analyst)

**What it does**: Uses Google NotebookLM to analyze YouTube videos and extract ALL possible trading strategies with precise, actionable entry/exit rules. This is the core intelligence step of the pipeline.

**Skill**: `.claude/skills/notebooklm-analyst/SKILL.md`

**Tools used**:
```bash
notebooklm create "Research: <topic>" --json     # Create notebook
notebooklm source add "<url>" -n <id> --json     # Add video as source
notebooklm source wait <src_id> -n <id>          # Wait for processing
notebooklm ask "<question>" -n <id>              # Query the notebook
```

**Input**: List of YouTube video URLs (from Step 1.5 for TOPIC, single URL for VIDEO).

**Output**: YAML list of strategies with concrete entry/exit rules.

**Process**:
1. Create ONE notebook for the entire analysis session
2. Add ALL video URLs as sources
3. Wait for all sources to be processed (10-60 seconds per source)
4. Execute a 3-round extraction sequence per strategy

**Extraction Sequence**:

**Round 1 -- Discovery**: One broad question to map all strategies:
> "List ALL the distinct trading strategies, entry methods, or trading systems mentioned in these sources. For each one, give: (1) a short name, (2) which video/source it comes from, (3) a one-sentence summary of the core idea."

**Round 2 -- Rules Extraction** (per strategy): Detailed question to get exact trading rules:
> "For the strategy [NAME], give me the EXACT trading rules as if I needed to program them. I need:
> 1. ENTRY rules for LONG: what conditions must ALL be true to buy?
> 2. ENTRY rules for SHORT: what conditions must ALL be true to sell short?
> 3. EXIT rules: how does the position close?
> 4. What INDICATORS are used? List each with its parameters
> 5. Are there any CONDITIONS that compare the CURRENT bar to a PREVIOUS bar?"

Question 5 is specifically designed to surface temporal comparisons (shifts) that are easy to miss -- divergence patterns, crossovers, and "higher high / lower low" conditions.

**Round 3 -- Context Extraction** (per strategy): Follow-up for market and timeframe guidance:
> "For the strategy [NAME]:
> 1. What MARKETS does the author say it works on?
> 2. What MARKETS does the author say to AVOID?
> 3. What TIMEFRAMES does the author recommend?
> 4. What TIMEFRAMES does the author say to AVOID?
> 5. Any other relevant context?"

**Clarification follow-ups**: If any answer is vague (e.g., "uses momentum"), a targeted follow-up is asked until a concrete rule is obtained or the source is confirmed to lack detail.

**Important**: The notebook is NOT deleted by this step. Cleanup is the agent's responsibility (Step 5).

**Error handling**:
- `notebooklm create` fails: report error, do not continue
- Sources fail to process: retry once, then continue with successful sources
- No strategies found: return `NO_STRATEGIES_FOUND`

**Early stop signal**: `NO_STRATEGIES_FOUND`

**Example output** (YAML):
```yaml
- name: "Hidden RSI Exhaustion Point Entry"
  description: "Enters on RSI divergence with price, using specific thresholds"
  source_channel: "Jacob Amaral"
  source_videos:
    - "AI-Generated Trading Strategies That Actually Work"
  parameters:
    - name: "rsi_period"
      description: "RSI lookback period"
      type: "int"
      default: 14
      range: [10, 20]
  entry_rules:
    - "Price makes a lower low: current LOW < previous LOW"
    - "RSI(14) makes a higher low: current RSI > previous RSI"
    - "RSI(14) on the previous bar < 70"
  exit_rules:
    - "Opposite signal (stop and reverse)"
  recommended_markets:
    - "Feeder Cattle (GF)"
    - "Orange Juice (OJ)"
  recommended_timeframes:
    - "4 hours"
    - "8 hours"
  avoid_timeframes:
    - "30 minutes"
  notes:
    - "Author mentioned strong results on agricultural commodities"
```

---

### Step 3: Strategy Variants (strategy-variants)

**What it does**: Takes raw strategies from the analyst and prepares them for JSON translation. Purifies strategies (removes risk management), splits by direction (long/short), proposes exit methods, and generates market/timeframe variants.

**Skill**: `.claude/skills/strategy-variants/SKILL.md`

**Tool used**: None (inline processing by the agent).

**Input**: YAML list of strategies from Step 2 (or formatted idea text for IDEA entry point).

**Output**: YAML list of self-contained strategy variants, each with a single direction, exit method, market, and timeframe.

**Process** (applied to EACH input strategy):

**Sub-step 3.1 -- Purify**:
- Remove ALL `risk_management` rules (stop loss, take profit, trailing stops, breakeven, position sizing)
- Capture what was removed in notes (e.g., `"removed_sl_tp": "ATR-based SL at 1.5x, TP at 3x"`)
- Keep only `entry_rules` and `exit_rules`

**Sub-step 3.2 -- Separate Directions**:
- If the strategy has both long AND short entry rules, split into two independent strategies
- Name them clearly: `"RSI_Exhaustion"` becomes `"RSI_Exhaustion_Long"` and `"RSI_Exhaustion_Short"`
- If short rules are "mirror of long", invert conditions explicitly (e.g., `RSI(14) < 30` becomes `RSI(14) > 70`)
- Inherently one-directional strategies are kept as-is

**Sub-step 3.3 -- Propose Exit Method**:
Each variant needs exactly ONE exit method:
1. **Stop & Reverse (SAR)**: Only valid for bidirectional strategies that are kept together (not split). Not valid for unidirectional variants.
2. **Source specifies a concrete exit**: Use as-is (e.g., "exit after 20 bars", "RSI > 90")
3. **No valid exit**: Use `num_bars` exit with `_TODO` value, noting exit needs to be determined during backtesting

**Sub-step 3.4 -- Propose Variants**:
- Combine purified strategies with market and timeframe options from the analyst data
- Use `recommended_markets` for market variants (standard symbols: GF, OJ, ES, etc.)
- Use `recommended_timeframes` for timeframe variants
- Exclude anything in `avoid_markets` or `avoid_timeframes`
- If no markets/timeframes are recommended, use `_TODO`
- **Maximum 5 variants per original strategy** (long/short split counts toward this limit)

**Naming convention**: `<Indicator>_<Logic>_<Direction>_<Exit>_<Timeframe>_<Market>`
- Examples: `RSI_Exhaustion_Long_SAR_4h_GF`, `VWAP_Reversal_Short_TE20_8h`, `Shakeout_Long_SAR_1D_OJ`

**Example output** (one variant):
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

---

### Step 4: Strategy Translation (strategy-translator)

**What it does**: Translates each strategy variant into a JSON draft file compatible with the IBKR trading engine. This is a mechanical, literal translation -- no creative decisions.

**Skill**: `.claude/skills/strategy-translator/SKILL.md`

**Tool used**: Database queries for strat_code assignment.

**Reference files** (read before translating):
1. `docs/STRATEGY_FILE_REFERENCE.md` -- primary source of truth
2. `examples/*.json` in the skill directory -- real strategies for format reference
3. `.claude/skills/strategy-translator/translation-rules.md` -- accumulated feedback rules
4. `schema.json` -- JSON schema for validation

**Input**: List of variant objects from Step 3.

**Output**: JSON drafts saved to database via `upsert_draft()`.

**Translation process** (per variant):
1. Map `indicators_needed` to `ind_list` format (grouped by timeframe)
2. Map `entry_rules` to `long_conds` or `short_conds` based on `direction`
3. Map `exit_rules` to `exit_conds`
4. Fill instrument fields from `symbol` and `timeframe`
5. Leave SL/TP as defaults (all `false`, empty params)
6. Set `_notes` from the variant's `notes`
7. Mark unknown values with `"_TODO"`

**Critical translation rules** (from `translation-rules.md`):

| Rule | Detail |
|------|--------|
| `cond` string is bare | No shift notation like `(N)` inside the cond string. Use `"LOW_6H < LOW_6H"` with `shift_1: 1, shift_2: 2` |
| No `group` in entry conditions | `long_conds` and `short_conds` are ALL AND. Groups only apply to `exit_conds` |
| Shift values >= 1 | Shift 0 does not exist. Minimum is shift 1 (most recent completed bar) |
| Multi-output indicators use `MULT_` prefix | MACD, STOCH, BBANDS, KELTNER, ICHIMOKU must have `indCode` starting with `"MULT_"` |
| Pure strategies only | No `stop_loss_init`, `take_profit_init`, or `stop_loss_mgmt` -- leave as defaults |

**strat_code assignment**:
```python
from tools.db.draft_repo import get_all_drafts
existing = get_all_drafts(session)
max_code = max((d.strat_code for d in existing), default=9000)
next_code = max_code + 1
```

**Draft saving**:
```python
from tools.db.draft_repo import upsert_draft
upsert_draft(session, strat_code=next_code, strat_name="<variant_name>", data=draft_json)
```

**Error handling**:
- `DATABASE_URL` not set: cannot proceed, report error
- Variant too vague to translate: skip and report
- Unknown indicator type: use `"_TODO"` for params, note in `_notes`

**Example output**:
```yaml
drafts_created:
  - strat_code: 9001
    strat_name: "RSI_Exhaustion_Long_SAR_4h_GF"
    parent_strategy: "Hidden RSI Exhaustion Point Entry"
    todo_count: 0
  - strat_code: 9002
    strat_name: "RSI_Exhaustion_Short_TE20_8h_OJ"
    parent_strategy: "Hidden RSI Exhaustion Point Entry"
    todo_count: 1
total_drafts: 2
```

---

### Step 4.5: TODO Auto-Resolution (todo-review)

**What it does**: Automatically resolves `_TODO` fields in the JSON drafts produced by Step 4. Uses the Instruments database for symbol-based lookups and applies sensible defaults for common fields. This reduces the number of TODOs that require manual human input via todo-fill.

**Skill**: `.claude/skills/todo-review/SKILL.md`

**Tools used**:
```bash
curl -H "X-API-Key: $DASHBOARD_API_KEY" http://localhost:8000/api/instruments/{symbol}
curl -X PATCH -H "X-API-Key: $DASHBOARD_API_KEY" -H "Content-Type: application/json" \
  -d '{"path": "<field_path>", "value": <value>}' \
  http://localhost:8000/api/strategies/drafts/{strat_code}/fill-todo
```

**Input**: List of `strat_code` integers from Step 4 (all newly translated drafts).

**Output**: A report per draft showing resolved fields, remaining TODOs, and before/after counts.

**Process**:
1. Fetch each draft by `strat_code` from the API
2. Recursively scan the `data` JSON for fields with value `"_TODO"`
3. Extract the `symbol` field and query the Instruments API
4. **Tier 1 -- Instrument Lookup**: Replace `_TODO` values for `exchange`, `multiplier`, `minTick`, `currency`, and `secType` using the Instruments API response
5. **Tier 2 -- Sensible Defaults**: Apply defaults for `rolling_days` (5), `currency` ("USD"), `secType` ("FUT" if futures context), `trading_hours` (null)
6. **Tier 3 -- Never Auto-Fill**: Leave indicator parameters, condition thresholds, `max_timePeriod`, `max_shift`, and `control_params` as `_TODO` -- these require human judgment or optimization
7. PATCH each resolved field individually via the API
8. Re-fetch to verify updated `todo_count`

**Skip conditions**: NONE -- this step always runs for all entry points (TOPIC, VIDEO, IDEA). Even if a draft has zero resolvable TODOs, the step still runs and reports "nothing to resolve".

**Error handling**:
| Condition | Action |
|-----------|--------|
| API not accessible | Report error, terminate step |
| `.env` missing `DASHBOARD_API_KEY` | Report error, terminate step |
| Symbol not found in Instruments DB (404) | Leave instrument fields as `_TODO`, note in report, continue |
| PATCH fails (4xx/5xx) | Report affected field/draft, continue with remaining |
| Symbol is `_TODO` | Skip instrument lookup, apply only Tier 2 defaults |

**Example output**:
```yaml
status: "complete"
drafts_processed: 3
todos_resolved: 9
todos_remaining: 15
per_draft:
  - strat_code: 9001
    strat_name: "RSI_Exhaustion_Long_SAR_4h_GF"
    filled:
      - field: "exchange"
        value: "CME"
        source: "instruments"
      - field: "multiplier"
        value: 500
        source: "instruments"
      - field: "rolling_days"
        value: 5
        source: "default"
    remaining:
      - field: "ind_list.4 hours[0].params.timePeriod_1"
        reason: "indicator parameter - needs optimization"
      - field: "control_params.start_date"
        reason: "backtest-specific"
    todo_count_before: 12
    todo_count_after: 7
```

---

### Step 5: Cleanup and History Recording

**What it does**: Cleans up the NotebookLM notebook and records which videos were processed in the research history.

**Skill/Agent**: Handled inline by the research agent.

**IDEA entry point**: This step is skipped entirely (no notebook, no video history).

**VIDEO entry point**: Records history with `topic_id=None`. `channel_id` is resolved if the channel exists in the DB.

**Process**:

1. **Optional conversation save** (if `save_conversations=true`):
   ```bash
   notebooklm history -n <notebook_id>
   ```
   Output is saved to `data/research/conversations/<topic_slug>_<YYYY-MM-DD>.md`.

2. **Delete the notebook** (ALWAYS, even if previous steps failed):
   ```bash
   notebooklm delete <notebook_id> --yes
   ```

3. **Record research history**:
   ```python
   from tools.db.research_repo import add_history, resolve_topic_id
   with sync_session_ctx() as session:
       topic_id = resolve_topic_id(session, "<topic_slug>")
       add_history(session, video_id="<id>", url="<url>",
                   channel_id=<id>, topic_id=topic_id,
                   strategies_found=<n>)
   ```

**Database fallback**: If `DATABASE_URL` is not set, history is appended to `data/research/history.yaml`.

**Critical rule**: The notebook delete ALWAYS executes, even if Steps 2-4 failed. This prevents orphaned notebooks from accumulating in the NotebookLM account.

---

### Step 6: Database Manager (db-manager)

**What it does**: Saves parent strategies and their variant drafts to PostgreSQL with deduplication.

**Skill**: `.claude/skills/db-manager/SKILL.md`

**Tool used**: SQLAlchemy sync session via `tools.db.strategy_repo` and `tools.db.draft_repo`.

**Input**: Strategy variants from Step 3 and JSON drafts from Step 4.

**Output**: Saved/updated strategies and linked drafts in the database.

**Process**:
1. Group variants by `parent_strategy` name
2. For each parent strategy:
   a. Resolve `source_channel` name to `source_channel_id` via `get_channel_by_name()`
   b. Call `insert_strategy()` (which internally calls `upsert_strategy()` for deduplication)
   c. Capture the returned `Strategy.id`
3. For each variant draft of that parent:
   a. Call `upsert_draft()` with `strategy_id=parent.id` to link the draft

**Deduplication**:
- **Strategies**: Case-insensitive name matching. If a strategy with the same name exists, it is updated (upsert).
- **Drafts**: Deduplication by `strat_code`. If a draft with the same `strat_code` exists, it is updated.

**Error handling**:
- `DATABASE_URL` not set: falls back to YAML file at `data/strategies/strategies.yaml`
- Connection error: report the error
- Invalid data format: report which strategies failed, save nothing

**Example output**:
```yaml
saved:
  - "Hidden RSI Exhaustion Point Entry"
updated:
  - "VWAP Bounce Strategy"
total_in_db: 15
```

---

### Step 7: Summary

**What it does**: Compiles and returns a final summary to the orchestrator with the pipeline results.

**Output format**:
```yaml
status: OK | NO_VIDEOS_FOUND | NO_NEW_VIDEOS | NO_STRATEGIES_FOUND | AUTH_ERROR | ERROR
topic: "<topic>"
videos_analyzed: <count>
strategies_found: <count>
new_saved: [<list>]
duplicates_updated: [<list>]
strategies:
  - name: "<name>"
    source_channel: "<channel>"
    description: "<brief>"
    entry_rules: [<rules>]
    exit_rules: [<rules>]
    json_draft: <draft JSON or file path>
    todo_fields: [<fields marked as _TODO>]
```

---

## 4. Data Flow

### End-to-End Data Transformation

```
YouTube Channels (YAML/DB)
    |
    v
Raw Video URLs + Metadata (title, channel, video_id)
    |
    v  [Step 1.5 filters irrelevant videos]
Classified Videos (strategy vs irrelevant)
    |
    v  [Step 2 analyzes with NotebookLM]
Raw Strategy YAML (entry_rules, exit_rules, markets, timeframes)
    |
    v  [Step 3 purifies and generates variants]
Strategy Variants YAML (single direction, single market, single timeframe)
    |
    v  [Step 4 translates to engine format]
IBKR JSON Drafts (ind_list, long_conds/short_conds, exit_conds) -- with _TODO fields
    |
    v  [Step 4.5 resolves _TODOs via Instruments API + defaults]
IBKR JSON Drafts (fewer _TODO fields -- only ambiguous ones remain)
    |
    v  [Step 6 persists to database]
PostgreSQL: strategies + drafts tables
```

### YAML Strategy Format (from notebooklm-analyst, Step 2)

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
    - "<rule if mentioned>"
  recommended_markets:
    - "<market or asset class>"
  recommended_timeframes:
    - "<timeframe>"
  avoid_timeframes:
    - "<timeframe to avoid>"
  avoid_markets:
    - "<market to avoid>"
  notes:
    - "<additional context>"
```

Fields `recommended_markets`, `recommended_timeframes`, `avoid_timeframes`, `avoid_markets`, and `risk_management` are optional -- only included if the source material mentions them.

### YAML Variant Format (from strategy-variants, Step 3)

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
    source: "<author/channel>"
    exit_method: "<description of chosen exit>"
    removed_sl_tp: "<what risk management was removed>"
    market_rationale: "<why this market was chosen>"
```

### IBKR JSON Draft Format (from strategy-translator, Step 4)

```json
{
  "strat_code": 9001,
  "strat_name": "RSI_Exhaustion_Long_SAR_4h_GF",
  "active": false,
  "tested": false,
  "prod": false,
  "symbol": "GF",
  "secType": "FUT",
  "exchange": "CME",
  "currency": "USD",
  "multiplier": 500,
  "minTick": 0.00025,
  "process_freq": "4 hours",
  "ind_list": {
    "4 hours": [
      {
        "indicator": "PRICE",
        "params": {
          "price_1": "low",
          "timePeriod_1": 1,
          "indCode": "LOW_4h"
        }
      },
      {
        "indicator": "RSI",
        "params": {
          "price_1": "close",
          "timePeriod_1": 14,
          "indCode": "RSI_14_4h"
        }
      }
    ]
  },
  "long_conds": [
    {
      "cond_type": "price_relation",
      "cond": "LOW_4h < LOW_4h",
      "condCode": "lower_low",
      "shift_1": 1,
      "shift_2": 2
    },
    {
      "cond_type": "ind_relation",
      "cond": "RSI_14_4h > RSI_14_4h",
      "condCode": "rsi_higher_low",
      "shift_1": 1,
      "shift_2": 2
    },
    {
      "cond_type": "ind_threshold",
      "cond": "RSI_14_4h < 70",
      "condCode": "rsi_below_70",
      "shift_1": 2
    }
  ],
  "short_conds": [],
  "exit_conds": [],
  "stop_loss_init": { "active": false },
  "take_profit_init": { "active": false },
  "control_params": {
    "start_date": "_TODO",
    "end_date": "_TODO"
  },
  "_notes": {
    "source": "Kevin Davey - AI-Generated Trading Strategies",
    "exit_method": "Stop & Reverse",
    "removed_sl_tp": "None"
  }
}
```

### Database Records Created

For a single pipeline run (TOPIC entry point with 3 videos, 2 strategies, 5 variant drafts):

| Table | Records Created |
|-------|----------------|
| `research_sessions` | 1 (the session record) |
| `research_history` | 3 (one per video, including irrelevant ones) |
| `strategies` | 2 (one per parent strategy) |
| `drafts` | 5 (one per variant, linked to parent strategy) |

---

## 5. Database Schema

### research_sessions

Tracks each pipeline execution for the History page and live monitoring.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Auto-incremented primary key |
| `status` | varchar(20) | `"running"`, `"completed"`, or `"error"` |
| `topic_id` | int (FK -> topics.id) | Topic being researched (NULL for VIDEO/IDEA) |
| `label` | varchar(255) | Free-text description for non-topic sessions |
| `strategies_found` | int | Count of strategies found (set on completion) |
| `drafts_created` | int | Count of drafts created (set on completion) |
| `step` | int | Current pipeline step number (0-6) |
| `step_name` | varchar(50) | Current step name (e.g., "yt-scraper", "notebooklm-analyst") |
| `total_steps` | int | Total number of steps (default: 6) |
| `channel` | varchar(100) | Channel currently being processed |
| `videos_processing` | text[] | Array of video URLs being processed |
| `started_at` | timestamptz | Session start time (auto-set) |
| `completed_at` | timestamptz | Session completion time |
| `error_detail` | text | Error message if status is "error" |
| `result_summary` | jsonb | Summary stats (videos_processed, strategies_found, etc.) |
| `updated_at` | timestamptz | Last update time (auto-updated) |

**Indexes**:
- Partial index on `status` where `status = 'running'` for fast active session lookups.

**NOTIFY**: After every state change, fires `NOTIFY research_update` with the session ID as payload. This allows the FastAPI backend to push real-time updates to WebSocket clients.

### research_history

Records every video that has been analyzed (or skipped as irrelevant).

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Auto-incremented primary key |
| `video_id` | varchar(20) | YouTube video ID |
| `url` | varchar(255) | Full YouTube URL |
| `channel_id` | int (FK -> channels.id) | Source channel (NULL if unknown) |
| `topic_id` | int (FK -> topics.id) | Research topic (NULL for VIDEO entry point) |
| `researched_at` | timestamptz | When the video was researched (auto-set) |
| `strategies_found` | int | Number of strategies extracted (0 for irrelevant) |
| `classification` | varchar(20) | `"strategy"`, `"irrelevant"`, or NULL |
| `title` | varchar(500) | Video title |

**Unique constraint**: `(video_id, topic_id)` -- prevents re-researching the same video for the same topic.

**Deduplication**: `add_history()` checks for existing `(video_id, topic_id)` pair before inserting. If it exists, returns the existing row unchanged.

### strategies

Parent strategy records containing the human-readable trading logic.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Auto-incremented primary key |
| `name` | varchar(255) | Unique strategy name |
| `status` | varchar(20) | `"pending"`, `"idea"`, or `"validated"` (default: `"pending"`) |
| `description` | text | Strategy description |
| `source_channel_id` | int (FK -> channels.id) | Where the strategy was found |
| `source_videos` | text[] | Array of source video titles |
| `parameters` | jsonb | Indicator parameters |
| `entry_rules` | jsonb | Entry conditions (human-readable) |
| `exit_rules` | jsonb | Exit conditions (human-readable) |
| `risk_management` | jsonb | Risk management rules |
| `notes` | jsonb | Additional notes and context |
| `created_at` | timestamptz | Creation time (via TimestampMixin) |
| `updated_at` | timestamptz | Last update time (via TimestampMixin) |

**Indexes**:
- Full-text search GIN index on `name || ' ' || COALESCE(description, '')` for the search functionality.

**Deduplication**: `upsert_strategy()` performs case-insensitive name matching. If a strategy with the same name exists, its fields are updated rather than creating a duplicate.

### drafts

JSON draft files for the IBKR trading engine, linked to parent strategies.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Auto-incremented primary key |
| `strat_code` | int (unique) | Unique strategy code (used as IB clientId) |
| `strat_name` | varchar(255) | Descriptive variant name |
| `strategy_id` | int (FK -> strategies.id) | Parent strategy |
| `data` | jsonb | Complete strategy JSON for the trading engine |
| `todo_count` | int | Number of `_TODO` fields remaining |
| `todo_fields` | text[] | Array of paths to `_TODO` fields |
| `active` | boolean | Strategy is active (default: false) |
| `tested` | boolean | Strategy passed backtesting (default: false) |
| `prod` | boolean | Approved for production (default: false) |
| `created_at` | timestamptz | Creation time (via TimestampMixin) |
| `updated_at` | timestamptz | Last update time (via TimestampMixin) |

**Deduplication**: `upsert_draft()` deduplicates by `strat_code`. Existing drafts with the same code are updated.

**TODO tracking**: `todo_count` and `todo_fields` are automatically computed from `_TODO` values in the `data` JSONB field. The `fill_todo` API endpoint allows incrementally replacing `_TODO` sentinels with real values.

### Supporting Tables

**topics**: Groups channels by research topic.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Primary key |
| `slug` | varchar(50) | Unique topic slug (e.g., "futures", "trading") |
| `description` | text | Topic description |

**channels**: YouTube channels monitored for each topic.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Primary key |
| `topic_id` | int (FK -> topics.id) | Parent topic (CASCADE delete) |
| `name` | varchar(100) | Channel name |
| `url` | varchar(255) | Channel URL |
| `last_fetched` | timestamptz | Last time videos were fetched |

**Unique constraint**: `(topic_id, url)` -- prevents duplicate channel-topic pairs.

### Entity Relationship Diagram

```
topics (1) ----< channels (N)
  |                  |
  |                  |
  v                  v
research_history >--- (channel_id, topic_id)
  ^
  |
research_sessions --- (topic_id)

strategies (1) ----< drafts (N)
  |
  +--- source_channel_id --> channels
```

---

## 6. Strategy JSON Format

The IBKR trading engine JSON format is documented comprehensively in `docs/STRATEGY_FILE_REFERENCE.md`. This section covers the key aspects relevant to the research pipeline.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `strat_code` | int | Unique strategy ID, also used as IB clientId. Range: 1001+ (pipeline starts at 9001) |
| `strat_name` | string | Human-readable variant name |
| `active` / `tested` / `prod` | boolean | Three-gate safety mechanism. All must be true for live trading |
| `symbol` | string | Trading symbol (e.g., "MNQ", "ES", "GF") |
| `secType` | string | IB security type: `"FUT"`, `"STK"`, `"OPT"`, `"CASH"` |
| `exchange` | string | Exchange code (e.g., "CME", "GLOBEX") |
| `process_freq` | string | Primary bar timeframe (e.g., "4 hours", "1 day") |
| `ind_list` | object | Indicators grouped by timeframe |
| `long_conds` | array | LONG entry conditions (ALL must be true) |
| `short_conds` | array | SHORT entry conditions (ALL must be true) |
| `exit_conds` | array | Exit conditions (AND within group, OR across groups) |

### ind_list Structure

Indicators are grouped by timeframe. Each indicator has a unique `indCode` used in conditions:

```json
"ind_list": {
  "4 hours": [
    {
      "indicator": "RSI",
      "params": {
        "price_1": "close",
        "timePeriod_1": 14,
        "indCode": "RSI_14_4h"
      }
    }
  ]
}
```

### Condition Types and `cond` String Format

A condition object:
```json
{
  "cond_type": "ind_threshold",
  "cond": "RSI_14_4h < 30",
  "condCode": "rsi_oversold",
  "shift_1": 1,
  "shift_2": 0
}
```

**Condition types**: `price_relation`, `ind_relation`, `ind_threshold`, `cross_above`, `cross_bellow` (note: engine spelling), `num_bars`, and others defined in `STRATEGY_FILE_REFERENCE.md`.

**cond string rules**:
- Uses indicator `indCode` names directly (e.g., `"RSI_14_4h < 30"`)
- Shift notation `(N)` is NEVER placed inside the `cond` string
- Same indicator at different shifts: `"LOW_4h < LOW_4h"` with `shift_1` and `shift_2` differentiating them

### Shift Convention

**Critical**: Shifts are specified in `shift_1` (left operand) and `shift_2` (right operand), NOT in the `cond` string.

- `shift_1` = lookback for the LEFT operand
- `shift_2` = lookback for the RIGHT operand
- Shift values must be >= 1 (shift 0 does not exist in the engine)
- Shift 1 = most recent completed bar, shift 2 = bar before that, etc.

**Example**: "Current low is lower than previous low"
```json
{
  "cond": "LOW_4h < LOW_4h",
  "shift_1": 1,
  "shift_2": 2
}
```
This reads: `LOW_4h[shift 1] < LOW_4h[shift 2]`, i.e., "most recent bar's low < the bar before that's low".

### The (N) Notation Fix (Phase 10.1)

An early bug in the translator generated conditions like `"LOW_6H(0) < LOW_6H(1)"` with shift notation embedded in the `cond` string. This broke the trading engine's condition parser, which uses `cond.split()` to look up column names in the DataFrame.

**Fix**: The `cond` string must always use bare indicator names. Shifts go exclusively in the `shift_1` and `shift_2` fields.

**Before (broken)**:
```json
{"cond": "LOW_6H(0) < LOW_6H(1)", "shift_1": 0, "shift_2": 0}
```

**After (correct)**:
```json
{"cond": "LOW_6H < LOW_6H", "shift_1": 1, "shift_2": 2}
```

This was the root cause of "zero trades" in backtesting for many pipeline-generated strategies.

---

## 7. Session Tracking

### Session Creation

Session tracking is MANDATORY for ALL entry points when `DATABASE_URL` is set. Sessions are created at pipeline start and updated at each step.

```python
from tools.db.research_repo import create_session, update_session_step, complete_session, error_session

# TOPIC entry point:
research_session = create_session(session, topic_slug=topic)

# VIDEO entry point:
research_session = create_session(session, label=f"Video: {video_title or video_url}")

# IDEA entry point:
research_session = create_session(session, label=f"Idea: {idea_text[:100]}")
```

### Session Lifecycle

```
create_session()
    |
    v  status="running", step=0, step_name="preflight"
update_session_step(step=1, step_name="yt-scraper")
    |
    v  (at each pipeline step)
update_session_step(step=2, step_name="notebooklm-analyst")
    |
    ...
    |
    v  On success:
complete_session(result_summary={...}, strategies_found=N, drafts_created=M)
    |  status="completed", completed_at=now()
    |
    v  On failure:
error_session(error_detail="NotebookLM timeout after 120s")
       status="error", completed_at=now()
```

### Step Updates

Each step update fires a PostgreSQL `NOTIFY research_update` event with the session ID as payload:
```python
update_session_step(session, session_id, step=1, step_name="yt-scraper",
                    channel="ChannelName", videos=["url1", "url2"])
```

### Completion Stats

On completion, the session records:
```python
complete_session(session, session_id,
    result_summary={"topic": topic_slug, "videos_processed": 5, "strategies_found": 2},
    strategies_found=2,
    drafts_created=5,
)
```

### Session Lifecycle by Entry Point

| Phase | TOPIC | VIDEO | IDEA |
|-------|-------|-------|------|
| Creation | `create_session(topic_slug=...)` | `create_session(label="Video: ...")` | `create_session(label="Idea: ...")` |
| Step 0 | Preflight | Preflight | Preflight |
| Step 1 | yt-scraper | (skipped) | (skipped) |
| Step 1.5 | classifier | (skipped) | (skipped) |
| Step 2 | analyst | analyst | (skipped) |
| Step 3 | variants | variants | variants |
| Step 4 | translator | translator | translator |
| Step 5 | cleanup | cleanup (topic_id=None) | (skipped) |
| Step 6 | db-manager | db-manager | db-manager |
| Completion | complete_session | complete_session | complete_session |

### If DATABASE_URL Is Not Set

The pipeline still runs but without session tracking. No `research_sessions` records are created. The frontend Live page will show no data.

---

## 8. Frontend Integration

### History Page (`frontend/src/pages/HistoryPage.tsx`)

The History page displays research sessions and individual video research records.

**Two view modes**:
1. **Grouped (By Session)**: Shows research sessions as expandable groups, each containing the videos processed in that session. Default view.
2. **Flat List**: Shows individual video research history entries with filters.

**API queries**:
- **Grouped mode**: `GET /api/research/sessions` via `getResearchSessions(50)` -- returns the last 50 completed/error sessions with their videos.
- **Flat mode**: `GET /api/research/history` via `getHistory({topic, channel, from, to, page, limit})` -- returns paginated video history.
- **Stats**: `GET /api/research/history/stats` via `getHistoryStats()` -- returns aggregate statistics (total videos, total strategies, by topic, by channel).

**Session group display**:
- Topic name (or "No topic" for VIDEO/IDEA sessions)
- Start date and time
- Video count / strategy count summary (e.g., "5v / 3s")
- Duration
- Status badge (completed/error)
- Link to session detail page
- Expandable table showing individual videos with video ID (linked to YouTube), channel, and strategies found count

**Flat list display**:
- Filterable by topic, channel, and date range
- Paginated (50 per page)
- Shows video ID, URL, channel, topic, research date, strategies found

### Strategies Page (`frontend/src/pages/StrategiesPage.tsx`)

The Strategies page displays extracted strategies organized by status with three main tabs.

**Tabs**:
1. **Pending**: Strategies with `status="pending"` (newly discovered, not yet reviewed)
2. **Ideas**: Strategies with `status="idea"` (reviewed and marked as interesting)
3. **Strategies**: Strategies with `status="validated"`, with two sub-tabs:
   - **With TODOs**: Validated strategies that still have `_TODO` fields in their drafts
   - **Complete**: Validated strategies with all fields filled in

**Filters**:
- Text search (full-text search on name + description)
- Channel filter (dropdown of unique source channels)
- Session filter (dropdown of research sessions)

**API queries**:
- `GET /api/strategies` with query params: `channel`, `search`, `session_id`, `has_draft`, `has_todos`, `status`, `page`, `limit`
- `GET /api/strategies/{strategy_name}` for detail view
- `GET /api/strategies/{strategy_name}/drafts` for linked drafts
- `PATCH /api/strategies/{strategy_name}/status` to change status

**Strategy card display**: Shows strategy name, description, source channel, entry/exit rules.

**Strategy detail view**: Full strategy information including all drafts linked to it. The `StrategyDetail` component shows:
- Strategy metadata (name, description, source)
- Entry and exit rules
- Linked draft variants with their strat_code, symbol, todo_count
- Ability to change status (pending -> idea -> validated)

### How Strategies and Drafts Relate in the UI

- A **Strategy** is the parent concept (e.g., "RSI Divergence Entry")
- A **Draft** is a specific tradeable variant (e.g., "RSI_Divergence_Long_SAR_4h_GF" with strat_code 9001)
- One strategy can have many drafts (different directions, markets, timeframes)
- The Strategies page shows parent strategies; clicking one reveals its linked drafts
- Draft detail includes the full JSON data blob, TODO summary, and fill-TODO capability

### Draft API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/strategies/drafts` | GET | List all drafts (filterable by has_todos, status) |
| `/api/strategies/drafts/{strat_code}` | GET | Get single draft with full data |
| `/api/strategies/drafts/{strat_code}/fill-todo` | PATCH | Replace a `_TODO` value at a specific path |
| `/api/strategies/drafts/{strat_code}/data` | PUT | Replace entire draft data blob |

### WebSocket Live Updates

The research status WebSocket at `/api/research/status` provides real-time updates during pipeline execution:
1. Client connects and sends auth message: `{"type": "auth", "api_key": "..."}`
2. On success, receives current active sessions
3. Receives updates on every `NOTIFY research_update` event from PostgreSQL

---

## 9. YouTube Channel Database

### Storage Format

Channels are stored in YAML format at `data/channels/channels.yaml`:

```yaml
topics:
  futures:
    description: Futures strategies
    channels:
    - name: Jacob Amaral
      url: https://www.youtube.com/@jacobamaral
      last_fetched: '2026-03-13'
  trading:
    description: Algorithmic and quantitative trading
    channels:
    - name: QuantProgram
      url: https://www.youtube.com/@QuantProgram
      last_fetched: null
```

### How Topics Group Channels

Topics are the top-level organizational unit. Each topic has a slug (e.g., `"futures"`, `"trading"`, `"ai-agents"`) and contains a list of YouTube channels relevant to that topic.

When you research a topic like `futures`, the pipeline fetches recent videos from ALL channels under the `futures` topic.

### PostgreSQL Storage

When `DATABASE_URL` is set, channels and topics are also stored in PostgreSQL tables (`topics` and `channels`). The YAML file serves as a fallback and initial seed.

### Channel Management

**Via CLI** (using the `tools.youtube.channels` module):
```bash
# List all topics
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics

# List channels for a topic
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml list futures
```

**Via Database** (using `tools.db.channel_repo`):
```python
from tools.db.channel_repo import (
    get_all_topics, get_topic_by_slug, create_topic,
    get_channels_by_topic, create_channel, delete_channel,
    get_channel_by_name, update_channel_last_fetched,
)
```

**Via API** (using the topics/channels endpoints in the FastAPI backend).

### Channel Fields

| Field | Description |
|-------|-------------|
| `name` | Human-readable channel name (e.g., "Jacob Amaral") |
| `url` | YouTube channel URL (e.g., "https://www.youtube.com/@jacobamaral") |
| `last_fetched` | Date when videos were last fetched (null if never) |

---

## 10. Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes (for DB features) | PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5432/irt`) |
| `DASHBOARD_API_KEY` | Yes (for WebSocket auth) | API key for frontend WebSocket authentication |
| `STRATEGIES_DIR` | No | Path to IBKR strategy files (default: `../Strategies/`) |

### Global Settings (`config/settings.json`)

```json
{
  "youtube": {
    "default_search_count": 20,
    "default_months_filter": 6,
    "fetch_workers": 4
  },
  "notebooklm": {
    "language": "es"
  },
  "paths": {
    "channels_db": "data/channels/channels.yaml",
    "strategies_db": "data/strategies/strategies.yaml",
    "backtests_dir": "data/backtests"
  }
}
```

| Setting | Description |
|---------|-------------|
| `youtube.default_search_count` | Default number of videos to fetch per channel |
| `youtube.default_months_filter` | Only fetch videos from the last N months |
| `youtube.fetch_workers` | Number of parallel fetch workers |
| `notebooklm.language` | Language for NotebookLM interactions |
| `paths.channels_db` | Path to the YAML channel database |
| `paths.strategies_db` | Path to the YAML strategy database (fallback) |
| `paths.backtests_dir` | Path to backtest results directory |

### NotebookLM Authentication

NotebookLM requires Google authentication. The CLI tool `notebooklm` manages this:

```bash
# Initial login (opens browser for Google OAuth)
notebooklm login

# Check authentication status
notebooklm auth check

# Full validation with network test
notebooklm auth check --test
```

Authentication is cookie-based and persists across sessions. When cookies expire, you must re-run `notebooklm login`.

The pipeline's Step 0 (Preflight) verifies auth before starting.

### Docker Setup

```bash
# Start all services (PostgreSQL, API, Frontend, Pipeline)
docker compose up -d

# Access points:
# - Dashboard: http://localhost:5173
# - API: http://localhost:8000

# Run pipeline manually
docker compose run pipeline python -m tools.youtube.search "futures trading" --count 5

# View registered channels
docker compose run pipeline python -m tools.youtube.channels --db data/channels/channels.yaml topics
```

---

## 11. Troubleshooting

### Early Stop Signals Reference

| Signal | Step | Meaning | Resolution |
|--------|------|---------|------------|
| `AUTH_ERROR` | 0 | NotebookLM not authenticated | Run `notebooklm login` in terminal |
| `NO_VIDEOS_FOUND` | 1 | No videos from channels or topic doesn't exist | Check topic slug exists; check channel URLs are valid |
| `NO_NEW_VIDEOS` | 1 | All videos have been researched already | Wait for new content; add more channels to the topic |
| `NO_STRATEGIES_FOUND` | 1.5 or 2 | All videos irrelevant (1.5) or no strategies extracted (2) | Try different topic; check video content manually |
| `ERROR` | Any | Generic error | Check error_detail in session record |

### Common Issues and Solutions

**Issue: Pipeline fails at Step 0 with AUTH_ERROR**
- Cause: NotebookLM cookies have expired
- Fix: Run `notebooklm login` and re-authenticate via browser
- Verify: `notebooklm auth check --test`

**Issue: `NO_VIDEOS_FOUND` but channels have content**
- Cause: Topic slug doesn't match any entry in channels.yaml/DB
- Fix: Check available topics with `python -m tools.youtube.channels --db data/channels/channels.yaml topics`
- Cause: `last_fetched` filter is too recent
- Fix: Check `default_months_filter` in `config/settings.json`

**Issue: `NO_NEW_VIDEOS` despite new channel uploads**
- Cause: All fetched videos are already in research_history
- Fix: Increase `--count` parameter to fetch more videos, or check if the new videos were uploaded after the last fetch

**Issue: NotebookLM rate limiting during Step 2**
- Cause: Google rate limits on NotebookLM API
- Fix: Wait 5-10 minutes and retry. The pipeline doesn't auto-retry rate limits.

**Issue: Strategies have too many `_TODO` fields**
- Cause: Source video doesn't provide specific parameter values
- Fix: Use the `/api/strategies/drafts/{strat_code}/fill-todo` endpoint or the `todo-fill` skill to fill in missing values

**Issue: Database connection errors**
- Cause: PostgreSQL not running or `DATABASE_URL` misconfigured
- Fix: Check `docker compose ps` to verify PostgreSQL is running; verify connection string

**Issue: Orphaned NotebookLM notebooks**
- Cause: Pipeline crashed before Step 5 cleanup
- Fix: Run `notebooklm list` to see orphaned notebooks, then `notebooklm delete <id> --yes` for each

### Zero Trades in Backtesting (Phase 10.1 Fix)

If a pipeline-generated strategy produces zero trades during backtesting, the most common cause is the `(N)` notation bug in condition strings.

**Symptoms**:
- Backtest completes but with 0 trades
- The `cond` field contains shift notation like `"LOW_6H(0) < LOW_6H(1)"`

**Root cause**: The trading engine's condition parser uses `cond.split()` to extract column names from the `cond` string and look them up in the DataFrame. When the `cond` string contains `(N)` notation (e.g., `"LOW_6H(0)"`), the parser can't find a column named `"LOW_6H(0)"` because the actual DataFrame column is named `"LOW_6H"`.

**Fix**: Ensure the `cond` string uses bare indicator names with shifts in separate fields:

Before (broken):
```json
{"cond": "LOW_6H(0) < LOW_6H(1)", "shift_1": 0, "shift_2": 0}
```

After (correct):
```json
{"cond": "LOW_6H < LOW_6H", "shift_1": 1, "shift_2": 2}
```

Also note that `shift_1` and `shift_2` must be >= 1 (shift 0 does not exist in the engine).

**How to check**: Inspect the `data` JSONB field of the draft and look for `(N)` patterns in any `cond` strings. If found, update via the `PUT /api/strategies/drafts/{strat_code}/data` endpoint.

### How to Re-Run a Failed Pipeline

1. Check the session status in the History page or via API: `GET /api/research/sessions`
2. Read the `error_detail` field to understand what failed
3. Fix the underlying issue (auth, connection, etc.)
4. Re-run by asking to research the same topic -- the pipeline will skip already-researched videos automatically
5. If the NotebookLM notebook was not cleaned up, delete it manually: `notebooklm list` then `notebooklm delete <id> --yes`

### Debugging Checklist

1. Check NotebookLM auth: `notebooklm auth check --test`
2. Check database connectivity: `docker compose ps` and verify PostgreSQL is healthy
3. Check available topics: verify the topic slug exists in `data/channels/channels.yaml`
4. Check research history: query `research_history` to see which videos have been processed
5. Check session status: query `research_sessions` for error details
6. Check draft data: inspect the `data` JSONB field for `_TODO` values and `(N)` notation bugs
7. Check engine compatibility: validate the draft JSON against `docs/STRATEGY_FILE_REFERENCE.md`
