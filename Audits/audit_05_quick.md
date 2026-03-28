# Audit 05 (Quick) — Monte Carlo Frontend Code

**Date:** 2026-03-28
**Scope:** `BacktestReportDrawer.tsx`, `BacktestPanel.tsx` — Monte Carlo UI code
**Auditor:** Claude (automated)
**Findings:** 12

---

## Findings

### MEDIUM

#### M-01: `buildHistogramBins` uses O(n*bins) filter — quadratic on large raw_metrics arrays

**File:** `BacktestReportDrawer.tsx:332`
**Description:** The histogram builder calls `values.filter(v => v >= binStart && v < binEnd)` for each of 20 bins. With 1000+ paths, each having raw arrays, this is O(n * bins) per histogram (4 histograms total). Should use a single-pass bucket assignment instead.
**Severity:** MEDIUM
**Impact:** Noticeable lag when rendering MC report with large path counts (>500).

#### M-02: `Math.min(...values)` / `Math.max(...values)` can throw on very large arrays

**File:** `BacktestReportDrawer.tsx:323-324`
**Description:** Spread into `Math.min`/`Math.max` creates N arguments on the call stack. For >~65K values, this throws a "Maximum call stack size exceeded" error. With `n_paths=10000`, raw arrays could have 10K elements.
**Severity:** MEDIUM
**Impact:** Runtime crash if user runs MC with high path count.

#### M-03: `percentileRank` uses O(n) filter per metric row — repeated 6 times

**File:** `BacktestReportDrawer.tsx:344-348`
**Description:** `MCScorecard` calls `percentileRank` for each of 6 metric rows, each filtering the entire raw array. Should precompute or use sorted binary search.
**Severity:** MEDIUM
**Impact:** Redundant computation on every render; minor with 1K paths, noticeable with 10K.

#### M-04: Unsafe double cast `as unknown as MonteCarloMetrics` in drawer

**File:** `BacktestReportDrawer.tsx:1162`
**Description:** `job?.result?.metrics as unknown as MonteCarloMetrics` bypasses all type checking. If the backend returns unexpected shape, components downstream will crash with unclear errors. Should validate shape at the boundary (runtime type guard or Zod).
**Severity:** MEDIUM
**Impact:** Silent type mismatches propagate deep into MC report components, causing confusing runtime errors.

#### M-05: `Number(mc.total_pnl?.median ?? mc.total_pnl?.p50 ?? undefined)` produces NaN silently

**File:** `BacktestReportDrawer.tsx:594-597`
**Description:** In `MCDistributionsGrid`, the fallback `?? undefined` means `Number(undefined)` returns `NaN`. The `isNaN` check catches it, but this pattern is fragile and repeated 4 times. Should use explicit null checks.
**Severity:** MEDIUM
**Impact:** Fragile code; if downstream components don't guard NaN, visual bugs appear.

#### M-06: Fan chart Area stacking does not produce correct visual bands

**File:** `BacktestReportDrawer.tsx:778-784`
**Description:** The fan chart uses separate `stackId` values for P5/P95 and no stacking for P25/P75. Recharts `Area` with stacking expects cumulative values — raw percentile values will overlap rather than form proper bands. The visual output may not accurately represent the P5-P95 and P25-P75 ranges.
**Severity:** MEDIUM
**Impact:** Misleading visualization — bands may not reflect actual percentile ranges.

### LOW

#### L-01: `deleteMutation` has no `onError` handler in BacktestPanel

**File:** `BacktestPanel.tsx:404-409`
**Description:** Delete mutation silently swallows errors. User gets no feedback if deletion fails. Already flagged in audit_02 (M-11) but still open.
**Severity:** LOW (duplicate of audit_02 #11)
**Impact:** Silent failure on delete.

#### L-02: Hardcoded `nPaths=1000` and `fitYears=10` defaults

**File:** `BacktestPanel.tsx:371-372`
**Description:** Default values for Monte Carlo config are hardcoded in component state. Should come from a config constant or user preferences, especially if sensible defaults change per instrument.
**Severity:** LOW
**Impact:** Not configurable without code change.

#### L-03: Hardcoded max limits `10000` / `50` only enforced client-side

**File:** `BacktestPanel.tsx:549, 559`
**Description:** HTML `max` attribute on inputs for nPaths (10000) and fitYears (50). These are only client-side constraints — the backend should also enforce limits to prevent resource exhaustion.
**Severity:** LOW
**Impact:** Bypassing UI (API call directly) could run expensive MC simulations.

#### L-04: Scatter chart renders all N data points without sampling

**File:** `BacktestReportDrawer.tsx:634-642`
**Description:** `MCScatterWinRateVsPF` plots every path as a scatter point. With 1000+ paths, Recharts renders 1000+ SVG circles, which is sluggish. Should sample or aggregate (e.g., max 200 points).
**Severity:** LOW
**Impact:** Slow rendering with high path counts.

#### L-05: Price paths chart renders up to 30 `<Line>` components

**File:** `BacktestReportDrawer.tsx:895-909`
**Description:** `MCPricePaths` renders up to 30 separate `<Line>` elements, each with potentially thousands of data points. Recharts creates individual SVG paths for each. With long time series, this could cause performance issues.
**Severity:** LOW
**Impact:** Potential DOM bloat and slow rendering.

#### L-06: `MetricCard` component duplicated across both files

**File:** `BacktestPanel.tsx:75-82`, `BacktestReportDrawer.tsx:66-73`
**Description:** Identical `MetricCard` component defined in both files. Should be extracted to a shared component.
**Severity:** LOW
**Impact:** Code duplication; divergence risk.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 0     |
| MEDIUM   | 6     |
| LOW      | 6     |
| **Total** | **12** |

### Key Themes

1. **Performance with large path counts (M-01, M-02, M-03, L-04, L-05):** Multiple O(n) or O(n*k) operations on raw_metrics arrays. Histogram binning is quadratic. Scatter/price charts render excessive SVG elements. These become real issues at n_paths > 500.

2. **Type safety (M-04, M-05):** The `as unknown as` double cast and `Number(undefined)` patterns bypass TypeScript's safety net. A runtime type guard at the API boundary would catch backend mismatches early.

3. **Visual accuracy (M-06):** Fan chart Area stacking needs review — Recharts stacking semantics may not produce correct percentile bands with raw values.

4. **Minor (L-01, L-02, L-03, L-06):** Duplicate code, missing error handlers, hardcoded defaults — standard cleanup items.
