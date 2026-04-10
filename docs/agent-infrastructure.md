# Agent Infrastructure

How the IRT project routes user requests to specialized AI agents for research and backtesting.

## 1. Overview

The agent architecture replaces the original monolithic research agent with a 3-layer system of independent, single-responsibility agents. Each agent lives in its own directory with an `AGENT.md` file that defines its metadata (YAML front-matter) and behavioral instructions.

**Why it exists:**

- The monolith (~369 lines) bundled orchestration, DB ops, session tracking, and error handling in one file.
- Individual capabilities (video discovery, strategy extraction, DB persistence) could not be invoked standalone.
- No smart routing -- the user had to know the exact command.
- Adding a new domain required modifying the monolith.

**3-layer model:**

| Layer | Role | Example |
|-------|------|---------|
| CEO | The Claude Code main session. Classifies user intent, routes to the right agent. | The user's session (not a file) |
| Manager | Orchestrates a sequence of agents for a domain pipeline. | Research Manager |
| Agent | Leaf worker. Single responsibility. Does not spawn other agents. | Video Discovery |

**10 agents total:** 1 manager, 3 research, 5 backtesting, 1 shared.

## 2. Architecture Diagram

```
                         +------------------------+
                         |          CEO            |
                         | (Claude Code session +  |
                         |  routing rules in       |
                         |  project CLAUDE.md)     |
                         +-----+----------+-------+
                               |          |
                    +----------+    +-----+-----+-----+-----+
                    |               |     |     |     |     |
          +---------v---------+  +-v---+ v---+ v---+ v---+ v---+
          | Research Manager  |  |Sim  |Cmp  |MC   |Mnk  |Str  |
          | (pipeline seq)    |  +-----+-----+-----+-----+-----+
          +--+-----+-----+---+   Backtesting agents (CEO-routed)
             |     |     |
          +--v-+ +-v--+ +v--+
          |VDis| |SEx | |SPr|
          +----+ +----+ +---+
                    \     |
                     \    |
                  +---v---v----+
                  |DB Persist  |
                  | (shared)   |
                  +------------+
```

**Legend:** VDis = Video Discovery, SEx = Strategy Extractor, SPr = Strategy Processor, Sim = Simple Backtester, Cmp = Complete Backtester, MC = Monte Carlo Analyst, Mnk = Monkey Tester, Str = Stress Tester.

## 3. Agent Catalog

| Agent | Domain | Role | Purpose | Status |
|-------|--------|------|---------|--------|
| research-manager | research | manager | Orchestrate research pipeline (discovery -> extraction -> processing -> persistence) | Active |
| video-discovery | research | agent | Fetch and classify YouTube videos by topic | Active |
| strategy-extractor | research | agent | Extract trading strategies from videos using NotebookLM | Active |
| strategy-processor | research | agent | Purify, split, generate variants, translate to IBKR JSON, auto-fill TODOs | Active |
| db-persistence | shared | agent | Save strategies and drafts to PostgreSQL with deduplication | Active |
| simple-backtester | backtesting | agent | Trigger simple backtest via API, interpret 40+ metrics | Active |
| complete-backtester | backtesting | agent | Full backtest with trade log and equity curve analysis | Active |
| monte-carlo-analyst | backtesting | agent | Monte Carlo simulation, luck vs skill assessment | Active |
| monkey-tester | backtesting | agent | Random entry benchmark, p-value and statistical edge | Active |
| stress-tester | backtesting | agent | Parameter sweep, robustness score, flag fragile params | Active |

Research agents (including the manager) are fully implemented with complete behavioral instructions. Backtesting agents have full front-matter and high-level flow documentation; their interpretation logic will deepen as the job completion monitor (Phase 5) is validated in production.

## 4. How It Works

### CEO Intent Classification

The CEO (Claude Code main session) reads the user's input and classifies it using rules defined in the project `CLAUDE.md`:

| User Input Pattern | Routes To | Entry Point |
|--------------------|-----------|-------------|
| "research `<topic>`" or topic-like input | research-manager | topic |
| YouTube URL | research-manager | url |
| "idea:" or describes a trade setup | research-manager | idea |
| "backtest `<draft>`" or "simple backtest" | simple-backtester | direct |
| "full backtest" or "complete backtest" | complete-backtester | direct |
| "monte carlo" or "MC analysis" | monte-carlo-analyst | direct |
| "monkey test" | monkey-tester | direct |
| "stress test" | stress-tester | direct |
| "full analysis on `<draft>`" | Chain: complete -> MC -> monkey -> stress | chained |

If intent is ambiguous, the CEO asks a clarifying question instead of guessing.

### Research Manager Pipeline

The Research Manager sequences 3 research agents + DB Persistence, with 3 entry points:

| Entry Point | Steps Executed |
|-------------|----------------|
| Topic (e.g., "research futures") | Discovery -> Extraction -> Processing -> Persistence |
| URL (e.g., YouTube link) | Extraction -> Processing -> Persistence |
| Idea (e.g., "buy RSI < 30") | Processing -> Persistence |

