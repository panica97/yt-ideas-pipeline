# Exploration: mc-baseline-date-fix

**Date:** 2026-03-28
**Topic:** MC baseline date range mismatch — the MC runner ignores the job's start/end dates and uses "last N bars" of all available data, causing the baseline backtest to run on a different period than the original backtest.

---

## 1. Current Behavior (Bug)

### Regular backtest (`worker/engine.py`)
The regular backtest correctly passes `--start` and `--end` from the job dict to the backtest engine CLI:

```python
cmd = [
    python_exe, config.engine_path,
    "--mode", "single",
    "--strategy", str(strat_code),
    "--start", job["start_date"],   # <-- explicit dates
    "--end", job["end_date"],       # <-- explicit dates
    ...
]
```

### MC engine (`worker/mc_engine.py`)
The MC engine calculates `sim_bars` from the job's date range but **never passes `--start`/`--end`** to the MC CLI:

```python
# Calculates sim_bars correctly from dates (lines 59-75)
sim_bars = max(1, int(calendar_days * 252 / 365))

# But only passes sim_bars, NOT the actual dates (lines 80-92)
cmd = [
    python_exe, mc_runner_path,
    "--sim-bars", str(sim_bars),
    # --start and --end are MISSING
    ...
]
```

### MC CLI (`packages/montecarlo/runner/main_mc.py`)
Does **not** accept `--start` or `--end` arguments at all. Only accepts `--sim-bars`.

### MC Runner (`packages/montecarlo/runner/mc_runner.py`, lines 215-255)
Uses "last N bars" logic to derive the baseline window:

```python
# Line 235: Takes the TAIL of all available data
baseline_slice = base_df_all.tail(n_periods)
```

This means: if the job requests 2020-01-01 to 2021-01-01, the MC runner converts that to ~252 sim_bars, then takes the **last 252 trading days of all loaded data** (e.g., 2025-03-xx to 2026-03-xx). The baseline backtest runs on completely wrong dates.

### Impact
- The MC baseline backtest result is meaningless for comparison — it's running on different data than the original backtest.
- MC synthetic paths are generated from a model fitted to the wrong window's statistical properties.
- All MC statistics (percentile ranks, p-values comparing baseline to MC distribution) are invalid.

---

## 2. Root Cause

Three-layer gap:

1. **`mc_engine.py`** has the dates but doesn't pass them.
2. **`main_mc.py`** doesn't accept date arguments.
3. **`mc_runner.py`** has no mechanism to use explicit dates — it only knows "last N bars".

---

## 3. Fix Approach

There is one straightforward approach: thread `--start` and `--end` through all three layers.

### Layer 1: `main_mc.py` — Add CLI arguments

Add two new optional arguments:
- `--start` (str): Start date (ISO format, e.g., `2020-01-01`)
- `--end` (str): End date (ISO format, e.g., `2021-01-01`)

Pass them to `runner.run_path_based()` as new optional parameters.

### Layer 2: `mc_runner.py` — Accept and use explicit dates for baseline

In `MonteCarloRunner.run_path_based()`:
- Add `start_date: Optional[str] = None` and `end_date: Optional[str] = None` parameters.
- When both are provided: filter `base_df_all` to that date range for the baseline window (replacing the `tail(n_periods)` logic).
- When not provided: keep existing "last N bars" behavior as fallback for standalone/CLI usage.

Specifically, replace lines 215-242 with logic like:

```python
if start_date and end_date:
    # Explicit date window from job
    bl_start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    bl_end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    baseline_slice = base_df_all.filter(
        (pl.col("date") >= bl_start_dt) & (pl.col("date") <= bl_end_dt)
    )
    # Derive actual sim_bars from the filtered data
    n_periods = len(baseline_slice)
    # ... compute bars_per_day, actual trading days for logging
else:
    # Fallback: last sim_bars trading days (existing behavior)
    ...existing tail() logic...
```

The `sim_bars` parameter keeps its role: it defines the **length of synthetic paths** (how many bars each MC path generates). The start/end dates define which **historical window** is used for the baseline backtest.

### Layer 3: `mc_engine.py` — Pass dates to CLI

Add `--start` and `--end` to the command list when dates are available:

```python
if start_date_str and end_date_str:
    cmd.extend(["--start", start_date_str, "--end", end_date_str])
```

---

## 4. Files to Modify

| File | Change |
|------|--------|
| `worker/mc_engine.py` | Add `--start`/`--end` to subprocess command (2 lines) |
| `packages/montecarlo/runner/main_mc.py` | Add `--start`/`--end` argparse args; pass to `run_path_based()` |
| `packages/montecarlo/runner/mc_runner.py` | Add `start_date`/`end_date` params to `run_path_based()`; conditional baseline window logic |

---

## 5. Edge Cases & Considerations

1. **Date range exceeds available data:** If the requested dates extend beyond loaded data, the filter will naturally return only the available overlap. Should log a warning if the actual baseline is shorter than requested.

2. **`sim_bars` vs date range mismatch:** `sim_bars` (synthetic path length) and the baseline date range should produce roughly the same number of bars. Since `mc_engine.py` already computes `sim_bars` from the date range, these will be consistent. But `mc_runner.py` should use the actual baseline bar count for logging accuracy.

3. **Backward compatibility:** When `--start`/`--end` are not provided, the existing "last N bars" behavior is preserved. No breaking change for standalone CLI usage.

4. **`fit_years` interaction:** The fitting window (`fit_years`) is independent from the baseline window. The model is fit on up to `fit_years` of history; the baseline is a subset within that. No change needed to fitting logic.

5. **Multi-timeframe baseline filtering:** The existing code at lines 244-254 already filters all timeframes using `baseline_start`/`baseline_end` dates derived from the base timeframe slice. This pattern works the same whether dates come from explicit args or tail() — no change needed there.

---

## 6. Risk Assessment

- **Risk level:** LOW
- **Rationale:** The fix is purely additive (new optional CLI args, new optional function params) with a clean fallback to existing behavior. No changes to the synthetic path generation, model fitting, or aggregation logic.
- **Testing:** Run a MC job with known start/end dates and verify the baseline window in stdout matches the requested dates.

---

## 7. Complexity Estimate

- **Size:** Small (3 files, ~30-40 lines of changes)
- **Estimated effort:** Single session
