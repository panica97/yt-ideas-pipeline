# Audit 07 — Phase 12.4: Monkey Test

**Date:** 2026-04-02
**Scope:** Monkey Test — core package, worker engine, API schema, frontend report component
**Auditor:** Claude (automated)
**Findings:** 12

---

## Files Reviewed

- `packages/monkey-test/runner.py` — Main orchestrator + CLI
- `packages/monkey-test/generator.py` — Random entry generation
- `packages/monkey-test/simulator.py` — Single simulation executor
- `packages/monkey-test/metrics.py` — Performance metrics computation
- `packages/monkey-test/aggregator.py` — Result aggregation + histogram
- `packages/monkey-test/extractor.py` — Trade parameter extraction
- `packages/monkey-test/config.py` — Configuration dataclass
- `worker/monkey_engine.py` — Worker subprocess runner
- `worker/executor.py` — Job executor (monkey branch)
- `api/models/schemas/backtest.py` — Pydantic schemas (monkey fields)
- `api/alembic/versions/015_add_monkey_test_params_to_backtest_jobs.py` — Migration
- `frontend/src/components/strategies/MonkeyTestReport.tsx` — Report UI
- `frontend/src/types/backtest.ts` — MonkeyTestMetrics TypeScript type

---

## Findings

### MEDIUM

#### M-01: `buildHistogramBins` uses O(n*bins) filter — same pattern as audit_05 M-01

**File:** `frontend/src/components/strategies/MonkeyTestReport.tsx:17-37`
**Description:** The histogram builder calls `values.filter(v => v >= binStart && v < binEnd)` for each of 20 bins. With 1000+ simulations this creates O(n * bins) iterations. Same quadratic pattern flagged in audit_05 for Monte Carlo.
**Severity:** MEDIUM
**Impact:** Noticeable lag when rendering monkey test report with high simulation counts.

#### M-02: `Math.min(...values)` / `Math.max(...values)` stack overflow risk

**File:** `frontend/src/components/strategies/MonkeyTestReport.tsx:19-20`
**Description:** Spread into `Math.min`/`Math.max` creates N arguments on the call stack. With n_simulations=5000+, the distribution arrays could exceed the ~65K argument limit and throw "Maximum call stack size exceeded".
**Severity:** MEDIUM
**Impact:** Runtime crash with high simulation counts.

#### M-03: Unsafe `as unknown as MonkeyTestMetrics` double cast

**File:** `frontend/src/components/strategies/BacktestReportDrawer.tsx:916`
**Description:** The monkey metrics are obtained via `job?.result?.metrics as unknown as MonkeyTestMetrics`. This bypasses all type checking. If the backend returns an unexpected shape (e.g., missing `distribution` or `real_strategy`), components will crash with unhelpful errors.
**Severity:** MEDIUM
**Impact:** Silent type mismatches propagate into report components, causing confusing runtime errors.

#### M-04: `PValueBadge` crashes if `p_value` or `percentile` is null/undefined

**File:** `frontend/src/components/strategies/MonkeyTestReport.tsx:64-104`
**Description:** The `PValueBadge` component calls `pValue.toFixed(4)` and `percentile.toFixed(1)` directly. The `MonkeyTestMetrics` type declares `percentile: number` and `p_value: number` as non-nullable, but the backend aggregator can return `null` for both when there are zero simulations or empty arrays (lines 92-93 of `aggregator.py`). The TypeScript type is wrong — it should be `number | null`.
**Severity:** MEDIUM
**Impact:** Runtime crash (`Cannot read property 'toFixed' of null`) when monkey test has edge-case results.

#### M-05: Generator `sample_size = n_trades * 3` may be insufficient for high-overlap scenarios

**File:** `packages/monkey-test/generator.py:53`
**Description:** The random entry generator samples `min(n_trades * 3, last_valid + 1)` candidate entries and then greedy-filters for overlaps. With long holding periods and many trades, the 3x buffer can be insufficient, resulting in significantly fewer trades placed than requested. The warning is emitted post-hoc but the simulation proceeds with reduced trade count, potentially skewing the distribution comparison.
**Severity:** MEDIUM
**Impact:** Monkey test comparison may be unfair — if random simulations consistently place fewer trades than the real strategy, the p-value is biased.