Early stop signals (`NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND`) halt the pipeline cleanly.

### Backtesting Routing

Backtesting agents are invoked directly by the CEO -- there is no Backtesting Manager. For "full analysis" requests, the CEO chains all 4 backtesting agents sequentially and synthesizes results. If synthesis logic grows complex, a Backtesting Manager can be promoted.

### Agents Use Skills

Agents do not replace the existing skill layer (`.claude/skills/`). They orchestrate skills:

- Video Discovery uses `yt-scraper` + `video-classifier`
- Strategy Extractor uses `notebooklm-analyst`
- Strategy Processor uses `strategy-variants` + `strategy-translator` + `todo-review`
- DB Persistence uses `db-manager`

Backtesting agents call the API directly (no skills needed).

## 5. How to Use

### Research Examples

```
User: "research futures"
  -> CEO classifies: topic="futures", domain=research
  -> Spawns Research Manager (topic entry)
  -> Full pipeline: Discovery -> Extraction -> Processing -> Persistence
  -> Returns summary with saved drafts

User: "extract from https://youtube.com/watch?v=..."
  -> CEO classifies: url, domain=research
  -> Spawns Research Manager (url entry)
  -> Skips discovery, runs: Extraction -> Processing -> Persistence

User: "here's an idea: buy when RSI < 30"
  -> CEO classifies: idea, domain=research
  -> Spawns Research Manager (idea entry)
  -> Skips discovery + extraction, runs: Processing -> Persistence
```

### Backtesting Examples

```
User: "backtest ES_RSI_001"
  -> CEO classifies: backtest, draft_id=ES_RSI_001
  -> Spawns Simple Backtester directly
  -> Returns metrics + pass/fail verdict

User: "full analysis on ES_RSI_001"
  -> CEO chains 4 agents sequentially:
     1. Complete Backtester -> metrics + trade log
     2. Monte Carlo Analyst -> luck vs skill assessment
     3. Monkey Tester -> statistical edge verdict
     4. Stress Tester -> parameter robustness
  -> CEO synthesizes all results into combined assessment
```

### How Agents Are Spawned

The CEO uses the Agent tool to launch agents:

```
Agent({
  description: "Research Manager",
  prompt: "Read and follow .claude/agents/research-manager/AGENT.md. Entry point: topic. Input: topic='futures'."
})
```

```
Agent({
  description: "Simple Backtester",
  prompt: "Read and follow .claude/agents/simple-backtester/AGENT.md. Input: draft_id='ES_RSI_001'."
})
```

## 6. How to Add a New Agent

1. Create directory `.claude/agents/{name}/`
2. Create `AGENT.md` with YAML front-matter (use `.claude/agents/TEMPLATE.md` as starting point):

```yaml
---
name: my-new-agent
description: One-line description
domain: research | backtesting | shared
role: agent
inputs:
  - name: param_name
    type: string
    required: true
outputs:
  - name: output_name
    type: string
skills_used:
  - skill-name
dependencies: []
---

# My New Agent

(behavioral instructions here)
```

3. If part of a Manager's pipeline, update that Manager's `AGENT.md` to include the new agent in its sequence.
4. If directly routable by the CEO, add a routing rule to the project `CLAUDE.md`.

See `.claude/agents/CONVENTION.md` for the full convention specification.

## 7. Job Completion Monitor

Backtesting agents need to wait for long-running worker jobs. The job completion infrastructure (Phase 5 of the migration) provides:

**API endpoints:**
- `POST /api/backtests` -- submit a job, returns `job_id`
- `GET /api/backtests/{job_id}` -- poll job status (`pending` -> `running` -> `completed` | `failed`)

**Pattern:** Agents submit a job, poll until completion, then interpret the results from the API response payload. Agents never parse worker stdout -- all data comes from structured JSON in the API response.

**Typical durations:**
- Simple backtest: 5-30 seconds
- Complete backtest: 10-60 seconds
- Monkey test: 30 seconds to 5 minutes
- Monte Carlo: 5-60 minutes
- Stress test: 1-30 minutes

## 8. Current Status

**Fully working:**
- Research pipeline end-to-end through agent architecture (CEO -> Research Manager -> 4 agents)
- CEO routing rules in project `CLAUDE.md` for both research and backtesting
- All 10 agent directories with `AGENT.md` files (front-matter + instructions)
- Convention documentation (`CONVENTION.md`, `TEMPLATE.md`, `DATA_FORMATS.md`)

**Active but evolving:**
- Backtesting agents have full AGENT.md files with high-level flows and API integration details
- Interpretation depth will increase as the job monitor is validated in production

**What's next:**
- Validate the job completion monitor end-to-end with real backtests
- Deepen backtesting agent interpretation logic based on production experience
- Consider promoting to a Backtesting Manager if CEO-level synthesis becomes complex
- Phase 8: retire the old monolithic research agent (currently archived, not deleted)

---

For the full design rationale, implementation phases, and decision log, see [Designs/agent-migration.md](../Designs/agent-migration.md).
