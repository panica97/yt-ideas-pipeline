# Audit 08 — Phase 12.5: Stress Test (Parameter Sensitivity)

**Date:** 2026-04-02
**Scope:** Stress Test — core package, worker engine, API schema, frontend report + param builder
**Auditor:** Claude (automated)
**Findings:** 14

---

## Files Reviewed

- `packages/stress-test/runner.py` — Main orchestrator + CLI
- `packages/stress-test/grid.py` — Grid generation (cartesian + single sweeps)
- `packages/stress-test/executor.py` — Single-variation subprocess runner
- `packages/stress-test/aggregator.py` — Result aggregation + robustness scoring
- `packages/stress-test/config.py` — Configuration dataclass
- `worker/stress_engine.py` — Worker subprocess runner
- `worker/executor.py` — Job executor (stress branch)
- `api/models/schemas/backtest.py` — Pydantic schemas (stress fields)
- `api/alembic/versions/016_add_stress_test_params_to_backtest_jobs.py` — Migration
- `frontend/src/components/strategies/StressTestReport.tsx` — Report UI
- `frontend/src/components/strategies/StressParamBuilder.tsx` — Parameter builder
- `frontend/src/types/backtest.ts` — StressTestMetrics TypeScript type

---

## Findings

### HIGH

#### H-01: Cartesian grid can generate explosive variation count with no server-side limit

**File:** `packages/stress-test/grid.py:53-76`, `packages/stress-test/config.py`
**Description:** `build_multi_grid` computes the cartesian product of all parameter ranges. With 4 parameters each having 10 values, this produces 10,000 variations. With 5 params x 20 values = 3.2 million. There is no server-side limit on the number of variations. The frontend has a warning at 500 variations but it is purely cosmetic — the API accepts any `stress_param_overrides` dict. Each variation spawns a subprocess backtest.
**Severity:** HIGH
**Impact:** A single API call could spawn thousands of subprocesses, exhausting CPU/memory and potentially crashing the server. This is a denial-of-service vector even with honest users making configuration mistakes.

### MEDIUM

#### M-01: `results` list pre-allocated with `[{}] * len(work_items)` creates aliased references

**File:** `packages/stress-test/runner.py:148`
**Description:** `results: List[Dict[str, Any]] = [{}] * len(work_items)` creates N references to the **same** empty dict. When `results[idx] = result` replaces the reference, this works correctly because it replaces (not mutates) the dict. So this is not a bug in practice, but the pattern is misleading and fragile — if anyone changes it to `results[idx].update(result)` it would corrupt all entries.
**Severity:** MEDIUM
**Impact:** No current bug, but the aliased-reference pattern is a maintenance trap.

#### M-02: ThreadPoolExecutor runs multiple backtests with shared global state

