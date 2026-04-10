# Design: Agent Migration — Smart Router + Independent Agents

**Status:** APPROVED
**Date:** 2026-04-10
**Branch:** agent-migration

---

## 1. Problem Statement

The research agent (`AGENT.md`, ~369 lines) is a monolith that handles orchestration, DB operations, session tracking, channel resolution, history logging, and error handling — all in a single file. This creates several issues:

- **No reusability** — individual capabilities (video discovery, strategy extraction, DB persistence) cannot be invoked standalone.
- **No independent improvement** — editing one concern risks breaking others.
- **No smart routing** — the user must know the exact command; the system cannot interpret intent and route accordingly.
- **No extensibility** — adding a new domain (market scanner) requires modifying the monolithic agent.

### Goals

1. Separate the monolith into single-responsibility agents.
2. Make every agent callable standalone (reusability).
3. Allow independent improvement of each agent by editing its own `AGENT.md`.
4. Enable smart routing: tell the CEO what you want and it routes to the right agents.
5. Make it trivial to add new leaf agents within an existing Manager's flow without modifying the CEO.

### Non-Goals

- Rewriting the existing skills (yt-scraper, notebooklm-analyst, etc.) — agents USE skills, they don't replace them.
- Building a general-purpose agent framework — this is specific to the IRT project.
- Changing the underlying infrastructure (API, worker, database schema).
- Automating agent selection with ML/embeddings — the CEO uses rule-based intent classification.

---

## 2. Proposed Approach

**Option A — Smart Router + Independent Agents** with a 3-layer architecture: CEO (the Claude Code main session), Managers, and Agents. Each agent is self-contained with an `AGENT.md` that includes a YAML front-matter block describing its name, domain, role, inputs, outputs, skills used, and dependencies. The CEO routes to agents using explicit rules defined in the project `CLAUDE.md`.

### 2.1 Architecture

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
          +--+-----+-----+---+
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

**Legend:**
- VDis = Video Discovery, SEx = Strategy Extractor, SPr = Strategy Processor
- Sim = Simple Backtester, Cmp = Complete Backtester, MC = Monte Carlo Analyst
- Mnk = Monkey Tester, Str = Stress Tester

### 2.2 Layer Definitions

#### Layer 1: CEO (Claude Code Main Session)

The top-level entry point is the user's Claude Code session itself — not a separate spawned agent. It receives user input and routes it to the appropriate Manager or agent. Its routing rules live in the project `CLAUDE.md` as an explicit rule table mapping domains to agents.

| Responsibility | Details |
|---|---|
| Intent classification | Classifies input as: topic, url, idea, strategy name, backtest request |
| Routing table | Explicit rules in `CLAUDE.md` listing each agent and its domain — no auto-discovery |
| Dynamic plan building | Determines which agents to invoke based on intent + routing rules |
| Routing | Dispatches to Research Manager for research tasks, or directly to backtesting agents for backtest requests |
| Result merging | Collects and synthesizes results from Managers and agents |

#### Layer 2: Managers

**Research Manager** is the only Manager in the current architecture. It has its agent sequence hardcoded in its `AGENT.md`.

**Research Manager:**

Manages the research pipeline with 3 entry points:

| Entry Point | Steps Executed |
|---|---|
| Topic (e.g., "research futures") | Discovery -> Extraction -> Processing -> Persistence |
| URL (e.g., "extract from youtube.com/...") | Extraction -> Processing -> Persistence (skip discovery) |
| Idea (e.g., "buy RSI < 30") | Processing -> Persistence (skip discovery + extraction) |

- Sequences agents in the correct order
- Handles early stop signals (`NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND`)
- Owns session lifecycle (create, update, complete)

**Backtesting routing** is handled directly by the CEO via rules in `CLAUDE.md`. Promote to a dedicated Manager agent if synthesis logic proves complex enough.

#### Layer 3: Agents

**Research Agents:**

| Agent | Responsibility | Skills Used | Input | Output |
|---|---|---|---|---|
| Video Discovery | Fetch videos + classify relevant/irrelevant | yt-scraper, video-classifier | topic or URL | `Video[]` + `stop_signal` |
| Strategy Extractor | NotebookLM analysis, 3-round questioning | notebooklm-analyst | `Video[]` | `Strategy[]` (raw YAML) |
| Strategy Processor | Purify, split directions, variants, translate to JSON, auto-fill TODOs | strategy-variants, strategy-translator, todo-review | `Strategy[]` | `Draft[]` |

