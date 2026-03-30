# Master Plan

**Project:** IRT (Ideas Research Team)
**Created:** 2026-03-22
**Last Updated:** 2026-03-30
**Current Phase:** Phase 13 — Metrics & Analysis
**Status:** Idle

---

## Phase Overview

| # | Phase | Description | Priority | Dependencies | Route | Status |
|---|-------|-------------|----------|--------------|-------|--------|
| 1 | Project Foundation | Initial setup, Docker, multi-agent architecture | HIGH | — | — | Done |
| 2 | Research Pipeline | Skills orchestration, NotebookLM, yt-scraper | HIGH | Phase 1 | — | Done |
| 3 | Frontend Dashboard | React + FastAPI + PostgreSQL web app | HIGH | Phase 2 | — | Done |
| 4 | Idea Validation Flow | Video classifier, 3-status validation, draft proposals | HIGH | Phase 3 | /sdd-ff | Done |
| 5 | Strategy Pipeline Refinement | DraftViewer, translator rewrite, strategy-variants skill | HIGH | Phase 4 | — | Done |
| 6 | Instruments Reference Table | Full CRUD backend + frontend for instruments | MEDIUM | Phase 3 | — | Done |
| 7 | UX Polish & Editing | TODO fill skill, Obsidian theme, inline JSON editor | MEDIUM | Phase 5 | /sdd-ff | Done |
| 8 | i18n & Symbol Selector | English translation, symbol dropdown, indicators table | MEDIUM | Phase 7 | /sdd-ff | Done |
| 9 | Audit & Hardening | Full codebase audit, 29 fixes, pagination | HIGH | Phase 8 | — | Done |
| 10 | Simple Backtesting | Backtest engine for validated strategies using Docker worker | HIGH | Phase 9 | /sdd-ff | Done |
| 10.1 | Fix Backtest Condition Format | Fix cond format mismatch causing 0 trades — strip shift notation from cond strings | HIGH | Phase 10 | quick fix | Done |
| 10.2 | Research Pipeline Flexibility | Make pipeline produce complete frontend-visible output regardless of entry point (topic, video URL, or raw idea) | HIGH | Phase 10.1 | SDD | Done |
| 10.3 | Backtest Result View | Improve backtest results display — Return/Drawdown ratio, Max DD %, toggleable equity curve chart | MEDIUM | Phase 10 | quick fix | Done |
| 10.4 | Backtest UI Cleanup | Remove timeframe selector (determined by strategy JSON), add Simple/Complete backtest mode buttons | MEDIUM | Phase 10 | quick fix | Done |
| 11 | Multi-Timeframe Complete Backtest | Complete backtest mode with trade capture, timeframe remapping, debug save, and full-screen report drawer | HIGH | Phase 10.4 | /sdd-new | Done |
| 12.2 | Synthetic Data (Monte Carlo) | Generate synthetic price data to test strategy robustness | HIGH | Phase 12.1 | /sdd-ff | Done |
| 12.3 | Data Info | Scan worker historical data, display per-symbol date ranges in Instruments table | HIGH | Phase 12.2 | /sdd-new | Done |
| 12.1 | Worker Unification | Copy backtest-engine + ibkr-core from Ops Platform into IRT/packages/, create project venv, update worker to use local engine. Make IRT fully self-contained with zero Ops Platform dependency | HIGH | Phase 11 | /sdd-new | Done |
| 12.4 | Monkey Test | Statistical robustness test: random entries on real OHLC to validate strategy edge via p-value | HIGH | Phase 12.3 | /sdd-new | design | Done |
| 13 | Metrics & Analysis | Compute and compare metrics from real and synthetic backtests | HIGH | Phase 12.3 | /sdd-ff | Planned |
| 14 | Worker Dockerization | Containerize the backtest worker for VPS deployment. Dockerfile with Python 3.12, pandas, pyarrow. Mount historical data and engine as volumes. Add worker service to docker-compose. | MEDIUM | Phase 11 | /sdd-new | Planned |

---

## Progress Summary

| Metric | Count |
|--------|-------|
| Total phases | 20 |
| Completed | 19 |
| In Progress | 0 |
| Planned | 1 |

---

## Phase History

