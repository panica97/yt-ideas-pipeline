# Metrics & Analysis — Phase 12

**Status:** Planned
**Started:** —
**SDD Change:** backtest-metrics-analysis
**Parent Phase:** Phase 12 from Master Plan

---

## Goal

Define, compute, and display performance metrics from both real and synthetic backtests. This phase transforms raw trade data into actionable insights: P&L curves, risk metrics, and statistical comparisons between real and Monte Carlo results. The goal is to answer "is this strategy worth trading?" with quantitative evidence.

## Sub-phases

| # | Task | Route | SDD Status | Status |
|---|------|-------|------------|--------|
| 1 | Metrics computation engine (P&L, win rate, max drawdown, Sharpe, profit factor, etc.) | /sdd-ff | — | Planned |
| 2 | Metrics data model and storage (per-backtest and aggregate metrics tables) | /sdd-new | — | Planned |
| 3 | Real vs synthetic comparison logic (statistical tests, confidence intervals) | /sdd-ff | — | Planned |
| 4 | API endpoints for metrics (per-strategy, per-backtest, comparison views) | /sdd-new | — | Planned |
| 5 | Frontend metrics dashboard (charts, tables, real vs synthetic overlay) | /sdd-ff | — | Planned |
| 6 | Strategy scoring/ranking (composite score from metrics for quick comparison) | /sdd-new | — | Planned |

## Decisions Log

| Date | Decision | Why | Impact |
|------|----------|-----|--------|
| — | — | — | — |

## SDD Progress

_No SDD phases started yet._

## Notes

- Core metrics to implement:
  - **P&L** (total, per-trade, cumulative curve)
  - **Win rate** (% of profitable trades)
  - **Max drawdown** (largest peak-to-trough decline)
  - **Sharpe ratio** (risk-adjusted return)
  - **Profit factor** (gross profit / gross loss)
  - **Sortino ratio** (downside-risk-adjusted return)
  - **Average trade duration**
  - **Expectancy** (average profit per trade)
- Real vs synthetic comparison should highlight overfitting: if a strategy works on historical but fails on Monte Carlo, it's likely curve-fitted
- Consider percentile-based reporting for Monte Carlo results (e.g., median Sharpe across N simulations, 5th percentile drawdown)
- Charts: equity curve, drawdown chart, trade distribution histogram, MC fan chart
- Strategy ranking enables quick prioritization of which strategies to investigate further
