# Simple Backtesting — Phase 10

**Status:** Done
**Started:** 2026-03-22
**SDD Change:** simple-backtesting
**Parent Phase:** Phase 10 from Master Plan

---

## Goal

Integrate the existing backtest engine from ops-worker-v0.1.0 (packages/backtest-engine + ibkr-core) into IRT. The project already has a complete, working engine that iterates over candles, evaluates entry/exit conditions, and tracks trades. The work here is about building the bridge between IRT (API + frontend + database) and the engine — a worker script that polls for jobs, runs backtests, and stores results. This follows the same pattern as the Operations Platform: worker runs on the host machine, uses engine packages in-place. This enables quantitative validation of strategies discovered by the research pipeline, using historical futures data already available locally.

## Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Data model: backtest_jobs + backtest_results tables + Alembic migration + Pydantic schemas | /sdd-new | — | Done |
| 2 | Worker script: Python polling loop (polls IRT API for pending jobs, exports draft JSON to temp file, runs engine subprocess, parses --metrics-json output, posts results back to API) | /sdd-ff | — | Done |
| 3 | API endpoints: trigger backtest, check job status, get results, cancel/delete | /sdd-new | — | Done |
| 4 | Frontend: BacktestPanel component in draft view (trigger with date range, poll status, display metrics) | /sdd-new | — | Done |

## Decisions Log

| Date | Decision | Why | Impact |
|------|----------|-----|--------|
| 2026-03-22 | Worker runs on host machine, not Docker | Matches ops-platform pattern: worker.py runs locally, uses same venv and engine packages from ops-worker-v0.1.0 | No new Dockerfile needed; worker points to existing backtest-engine + ibkr-core via REPO_ROOT |
| 2026-03-22 | DB-based job queue (backtest_jobs table) | Lightweight, no extra infra (no Redis), PostgreSQL already in stack | New table + Alembic migration |
| 2026-03-22 | Results in PostgreSQL (backtest_results table) | Queryable from dashboard, keeps all data in one place | New table + Alembic migration |
| 2026-03-22 | Worker accesses hist data directly from host filesystem | Worker runs on host, no Docker volume mount needed — path configured via env var or .env file | Worker .env points to C:\Users\Pablo Nieto\Desktop\PopFinance\data_futuros |
| 2026-03-22 | Export drafts.data JSONB to temp JSON for engine | Engine expects JSON files on disk via ibkr-core StratOBJ loader, drafts.data already matches ibkr-core schema exactly | Bridge service needed |
| 2026-03-22 | Symbols stored with @ prefix (@MNQ, @ES) | Engine searches for {symbol}_1M_edit.txt, files on disk use @ prefix — no mapping needed | Drafts must use @-prefixed symbols; bridge passes symbol as-is to engine |
| 2026-03-22 | Metrics-only for Phase 10 (no individual trades) | --metrics-json only outputs summary metrics; trade extraction adds complexity | Results table stores summary metrics only; trade-level detail deferred to future phase |
| 2026-03-22 | Engine packages used in-place from ops-worker-v0.1.0 | Same pattern as ops-platform: engine is sibling of worker in same repo, shared venv | Worker references packages/backtest-engine and packages/ibkr-core from ops-worker-v0.1.0 path |
| 2026-03-22 | Bridge prepends @ to symbol if missing | Engine expects @MNQ_1M_edit.txt but drafts store MES without @ | bridge.py adds @ prefix before writing temp JSON |
| 2026-03-22 | Frontend uses engine metric field names (total_pnl not net_pnl) | Engine returns total_pnl, win_rate as percentage, trade_count — not the names originally assumed | BacktestPanel uses safe fallbacks with ?? 0 |

## SDD Progress

| Phase | Status | Artifact | Notes |
|-------|--------|----------|-------|
| Proposal | Done | openspec/changes/simple-backtesting/proposal.md | Intent, scope, 5 risks identified |
| Specs | Done | openspec/changes/simple-backtesting/specs/ (4 domains) | 90 requirements, 43 scenarios across data-model, worker, api, frontend |
| Design | Done | openspec/changes/simple-backtesting/design.md | 6 architecture decisions, 11 new files, 4 modified |
| Tasks | Done | openspec/changes/simple-backtesting/tasks.md | 18 tasks in 5 phases |
| Apply | Done | Phase 1-4 implemented | 3 bugs found and fixed during verification |
| Verify | Done | Playwright + manual worker testing | All endpoints, frontend, and worker verified |

## Notes

