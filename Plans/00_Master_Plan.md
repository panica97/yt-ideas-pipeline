# Master Plan

**Project:** IRT (Ideas Research Team)
**Created:** 2026-03-22
**Last Updated:** 2026-03-22
**Current Phase:** Phase 10 — Simple Backtesting (Done)
**Status:** In Progress

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
| 11 | Synthetic Data (Monte Carlo) | Generate synthetic price data to test strategy robustness | HIGH | Phase 10 | /sdd-ff | Planned |
| 12 | Metrics & Analysis | Compute and compare metrics from real and synthetic backtests | HIGH | Phase 11 | /sdd-ff | Planned |

---

## Progress Summary

| Metric | Count |
|--------|-------|
| Total phases | 12 |
| Completed | 10 |
| In Progress | 0 |
| Planned | 2 |

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