| Date | Phase | Action | Notes |
|------|-------|--------|-------|
| 2026-03-06 | Phase 1 | Completed | Initial commit through Docker + multi-agent restructure |
| 2026-03-09 | Phase 2 | Completed | /research orchestration, notebooklm skill, docs |
| 2026-03-15 | Phase 3 | Completed | React dashboard, FastAPI, research-centric navigation |
| 2026-03-16 | Phase 4 | Completed | SDD: idea-validation-flow. Video classifier, 3-status flow |
| 2026-03-21 | Phase 5 | Completed | DraftViewer, condition display fixes, variants skill |
| 2026-03-21 | Phase 6 | Completed | Instrument model, repo, service, router, frontend CRUD |
| 2026-03-21 | Phase 7 | Completed | SDD: inline-json-editor. TODO fill, Obsidian theme |
| 2026-03-22 | Phase 8 | Completed | SDD: symbol-selector. i18n to English, indicators table |
| 2026-03-22 | Phase 9 | Completed | 30-finding audit, 29 resolved, pagination added |
| 2026-03-22 | Phase 10 | Completed | Backtest engine integration: worker, API, frontend. 3 bugs fixed during verification. |
| 2026-03-23 | Phase 10.1 | Created | Hotfix: cond format mismatch causes 0 trades — shift notation in cond strings breaks engine parser |
| 2026-03-23 | Phase 10.2 | Created | Research Pipeline Flexibility: make pipeline produce complete frontend-visible output (sessions, history, parent strategies) regardless of entry point (topic, video URL, raw idea) |
| 2026-03-23 | Phase 10.1 | Completed | Hotfix: stripped (N) shift notation from cond strings, added frontend shift display (a67a819) |
| 2026-03-23 | Phase 10.2 | Completed | Research pipeline flexibility + documentation + todo-review skill (fd5481d, 0d1788c) |
| 2026-03-23 | — | Bugfix | Fix TODO counter: detect _TODO values nested inside arrays (2da3ded) |
| 2026-03-23 | Phase 10.3 | Completed | Backtest Result View: Return/DD ratio, Max DD %, equity curve chart (e21534e) |
| 2026-03-23 | Phase 10.4 | Completed | Backtest UI Cleanup: remove timeframe selector, add Simple/Complete mode buttons (a3643c8) |
| 2026-03-24 | Phase 11 | Created | Multi-Timeframe Complete Backtest: 6 sub-phases from approved design doc |
| 2026-03-24 | Phase 12-13 | Renumbered | Synthetic Data (Monte Carlo) 11→12, Metrics & Analysis 12→13 |
| 2026-03-25 | Phase 11 | Completed | Multi-Timeframe Complete Backtest validated |
| 2026-03-25 | Phase 12.1 | Redesigned | Scope expanded: internalize engine + ibkr-core into IRT (was: port parallel orchestrator only). Parallel orchestrator already implemented. |
| 2026-03-25 | Phase 12.1 | Started | Copy engine packages, create venv, update worker config |
| 2026-03-25 | Phase 12.1 | Completed | Engine + ibkr-core internalized, parallel orchestrator, venv setup, SL/TP None fixes in 6 engine files |
| 2026-03-28 | Phase 12.2 | Completed | Synthetic Data (Monte Carlo): MC engine internalized, backend schema + migration, worker MC mode, frontend MC UI + report (fan chart, histograms, scorecard, risk table, scatter, drawdown cone, price paths, confidence intervals) |
| 2026-03-29 | Phase 12.2 | Bugfixes | Fix UnicodeEncodeError on Windows cp1252, include baseline_metrics in MC JSON output, MC scorecard Actual reads real baseline instead of P50, remove color from Actual/Rank columns |
| 2026-03-29 | Phase 12.3 | Created | Data Info: scan worker historical data, display per-symbol date ranges in Instruments table |
| 2026-03-29 | Phase 12.3 | Completed | ScanJob model + migration, API scan endpoints, worker data-info scanner, frontend Scan Data button + date columns, backtest date picker constrained to available data range |
| 2026-03-29 | Phase 12.4 | Created | Monkey Test: random-entry statistical test from approved design doc |
| 2026-03-30 | Phase 12.4 | Completed | Monkey Test: core package, worker/API integration, frontend UI + report (a6e7012) |
| 2026-03-30 | Phase 12.4 | Bugfix | Fix monkey test report: read metrics flat instead of nested .monkey key (9f58262) |
| 2026-03-30 | Phase 12.4 | Docs | Add Monkey Test to backtesting documentation — section 6 with 8 subsections (0768410) |