**File:** `packages/stress-test/runner.py:165-181`
**Description:** `execute_variation` spawns subprocesses, which is safe. However, the `_run_one` closure captures `strategy_id`, `hist_data_path`, `strategies_path` from the outer scope. More importantly, each subprocess reads the same strategy JSON file from disk. If two threads happen to remap/write the same strategy file concurrently (via executor.py's temp file approach), there could be a race. The current implementation uses unique temp files per variation, so this is mitigated, but the design relies on this assumption.
**Severity:** MEDIUM
**Impact:** Currently safe due to subprocess isolation + unique temp files, but fragile if the temp file naming changes.

#### M-03: Unsafe `as unknown as StressTestMetrics` double cast

**File:** `frontend/src/components/strategies/BacktestReportDrawer.tsx:917`
**Description:** Same pattern as monkey test — `job?.result?.metrics as unknown as StressTestMetrics`. No runtime type guard at the API boundary.
**Severity:** MEDIUM
**Impact:** If backend returns unexpected shape, components crash with unhelpful errors.

#### M-04: `Math.max(...ddVals)` and `Math.max(...vals)` stack overflow on large variation sets

**File:** `frontend/src/components/strategies/StressTestReport.tsx:165`, `StressTestReport.tsx:651-652`, `StressTestReport.tsx:769`
**Description:** Multiple places use `Math.max(...array)` or `Math.min(...array)`. With 500+ variations, this creates 500+ call stack arguments. While less likely to hit the 65K limit than Monte Carlo, it is the same unsafe pattern.
**Severity:** MEDIUM
**Impact:** Potential stack overflow crash with very large stress test runs.

#### M-05: `SensitivityHeatmap` uses `useMemo` with side effects (calling `setXParam`/`setYParam`)

**File:** `frontend/src/components/strategies/StressTestReport.tsx:508-516`
**Description:** The `useMemo` callback calls `setXParam` and `setYParam` state setters as a side effect. React docs explicitly warn against this: "Your calculation function should be pure — it should not have side effects." This can cause render loops or stale state.
**Severity:** MEDIUM
**Impact:** Potential render loops or incorrect parameter selection on re-renders.

#### M-06: Robustness score uses `low_drawdown_pct` with hardcoded 50% threshold

**File:** `packages/stress-test/aggregator.py:16, 159`
**Description:** `LOW_DD_THRESHOLD = 50.0` is hardcoded. The `max_drawdown_pct` metric from the engine can be reported as either a positive or negative number depending on the engine output format. The aggregator uses `abs(max_dd)` but the threshold of 50% is very generous — most robustness frameworks use 20-30%. This inflates the robustness score.
**Severity:** MEDIUM
**Impact:** Robustness score is overly optimistic due to lenient drawdown threshold.

#### M-07: `StressParamBuilder` `useEffect` for states initialization can cause infinite loop

**File:** `frontend/src/components/strategies/StressParamBuilder.tsx:289-300`
**Description:** The `useEffect` depends on `[params]` and calls `setStates(initial)`. Inside the loop, it reads `states[p.key]` to preserve existing state. But `states` is not in the dependency array (eslint rule is disabled). If `params` reference changes on every render (which it would if `draftData` is a new object each time), this effect fires on every render, potentially resetting user edits.
**Severity:** MEDIUM
**Impact:** User parameter configurations could be lost on parent re-renders.

### LOW

#### L-01: `_sanitize_for_json` duplicated again in `stress-test/runner.py`

**File:** `packages/stress-test/runner.py:46-64`
**Description:** Third copy of this helper (also in monkey-test runner and aggregator). Should be in a shared utility.
**Severity:** LOW
**Impact:** Code duplication; divergence risk.

#### L-02: No validation on `stress_param_overrides` shape at API level

**File:** `api/models/schemas/backtest.py:24-27`
**Description:** `stress_param_overrides` and `stress_single_overrides` are typed as `Optional[dict]` with no schema validation. Any arbitrary JSON is accepted. Malformed specs (e.g., missing `min`/`max`/`step` keys) only fail at the runner level with unclear errors.
**Severity:** LOW
**Impact:** Poor error messages for malformed stress test configs.

#### L-03: `colorScale` function in StressTestReport produces white mid-range values with poor contrast

**File:** `frontend/src/components/strategies/StressTestReport.tsx:116-127`
**Description:** The color interpolation passes through near-white (rgb 255,255,255) at the midpoint (norm=0.5). In the heatmap, mid-range cells have white text on near-white background, making values unreadable.
**Severity:** LOW
**Impact:** Poor readability for mid-range heatmap cells.

#### L-04: Worker `--save` flag always passed to stress test runner

**File:** `worker/stress_engine.py` does not pass `--save` (confirmed), but `runner.py:312-328` has save logic
**Description:** Unlike monkey_engine which always passes `--save`, the stress_engine does NOT pass `--save`. This is correct behavior. However, the runner CLI supports `--save` and `--output-dir`, and if used directly via CLI, results accumulate. No issue for the worker path.
**Severity:** LOW
**Impact:** No worker impact; CLI-only concern.

#### L-05: `StressTestVariation.status` type mismatch between frontend and backend

**File:** `frontend/src/types/backtest.ts:267`, `packages/stress-test/executor.py:164`
**Description:** Frontend declares `status: 'completed' | 'failed'` but the backend executor returns `status: "ok"` or `status: "error"`. The frontend `StressTestReport` filters by `v.status === 'completed'` which would never match `"ok"`. This suggests there is a transformation layer (in `BacktestReportDrawer.tsx` or the API) that maps these values, but the type mismatch is confusing and error-prone.
**Severity:** LOW
**Impact:** If the transformation is missing or breaks, all variations would show as "not completed" in the report.

#### L-06: `smartDefaults` in StressParamBuilder can produce `min > max` for small values

**File:** `frontend/src/components/strategies/StressParamBuilder.tsx:29-36`
**Description:** For a `currentValue` of 0 or negative numbers, `Math.round(value * 0.5)` and `Math.round(value * 2)` can produce `min=0, max=0` or negative ranges. The `Math.max(1, ...)` guard on `min` helps for zero, but negative values (e.g., a trailing ratio of -1) would produce `min=1, max=-2`.
**Severity:** LOW
**Impact:** Edge case: nonsensical default ranges for zero or negative parameter values.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 1     |
| MEDIUM   | 7     |
| LOW      | 6     |
| **Total** | **14** |

### Key Themes

1. **Resource exhaustion (H-01):** No server-side limit on cartesian grid size. A 5-param grid with moderate ranges can spawn millions of subprocess backtests. Needs a hard cap.

2. **Frontend patterns (M-03, M-04, M-05, M-07):** Unsafe type cast, Math.min/max spread, side effects in useMemo, potential infinite loops in useEffect — multiple React anti-patterns.

3. **Robustness scoring (M-06):** The 50% drawdown threshold is very lenient and inflates robustness scores.

4. **Code quality (M-01, L-01, L-02):** Aliased list references, triplicated helper function, unvalidated API inputs.

5. **Type mismatches (L-05):** Frontend expects `completed`/`failed` but backend returns `ok`/`error` — needs investigation of the transformation layer.