**Backtesting Agents:**

| Agent | Responsibility | Input | Output |
|---|---|---|---|
| Simple Backtester | Trigger simple backtest via API, interpret 40+ metrics | draft_id, timeframe | `Metrics{}` |
| Complete Backtester | Full backtest + trade log + equity curve analysis | draft_id, timeframe | `Metrics{}` + `Trades[]` |
| Monte Carlo Analyst | Trigger MC sim, interpret distributional stats, assess luck vs skill | draft_id, config | `MCResult{}` + assessment |
| Monkey Tester | Trigger monkey test, interpret p-value, judge edge | draft_id | `MonkeyResult{}` + verdict |
| Stress Tester | Trigger param sweep, interpret robustness score, flag fragile params | draft_id, params? | `StressResult{}` + verdict |

Note: Backtesting agents are **interpreters**, not engines. The worker/engine infrastructure already exists. Agents provide the AI interface on top: trigger via API, wait for completion, interpret results, give verdicts.

**Shared Agents:**

| Agent | Responsibility | Skills Used | Input | Output |
|---|---|---|---|---|
| DB Persistence | Save strategies + drafts, dedup, channel resolution, history logging | db-manager | `Strategy[]` or `Draft[]` | DB confirmation |

### 2.3 AGENT.md Front-Matter Convention

Each agent lives in `.claude/agents/{name}/` with a single file:

```
.claude/agents/
  video-discovery/
    AGENT.md            # Front-matter (metadata) + instructions + behavior
  strategy-extractor/
    AGENT.md
  ...
```

#### Front-Matter Format

Every `AGENT.md` starts with a YAML front-matter block delimited by `---`. This block contains machine-readable metadata that serves as guidance for the Research Manager and for developers reading the file. The CEO does not read front-matter — its routing rules are defined explicitly in CLAUDE.md.

**Example — Video Discovery:**

```yaml
---
name: video-discovery
description: Fetch and classify YouTube videos by topic
domain: research
role: agent
inputs:
  - name: topic
    type: string
    required: true
  - name: max_videos
    type: integer
    default: 10
outputs:
  - name: videos
    type: "Video[]"
  - name: stop_signal
    type: string
    enum: [null, NO_VIDEOS_FOUND, NO_NEW_VIDEOS]
skills_used:
  - yt-scraper
  - video-classifier
dependencies: []
---

# Video Discovery Agent

(rest of AGENT.md instructions here)
```

**Adding a new leaf agent** within an existing Manager's flow = drop a new directory with an `AGENT.md` (including front-matter), then update the Manager's hardcoded sequence in its `AGENT.md` and add a routing rule in `CLAUDE.md`.

### 2.4 Data Flow Examples

#### Research: "research futures"

```
User: "research futures"
  |
  CEO (classifies: topic="futures", domain=research)
  |
  Research Manager (entry: topic -> full pipeline)
  |
  +-> Video Discovery(topic="futures")
  |     -> Video[]
  |
  +-> Strategy Extractor(videos)
  |     -> Strategy[]
  |
  +-> Strategy Processor(strategies)
  |     -> Draft[]
  |
  +-> DB Persistence(drafts)
  |     -> confirmation
  |
  -> Return summary to user
```

#### Research: "here's an idea: buy RSI < 30"

```
User: "here's an idea: buy RSI < 30"
  |
  CEO (classifies: idea="buy RSI < 30", domain=research)
  |
  Research Manager (entry: idea -> skip discovery + extraction)
  |
  +-> Strategy Processor(idea="buy RSI < 30")
  |     -> Draft[]
  |
  +-> DB Persistence(drafts)
  |     -> confirmation
  |
  -> Return summary to user
```

#### Backtesting: "full analysis on ES_RSI_001"