- Engine data format is compatible: CSV files like @MNQ_1M_edit.txt with Date,Time,Open,High,Low,Close columns
- Engine resamples 1-min bars to any timeframe (4h, 1d, etc.)
- Available symbols: @ES, @NQ, @MNQ, @MES, @MGC, @GC
- drafts.data JSONB already matches ibkr-core schema (strat_code, ind_list, long_conds, short_conds, etc.)
- Engine supports --metrics-json flag for machine-readable output
- Engine supports single mode (one strategy) and portfolio mode (multiple strategies)
- Strategies must have status "validated" and todo_count = 0 to be backtestable
- RESOLVED: Engine maps symbol directly to file ({symbol}_1M_edit.txt) — symbols must include @ prefix
- RESOLVED: --metrics-json outputs summary metrics only (total_pnl, trade_count, win_rate, sharpe_ratio, max_drawdown, initial_equity, final_equity) — individual trades deferred
- RESOLVED: Engine packages used in-place from ops-worker-v0.1.0/packages/ — same pattern as Operations Platform. No copy needed.
- Worker runs outside Docker on host machine, same as ops-platform pattern. Polls IRT API for jobs, runs backtest-engine via subprocess, posts results back.
- KNOWN ISSUE: First backtest (strat_code 9007 on MES, 2023-01-03 to 2026-03-22) produced 0 trades. **Root cause identified** — see Phase 10.1 below.
- Bugs fixed during verification: (1) 401 auth — worker needed API key header, (2) FileNotFoundError — symbol @ prefix mapping, (3) toFixed crash — metric field name mismatch

---

## Phase 10.1 — Fix Backtest Condition Format

**Status:** Done
**Completed:** 2026-03-23
**Commit:** a67a819
**Priority:** HIGH — blocks all backtesting
**Parent Phase:** Phase 10.1 from Master Plan

### Goal

Fix the backtest condition format mismatch that causes the engine to produce 0 trades silently. The strategy-translator puts shift notation `(N)` inside `cond` strings (e.g., `"LOW_4h(1) < LOW_4h(2)"`), but the engine's parser expects bare indicator names only (e.g., `"LOW_4h < LOW_4h"`). Shifts must live exclusively in `shift_1`/`shift_2` fields, as defined in STRATEGY_FILE_REFERENCE.md.

**Root Cause:** Strategy 9007's backtest produced 0 trades because `cond.split()` produces tokens like `"LOW_4h(1)"` instead of `"LOW_4h"`, causing column lookups to fail silently (NaN fill → all comparisons False → 0 trades).

### Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Fix strategy-translator skill: remove shift notation from cond string instructions in SKILL.md, translation-rules.md, and schema.json. Cond must use bare indicator names; shifts only in shift_1/shift_2. | quick fix | — | Done |
| 2 | Fix frontend condition display: update ConditionBlock in ConditionsSection.tsx to render shift notation visually when shift_1/shift_2 are present, even though stored cond uses bare names. | quick fix | — | Done |
| 3 | Fix existing drafts in DB: create Alembic migration or script to strip `(N)` suffixes from cond strings in data->'long_conds', data->'short_conds', and data->'exit_conds' JSONB arrays. | quick fix | — | Done |

### Notes

- This is a hotfix inserted after Phase 10 completion to unblock backtesting
- All 3 tasks are independent quick fixes — no SDD overhead needed
- After completion, re-run the strat_code 9007 backtest to verify trades are generated

---

## Phase 10.2 — Research Pipeline Flexibility

**Status:** Done
**Completed:** 2026-03-23
**Commits:** fd5481d, 0d1788c
**Priority:** HIGH — frontend is unusable without this for non-standard pipeline entry points
**Parent Phase:** Phase 10.2 from Master Plan
**Depends on:** Phase 10.1

### Goal

Make the research pipeline produce complete frontend-visible output regardless of entry point. Whether the input is a topic, a video URL, or a raw idea, the pipeline must always create: research sessions, properly linked history records, parent strategy records, and drafts.

Currently, session tracking, history linking, and parent strategy creation only work when the full pipeline runs from step 0 (yt-scraper). When steps are skipped (e.g., single video input), the downstream tracking breaks — the frontend shows nothing.

### Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Session tracking for all entry points: the research agent must call `create_session()` at pipeline start and `complete_session()` at pipeline end, regardless of which steps are skipped. Update `.claude/agents/research/AGENT.md` to make session tracking mandatory and independent of pipeline steps. `tools/db/research_repo.py` already has the functions — they just need to be called consistently. | SDD | — | Done |
| 2 | research_history linking for all entry points: when a video URL is provided directly (no yt-scraper), the pipeline must still resolve or create the topic and channel references. For a direct video URL: extract channel info from video metadata (yt-dlp provides this), find or create the channel record, and link it. For a topic: use the existing topic record. For a raw idea (no video): create a history entry with a synthetic source. Ensure `topic_id` and `channel_id` are never NULL in `research_history`. | SDD | — | Done |
| 3 | Parent strategy creation from drafts: the db-manager must create parent `strategy` records when saving drafts. Each unique "parent strategy" (from strategy-variants) should map to one strategy record. Drafts link to their parent strategy via foreign key. This makes the Strategies page show strategies with their draft variants underneath. Update `.claude/skills/db-manager/SKILL.md` to include this step. | SDD | — | Done |