#### M-06: `_sanitize_for_json` duplicated in `runner.py` and `aggregator.py`

**File:** `packages/monkey-test/runner.py:50-63`, `packages/monkey-test/aggregator.py:123-136`
**Description:** The exact same `_sanitize_for_json` function is copy-pasted in both files. Should be in a shared utility module.
**Severity:** MEDIUM
**Impact:** Code duplication; divergence risk if one copy is updated but not the other.

### LOW

#### L-01: `return_dd` can be `float('inf')` and break aggregation

**File:** `packages/monkey-test/metrics.py:38-42`
**Description:** When `max_drawdown` is 0 and `net_profit > 0`, `return_dd` is set to `float('inf')`. The aggregator sanitizes inf values (line 64 of aggregator.py), but these paths are excluded from the percentile calculation, subtly reducing the effective sample size.
**Severity:** LOW
**Impact:** Inf values are handled but excluded from distributions, slightly biasing percentile calculation.

#### L-02: `extractor.py` uses both `polars` and `pandas` fallback but `_read_parquet` is never called in the main flow

**File:** `packages/monkey-test/extractor.py:15-26`
**Description:** The `_read_parquet` function and `extract_from_parquet` convenience wrapper are defined but never used in the monkey test flow. The runner gets trades directly from `bt_result.get("trades", [])` as dicts. This is dead code.
**Severity:** LOW
**Impact:** No runtime impact; dead code creates confusion.

#### L-03: No input validation on `n_simulations` or `monkey_mode` at API level

**File:** `api/models/schemas/backtest.py:22-23`
**Description:** `n_simulations` is `Optional[int]` with no min/max constraint, and `monkey_mode` is `Optional[str]` with no validation that it's "A" or "B". A malicious or buggy client could request `n_simulations=1000000` or `monkey_mode="Z"`.
**Severity:** LOW
**Impact:** Resource exhaustion via API call with absurdly high simulation count; invalid mode would fail at the runner level with a less helpful error.

#### L-04: Worker monkey engine `--save` flag always passed

**File:** `worker/monkey_engine.py:94`
**Description:** The `--save` flag is always included in the subprocess command, which writes results to `monkey_results/` in the current working directory. These files are never cleaned up and accumulate over time.
**Severity:** LOW
**Impact:** Disk space leak from accumulated result files.

#### L-05: Monkey test progress callback only runs after subprocess completes

**File:** `worker/monkey_engine.py:112-121`
**Description:** Progress markers are parsed from `result.stdout` after `subprocess.run()` finishes (it uses `capture_output=True`). This means the `progress_callback` is called retroactively all at once, not in real-time. The progress parameter is effectively useless for live progress tracking.
**Severity:** LOW
**Impact:** No real-time progress reporting for monkey tests; the UI shows no intermediate progress.

#### L-06: `computeP50` function uses ceiling-based index which may be off-by-one

**File:** `frontend/src/components/strategies/MonkeyTestReport.tsx:39-43`
**Description:** `Math.ceil(0.5 * sorted.length) - 1` computes the median index. For even-length arrays, this returns the lower-middle element rather than averaging the two middle elements. This is a minor inaccuracy in the P50 display.
**Severity:** LOW
**Impact:** Minor numerical difference in displayed P50 values; cosmetic.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 0     |
| MEDIUM   | 6     |
| LOW      | 6     |
| **Total** | **12** |

### Key Themes

1. **Frontend performance/safety (M-01, M-02, M-03, M-04):** Same quadratic histogram and Math.min spread patterns from MC audit. Unsafe type cast. Null-safety gap in PValueBadge.

2. **Simulation fairness (M-05):** The 3x buffer for random entry candidates may not be enough, leading to fewer trades placed than requested, which biases the comparison.

3. **Code duplication (M-06, L-02):** `_sanitize_for_json` duplicated; dead parquet code in extractor.

4. **Backend gaps (L-03, L-04, L-05):** Missing input validation, unnecessary `--save` flag, no real-time progress.