```
User: "full analysis on ES_RSI_001"
  |
  CEO (classifies: backtest, mode=full_analysis, draft_id=ES_RSI_001)
  |
  CEO routes directly to backtesting agents (no Backtesting Manager)
  |
  +-> Complete Backtester(draft_id)
  |     -> Metrics{} + Trades[]
  |
  +-> Monte Carlo Analyst(draft_id)
  |     -> MCResult{} + assessment
  |
  +-> Monkey Tester(draft_id)
  |     -> MonkeyResult{} + verdict
  |
  +-> Stress Tester(draft_id)
  |     -> StressResult{} + verdict
  |
  -> CEO synthesizes all results
  -> Return combined analysis to user
```

---

## 3. Key Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Research Manager is the only Manager; backtesting routes directly from CEO | Research has complex pipeline sequencing that justifies a Manager. Backtesting routing starts as CEO-level rules; promote to a dedicated Manager only if synthesis logic warrants it |
| 2 | Backtesting agents are interpreters, not engines | The worker/engine infrastructure already exists; agents provide the AI interface on top (trigger via API, interpret results, give verdicts) |
| 3 | Strategy Processor bundles variants + translator + todo-review | These 3 steps always run together and share the same data; splitting them adds overhead without reusability benefit |
| 4 | DB Persistence is shared, not per-domain | Both research and backtesting write results; one agent avoids duplication |
| 5 | Session tracking moves to Managers | Agents should not know about sessions; Managers manage lifecycle |
| 6 | Front-matter in AGENT.md replaces separate manifest.yaml | Simpler, fewer files, same information. Metadata lives alongside instructions in a single file |
| 7 | Existing skills remain unchanged | Agents USE skills; the skill layer is stable and tested |
| 8 | CEO = Claude Code main session | The user's Claude Code session serves as the CEO; no separate agent needed. Routing rules live in project `CLAUDE.md`. |
| 9 | CEO routing is explicit rules in CLAUDE.md, not auto-discovery | YAGNI for a single-developer project. A simple rule table is easier to maintain than directory scanning and manifest parsing |
| 10 | Backtesting agents read structured JSON from API responses only | Agents never parse worker stdout directly; all data comes from API response payloads |
| 11 | Long-running ops use a job completion monitor | A one-shot scheduled task polls the API until the job completes, then spawns the interpretation agent and self-removes. Job completion monitor is Phase 5 — a prerequisite for backtesting agents. |
| 12 | Backtesting Manager deferred | Start with CEO-level routing, promote to Manager only if synthesis logic proves complex enough |
| 13 | Job completion monitor is Phase 5, prerequisite for backtesting agents | The async job tracking infrastructure must exist before backtesting agents can wait for worker completion |

---

## 5. Implementation Phases

### Phase 1: Foundation — Front-Matter Convention & Directory Structure

**Goal:** Establish the convention layer that all subsequent phases build on.

**Tasks:**
- Define the AGENT.md front-matter convention (YAML block with: name, description, domain, role, inputs, outputs, skills_used, dependencies)
- Create the `.claude/agents/` directory structure with placeholder `AGENT.md` files (front-matter only) for each planned agent (10 total: 1 manager + 3 research + 5 backtesting + 1 shared)
- Create a template `AGENT.md` showing the front-matter format for future agent authors
- Document existing data formats (Video, Strategy, Draft) as the inter-agent guidance. Point to where they already live in the codebase. No new schemas — agents must conform to existing formats.

**Deliverables:** Convention documentation, 10 AGENT.md files with front-matter, directory structure, data format guidance documentation.
**No code changes** — this is purely the convention layer.

**Acceptance Tests:**
- Every AGENT.md has a valid YAML front-matter block with required fields: name, description, domain, role, inputs, outputs
- Directory structure follows the convention: `.claude/agents/{name}/AGENT.md`

---

### Phase 2: Extract Research Agents from Monolith

**Goal:** Break the research portion of the monolith into 3 standalone agents.

**Tasks:**
- Create **Video Discovery** agent (`AGENT.md` with front-matter) — extract yt-scraper + classifier logic from current `AGENT.md`
- Create **Strategy Extractor** agent (`AGENT.md` with front-matter) — extract notebooklm-analyst logic
- Create **Strategy Processor** agent (`AGENT.md` with front-matter) — extract variants + translator + todo-review logic
- Verify each agent is callable standalone (not just via pipeline)
- Preserve existing skills unchanged — agents reference skills, they don't duplicate them