### Notes

- All 3 tasks routed through SDD due to cross-cutting scope across agent, skills, and DB layer
- The DB schema and API endpoints already exist; the gap is in how the research agent and skills call them depending on entry point
- Root cause: research pipeline was built assuming full pipeline execution from yt-scraper; alternative entry points (video URL, raw idea) skip steps that create the relational scaffolding the UI needs
- After completion, test all three entry points (topic, video URL, raw idea) and verify History and Strategies pages populate correctly for each

---

## Phase 10.3 — Backtest Result View

**Status:** Done
**Completed:** 2026-03-23
**Commit:** e21534e
**Priority:** MEDIUM — improves backtest usability
**Parent Phase:** Phase 10.3 from Master Plan
**Depends on:** Phase 10

### Goal

Improve the backtest results display in the frontend. Replace less useful metric cards with more meaningful ones (Return/Drawdown ratio, Max DD %), and add a toggleable PnL equity curve chart for visual analysis of strategy performance over time.

### Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Replace Net PnL metric card with Return/Drawdown ratio (return % divided by max drawdown %). Compute on the frontend from existing metrics (total_pnl, initial_equity, max_drawdown). | quick fix | — | Done |
| 2 | Replace Max Drawdown (absolute) card with Max Drawdown % (percentage of account). Compute as max_drawdown / initial_equity * 100. | quick fix | — | Done |
| 3 | Add PnL equity curve chart (line chart of cumulative PnL over time). Hidden by default with a toggle button to show/hide. May require the engine to return equity curve data points in the metrics JSONB, or compute from trades list on the frontend. | quick fix | — | Done |

### Files to Modify

- `frontend/src/components/strategies/BacktestPanel.tsx` — metric cards and new chart component
- `frontend/src/types/backtest.ts` — type updates if equity curve data is added to metrics

### Notes

- Return/Drawdown ratio = (total_pnl / initial_equity * 100) / (max_drawdown / initial_equity * 100), simplifies to total_pnl / max_drawdown
- Max DD % = max_drawdown / initial_equity * 100
- Equity curve data may need to come from the engine (array of cumulative PnL at each trade close) or be computed from the trades list if individual trades are available
- If engine changes are needed, the worker and bridge may also need updates to pass through equity curve data
- Chart library TBD — consider lightweight option (e.g., recharts, already common in React projects)

---

## Phase 10.4 — Backtest UI Cleanup

**Status:** Planned
**Priority:** MEDIUM — UI polish for backtest launch flow
**Parent Phase:** Phase 10.4 from Master Plan
**Depends on:** Phase 10

### Goal

Clean up the backtest launch UI. Remove the timeframe selector from the backtest launch form (the timeframe is determined by the strategy JSON's `primary_timeframe`, so letting the user pick a different one is misleading). Add backtest mode selection buttons when the backtest panel opens: "Simple Backtest" (triggers the current backtest flow) and "Complete Backtest" (disabled placeholder for a future, more advanced backtesting mode).

### Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Remove the timeframe selector from the backtest launch form. The engine already reads `primary_timeframe` from the strategy JSON — the UI dropdown is redundant and misleading. | quick fix | — | Planned |
| 2 | Add backtest mode selection: when the backtest panel opens, show two mode buttons — "Simple Backtest" (triggers the current backtest flow) and "Complete Backtest" (disabled placeholder for a future plan). | quick fix | — | Planned |

### Files to Modify

- `frontend/src/components/strategies/BacktestPanel.tsx` — remove timeframe selector, add mode buttons

### Notes

- The timeframe selector currently lets users pick a timeframe that may conflict with the strategy's `primary_timeframe`, leading to confusion
- "Complete Backtest" mode is a placeholder — it should be visually present but disabled with a tooltip like "Coming soon"
- This prepares the UI for a future advanced backtesting mode (e.g., walk-forward analysis, multi-timeframe, or Monte Carlo)

---

## Interim Bugfix — TODO Counter (2da3ded)

Between Phase 10.2 and 10.3, a bugfix was committed to detect `_TODO` values nested inside arrays in the todo counter. This was not a planned sub-phase but fixes a bug where nested TODO markers were not counted, causing strategies to appear ready for backtesting when they still had incomplete fields.