**Deliverables:** 3 agent directories under `.claude/agents/`, each with `AGENT.md`.
**Key constraint:** The old monolith continues to work during this phase. These agents exist alongside it.

**Acceptance Tests:**
- Standalone: Video Discovery with known topic -> returns `Video[]` with valid structure
- Standalone: Strategy Extractor with known `Video[]` -> returns `Strategy[]` YAML
- Standalone: Strategy Processor with known `Strategy[]` -> returns `Draft[]` JSON with auto-filled fields

---

### Phase 3: Extract Shared Agents

**Goal:** Extract cross-domain capabilities into a shared agent.

**Tasks:**
- Create **DB Persistence** agent — extract all DB operations from current `AGENT.md` (insert_strategy, upsert_draft, add_history, channel resolution)

**Deliverables:** 1 shared agent directory under `.claude/agents/`.
**Key constraint:** This agent is consumed by both research and backtesting domains.

**Note:** TODO resolution is handled by Strategy Processor's `todo-review` step for auto-fill. Fields that cannot be auto-resolved are flagged but do not block the pipeline.

**Acceptance Tests:**
- Standalone: DB Persistence with known `Draft[]` -> records appear in database, deduplication works

---

### Phase 4: Research Manager

**Goal:** Replace the monolithic research pipeline with a proper Manager that sequences the Phase 2-3 agents.

**Tasks:**
- Create **Research Manager** agent that sequences the research pipeline (hardcoded agent sequence in `AGENT.md`)
- Implement 3 entry points (topic/url/idea) with dynamic step selection
- Implement session lifecycle management (create/update/complete)
- Implement early stop signal handling (`NO_VIDEOS_FOUND`, `NO_STRATEGIES_FOUND`)
- Test: run full research pipeline through the new Manager
- Verify all 3 entry points produce correct results

**Deliverables:** Research Manager agent, passing end-to-end tests.
**Key milestone:** After this phase, the research pipeline runs through the new architecture. The old monolith can be bypassed (but is not yet deleted).

**Acceptance Tests:**
- Integration: Topic entry "research futures" -> full pipeline -> drafts in DB
- Integration: URL entry with YouTube link -> skips discovery -> drafts in DB
- Integration: Idea entry "buy RSI < 30" -> skips discovery + extraction -> drafts in DB
- Early stop: Topic with no videos -> returns `NO_VIDEOS_FOUND`, pipeline stops cleanly

---

### Phase 5: Job Completion Monitor

**Goal:** Build the infrastructure for async job tracking. This is a prerequisite for backtesting agents.

**Tasks:**
- API endpoint to submit jobs and return `job_id`
- DB table for job status tracking
- One-shot scheduled task pattern that polls until completion, then spawns interpretation agent and self-removes

This is backend infrastructure work (Python/FastAPI).

**Deliverables:** Job submission API, job status DB table, polling/callback mechanism.

**Acceptance Tests:**
- Submit a job via API -> get `job_id`
- Job completes -> monitor detects completion -> triggers callback -> self-removes

---

### Phase 6: Backtesting Agents — SKETCH

> Will be fully designed after Phase 5 is complete.

**Simple Backtester** — Triggers a simple backtest via API, waits for completion via job monitor, interprets 40+ metrics and presents results with a verdict.

**Complete Backtester** — Full backtest with trade log analysis and equity curve interpretation. Provides deeper analysis than simple mode including per-trade breakdown.

**Monte Carlo Analyst** — Triggers MC simulation, interprets distributional stats (confidence intervals, drawdown distributions), assesses luck vs skill.

**Monkey Tester** — Triggers monkey test (random entry benchmark), interprets p-value, judges whether the strategy has a statistically significant edge.

**Stress Tester** — Triggers parameter sweep, interprets robustness score, flags fragile parameters that cause performance degradation when perturbed.

---

### Phase 7: CEO Routing Rules & Documentation

**Goal:** Add routing rules to the project `CLAUDE.md` so the Claude Code main session can classify user intent and route to the right Manager or backtesting agent. This is NOT about creating a separate agent — the main session IS the CEO.

**Tasks:**
- Add routing rules to project `CLAUDE.md` — intent classification (topic, url, idea, strategy name, backtest request) and dispatch to the appropriate Manager or agent
- Add backtesting routing rules: single test mode routes to one agent, full analysis chains all backtesting agents, CEO handles result synthesis
- Add handling guidance for ambiguous requests (ask clarifying questions)
- Update project documentation (`docs/`) to reflect the new agent architecture

**Deliverables:** Updated project `CLAUDE.md` with routing rules (research + backtesting), updated documentation.

**Acceptance Tests:**
- E2E: "research futures" -> routes to Research Manager
- E2E: "backtest ES_RSI_001" -> routes to backtesting agent(s) directly
- E2E: "here's an idea: buy RSI < 30" -> routes to Research Manager (idea entry)
- E2E: Ambiguous input -> asks clarifying question

---

### Phase 8: Migration & Cleanup

**Goal:** Retire the monolith and finalize the migration.

**Tasks:**
- Retire the old monolithic `AGENT.md` (archive, do not delete, for reference)
- Delete the `/research` skill entirely. Users interact through the CEO which routes to the Research Manager.
- Final documentation pass (`CLAUDE.md`, `docs/`)
- End-to-end test of all entry points through the new architecture
- Verify standalone agent invocation works for each of the 10 agents (1 Manager + 3 research + 5 backtesting + 1 shared)
- Clean up any dead references to the old monolith

**Deliverables:** Fully migrated system, updated documentation, archived monolith.

**Acceptance Tests:**
- All 10 agents callable standalone
- Full research pipeline works end-to-end through CEO
- Old monolith archived, no dead references remain

---

## 6. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Agent context fragmentation — each agent loses context the monolith had | Medium | Medium | Front-matter guidance ensures agents get exactly what they need; Managers pass typed context between agents |
| 2 | Over-engineering — too many agents for the current scale | Low | Medium | Start with research agents (Phases 2-4), validate the architecture before building backtesting agents (Phase 6) |
| 3 | Backtesting agents are thin wrappers with little value | Medium | Low | Their value is interpretation and recommendations, not just API calls; design `AGENT.md` with analytical personality and domain knowledge |
| 4 | Breaking existing research pipeline during migration | Medium | High | Phase 4 replaces the monolith only after all research agents are tested standalone; old `AGENT.md` is kept until Phase 8 |
| 5 | CEO backtesting routing becomes too complex without a Manager | Low | Medium | Start simple; promote to a dedicated Backtesting Manager if synthesis logic proves complex enough |

---

## 7. Open Questions

1. ~~**CEO identity**~~ — **RESOLVED (Decision #8):** The Claude Code main session serves as the CEO. No separate agent needed; routing rules live in project `CLAUDE.md`.
2. ~~**Backtesting data source**~~ — **RESOLVED (Decision #10):** API response. Backtesting agents read structured JSON from API responses only, never parse worker stdout.
3. ~~**Long-running operations**~~ — **RESOLVED (Decision #11):** Job completion monitor (Phase 5). The concrete flow:
   1. CEO calls API -> starts job -> gets `job_id`
   2. CEO creates a job completion monitor (one-shot scheduled task) for `job_id`
   3. Job completion monitor polls API periodically until `status = completed`
   4. On completion -> spawns interpretation agent with results -> self-removes
   This is a one-shot pattern (the monitor removes itself after firing).

---

## 8. Next Steps

**Phases 1-4 can proceed independently** (no external blockers):

1. **Phase 1** — Define the front-matter convention and create all 10 AGENT.md files. This unblocks all subsequent phases.
2. Validate Phase 1 output with a quick review before proceeding.
3. Begin Phase 2 (extract research agents) immediately after Phase 1 approval.
4. Phases 3-4 follow sequentially after Phase 2.

**Phase 5 (Job Completion Monitor)** is backend infrastructure work that can begin anytime after Phase 4 (or in parallel if resources allow).

**Phase 6 (Backtesting Agents)** is blocked on Phase 5. Only a sketch is provided now — will be fully designed after Phase 5 is complete.

**Phase 7 (CEO Routing Rules)** can be done anytime after Phase 4. Now includes backtesting routing since there is no Backtesting Manager.

**Phase 8** (cleanup) runs last, after all other phases are complete.
