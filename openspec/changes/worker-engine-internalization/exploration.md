# Exploration: worker-engine-internalization

**Date:** 2026-03-25
**Phase:** SDD Explore
**Goal:** Internalize `backtest-engine` and `ibkr-core` packages from Operations-Platform into IRT, eliminating the cross-repo dependency. The worker's `_resolve_python()` will use IRT's own `.venv` instead of reaching into Ops-Platform.

---

## 1. Exact Files to Copy

### 1a. ibkr-core -> IRT/packages/ibkr-core/

Source: `C:/Users/Pablo Nieto/codigos/Operations-Platform/packages/ibkr-core/`

| Source | Destination (under IRT/) |
|--------|--------------------------|
| `pyproject.toml` | `packages/ibkr-core/pyproject.toml` |
| `ibkr_core/__init__.py` | `packages/ibkr-core/ibkr_core/__init__.py` |
| `ibkr_core/_compat.py` | `packages/ibkr-core/ibkr_core/_compat.py` |
| `ibkr_core/indicators.py` | `packages/ibkr-core/ibkr_core/indicators.py` |
| `ibkr_core/logger.py` | `packages/ibkr-core/ibkr_core/logger.py` |
| `ibkr_core/market_data.py` | `packages/ibkr-core/ibkr_core/market_data.py` |
| `ibkr_core/schema.json` | `packages/ibkr-core/ibkr_core/schema.json` |
| `ibkr_core/sl_tp.py` | `packages/ibkr-core/ibkr_core/sl_tp.py` |
| `ibkr_core/strat_loader.py` | `packages/ibkr-core/ibkr_core/strat_loader.py` |
| `ibkr_core/strategies.py` | `packages/ibkr-core/ibkr_core/strategies.py` |
| `ibkr_core/trading_calendar.json` | `packages/ibkr-core/ibkr_core/trading_calendar.json` |
| `ibkr_core/trading_calendar.py` | `packages/ibkr-core/ibkr_core/trading_calendar.py` |
| `ibkr_core/custom_indicators/__init__.py` | `packages/ibkr-core/ibkr_core/custom_indicators/__init__.py` |
| `ibkr_core/custom_indicators/kama.py` | `packages/ibkr-core/ibkr_core/custom_indicators/kama.py` |

**Excluded (not needed at runtime):**
- `tests/` — test fixtures and test files (not needed for worker execution)
- `scripts/test_clean_venv.py` — dev utility

### 1b. backtest-engine -> IRT/packages/backtest-engine/

Source: `C:/Users/Pablo Nieto/codigos/Operations-Platform/packages/backtest-engine/`

| Source | Destination (under IRT/) |
|--------|--------------------------|
| `pyproject.toml` | `packages/backtest-engine/pyproject.toml` |
| `main.py` | `packages/backtest-engine/main.py` |
| `constants.py` | `packages/backtest-engine/constants.py` |
| `logger.py` | `packages/backtest-engine/logger.py` |
| `data/margin_data.json` | `packages/backtest-engine/data/margin_data.json` |
| `engine/__init__.py` | `packages/backtest-engine/engine/__init__.py` |
| `engine/_00_constants.py` | `packages/backtest-engine/engine/_00_constants.py` |
| `engine/_01_data_processor.py` | `packages/backtest-engine/engine/_01_data_processor.py` |
| `engine/_02_strategy_manager.py` | `packages/backtest-engine/engine/_02_strategy_manager.py` |
| `engine/_03_price_utils.py` | `packages/backtest-engine/engine/_03_price_utils.py` |
| `engine/_03b_warmup_utils.py` | `packages/backtest-engine/engine/_03b_warmup_utils.py` |
| `engine/_04_trading_hours.py` | `packages/backtest-engine/engine/_04_trading_hours.py` |
| `engine/_05_sl_tp_manager.py` | `packages/backtest-engine/engine/_05_sl_tp_manager.py` |
| `engine/_06_position_manager.py` | `packages/backtest-engine/engine/_06_position_manager.py` |
| `engine/_07_exit_simulation.py` | `packages/backtest-engine/engine/_07_exit_simulation.py` |
| `engine/_08_metrics_reporter.py` | `packages/backtest-engine/engine/_08_metrics_reporter.py` |
| `engine/_09_position_sizer.py` | `packages/backtest-engine/engine/_09_position_sizer.py` |
| `engine/_10_backtester.py` | `packages/backtest-engine/engine/_10_backtester.py` |
| `engine/_11_portfolio_state.py` | `packages/backtest-engine/engine/_11_portfolio_state.py` |
| `engine/_12_portfolio_orchestrator.py` | `packages/backtest-engine/engine/_12_portfolio_orchestrator.py` |
| `engine/_13_margin_calculator.py` | `packages/backtest-engine/engine/_13_margin_calculator.py` |
| `engine/_14_portfolio_metrics.py` | `packages/backtest-engine/engine/_14_portfolio_metrics.py` |
| `engine/_15_portfolio_reporter.py` | `packages/backtest-engine/engine/_15_portfolio_reporter.py` |
| `engine/_16_vectorized_signals.py` | `packages/backtest-engine/engine/_16_vectorized_signals.py` |

**Excluded (not needed at runtime):**
- `tests/` — test files and conftest
- `logs_system/` — runtime-generated log files
- `__pycache__/` — compiled bytecode

**Total files to copy: 14 (ibkr-core) + 22 (backtest-engine) = 36 files**

---

## 2. _resolve_python() Changes

### Current code (worker/engine.py, lines 31-46):

```python
def _resolve_python() -> str:
    engine_path = os.environ.get("ENGINE_PATH", "")
    if engine_path:
        # Look for a venv relative to the engine's parent (ops-worker root)
        ops_root = Path(engine_path).resolve().parent.parent.parent
        venv_python = ops_root / ".venv" / (
            "Scripts" if os.name == "nt" else "bin"
        ) / ("python.exe" if os.name == "nt" else "python")
        if venv_python.is_file():
            return str(venv_python)
    return sys.executable
```

### New code:

```python
def _resolve_python() -> str:
    """Resolve the Python executable to use for the engine subprocess.

    Uses the .venv at the IRT project root (parent of worker/ directory)
    so that ibkr_core and other engine dependencies are available.
    """
    # IRT project root = parent of the worker/ package directory
    irt_root = Path(__file__).resolve().parent.parent
    venv_python = irt_root / ".venv" / (
        "Scripts" if os.name == "nt" else "bin"
    ) / ("python.exe" if os.name == "nt" else "python")
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable
```

**Rationale:** The current logic navigates `ENGINE_PATH -> parent.parent.parent` to find the Ops-Platform `.venv`. After internalization, the engine lives inside IRT, so we navigate from `worker/engine.py -> parent (worker/) -> parent (IRT root)` to find `IRT/.venv`. This is deterministic and no longer depends on `ENGINE_PATH` for venv resolution.

---

## 3. ENGINE_PATH Value

### .env.example (new value):

```env
# Absolute path to the backtest engine's main.py entry point
# After internalization, this points to the local packages/ copy
ENGINE_PATH=packages/backtest-engine/main.py
```

### .env (actual value for dev machine):

```env
ENGINE_PATH=packages/backtest-engine/main.py
```

**Note:** The path can be relative (resolved from worker's cwd) or absolute. Relative is preferred because it's portable across machines. The `config.engine_path` is used in `run_engine()` to build the subprocess command: `[python_exe, config.engine_path, "--mode", "single", ...]`. Since the worker runs from the IRT project root (via `python -m worker.main`), a relative path works.

### _find_parquet() also uses engine_path

`_find_parquet()` at line 179 does `Path(Config().engine_path).parent` to locate `logs_backtest/`. With `ENGINE_PATH=packages/backtest-engine/main.py`, this resolves to `packages/backtest-engine/` which is correct -- `logs_backtest/` will appear there when the engine runs with `--save`.

---

## 4. requirements.txt — Merged Dependencies

Current IRT `requirements.txt` + ibkr-core deps + backtest-engine deps + worker deps:

```
# --- IRT core (existing) ---
yt-dlp
pyyaml
notebooklm-py
sqlalchemy>=2.0
psycopg2-binary>=2.9.0
alembic

# --- Worker (existing, from worker imports) ---
requests
python-dotenv>=1.0.0

# --- ibkr-core (new) ---
polars>=1.34.0
numpy>=2.3.0
pandas>=2.3.0
TA-Lib>=0.6.0
pytz>=2025.2
icecream>=2.1.0
jsonschema>=4.0.0
```

**Notes:**
- `psycopg2-binary` version bumped to `>=2.9.0` to satisfy both IRT's existing dep and ibkr-core's optional `live` dep.
- `requests` is already used by `worker/config.py` but was missing from requirements.txt.
- `python-dotenv` is already used by `worker/config.py` but was missing from requirements.txt.
- ibkr-core `live` extras (`ib_async`) are NOT needed -- IRT only uses backtest mode.
- ibkr-core `dev` extras (`pytest`) are NOT needed in production requirements.
- backtest-engine's only dep is `ibkr-core` (installed via pip install -e) + `python-dotenv`.
- **TA-Lib requires a system-level C library** (`ta-lib`). This must be pre-installed on the host. On Windows, install the binary wheel from the unofficial Python binaries page.

---

## 5. .gitignore Additions

Current `.gitignore` is minimal. Add:

```gitignore
# Python virtual environment
.venv/

# Engine runtime artifacts
packages/backtest-engine/logs_backtest/
packages/backtest-engine/logs_portfolio/
packages/backtest-engine/logs_system/
packages/backtest-engine/logs_integration_test/
packages/backtest-engine/logs_comparison/
packages/backtest-engine/logs_stress_test/

# Python bytecode (already have __pycache__/ but be explicit for packages)
packages/**/__pycache__/
*.pyc

# Debug JSON output from worker
data/backtests/debug/
```

---

## 6. Installation Procedure (for the apply phase)

After copying the files, the IRT `.venv` must be set up:

```bash
cd C:/Users/Pablo Nieto/codigos/IRT
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -e packages/ibkr-core
pip install -e packages/backtest-engine
pip install -r requirements.txt
```

The `-e` (editable) installs make `ibkr_core` and `backtest-engine` importable from the venv. The engine's `main.py` does `sys.path.insert(0, PROJECT_ROOT)` so its internal bare imports (`from constants import ...`, `from engine._10_backtester import ...`) will resolve correctly.

---

## 7. Risks and Mitigation

### RISK 1: Bare imports in backtest-engine (MEDIUM)

**Problem:** `backtest-engine/main.py` uses bare imports like `from constants import ...` and `from logger import get_logger`. The engine modules use bare imports like `from _00_constants import ExitReason`. These work because `main.py` injects `PROJECT_ROOT` and `ENGINE_PATH` into `sys.path` at startup (lines 47-60).

**Mitigation:** This is already handled. The engine is invoked as a subprocess via `python packages/backtest-engine/main.py ...`, so `main.py`'s `PROJECT_ROOT = Path(__file__).parent` resolves to `packages/backtest-engine/` and its `sys.path` manipulation works as-is. No changes needed.

### RISK 2: trading_calendar.json path resolution (LOW)

**Problem:** `ibkr_core/trading_calendar.py` looks for `trading_calendar.json` at `Path(__file__).parent.parent / 'trading_calendar.json'` (i.e., one level above `ibkr_core/`). After copy, this resolves to `packages/ibkr-core/trading_calendar.json`.

**Mitigation:** The file exists at `ibkr_core/trading_calendar.json` (inside the package), but the code looks one level up. However, checking the source: the file IS located at `ibkr_core/trading_calendar.json` in the package AND the code looks at `current_dir.parent / 'trading_calendar.json'` where `current_dir = Path(__file__).parent` = `ibkr_core/`. So it looks at `packages/ibkr-core/trading_calendar.json`. **We need to copy `trading_calendar.json` to BOTH `ibkr_core/` (already listed) AND `packages/ibkr-core/` (the parent directory).** Add this file to the copy list:

| Extra file | Destination |
|-----------|-------------|
| `ibkr_core/trading_calendar.json` | `packages/ibkr-core/trading_calendar.json` |

### RISK 3: margin_data.json relative path (LOW)

**Problem:** `engine/_13_margin_calculator.py` line 104 resolves margin data via `Path(__file__).parent.parent / 'data' / 'margin_data.json'`. This means `engine/ -> parent = backtest-engine/ -> data/margin_data.json`. After copy this resolves to `packages/backtest-engine/data/margin_data.json`, which is correct since we copy that file.

**Mitigation:** None needed. Path resolves correctly.

### RISK 4: schema.json path (LOW)

**Problem:** `ibkr_core/strat_loader.py` line 34 uses `Path(__file__).parent / 'schema.json'` = `ibkr_core/schema.json`. This is already in the copy list.

**Mitigation:** None needed.

### RISK 5: TA-Lib system dependency (MEDIUM)

**Problem:** `ibkr_core/indicators.py` imports `talib`, which requires the TA-Lib C library installed at the system level. This is NOT a pip-installable pure Python package.

**Mitigation:** Document the prerequisite. On Windows, install from the unofficial binaries: `pip install TA_Lib-{version}-cp312-win_amd64.whl`. On Linux (for future Docker), install `ta-lib` via apt/yum.

### RISK 6: Dual-repo drift (LOW, long-term)

**Problem:** After copying, IRT has a snapshot of the engine. If Operations-Platform evolves, the copies diverge.

**Mitigation:** This is intentional per Phase 12.1 design. IRT owns its engine copy going forward. Keep a `COPIED_FROM` marker comment in each `pyproject.toml` with the commit hash for traceability.

### RISK 7: logs_backtest output location (LOW)

**Problem:** The engine writes `logs_backtest/` relative to `PROJECT_ROOT` (which is `packages/backtest-engine/`). The worker's `_find_parquet()` also looks there.

**Mitigation:** Both resolve via `Path(Config().engine_path).parent`, so they agree. The `.gitignore` additions cover these directories.

### RISK 8: `icecream` import in engine code (LOW)

**Problem:** Several engine/ibkr_core files import `icecream` (`from icecream import ic`). This is a debug utility.

**Mitigation:** Already included in requirements.txt above (`icecream>=2.1.0`).

---

## 8. Summary of All Changes Needed

| Category | File(s) | Action |
|----------|---------|--------|
| Copy | 36 source files + 1 extra `trading_calendar.json` | Copy from Ops-Platform to `IRT/packages/` |
| Modify | `worker/engine.py` | Rewrite `_resolve_python()` to use IRT root `.venv` |
| Modify | `worker/.env.example` | Update `ENGINE_PATH` to `packages/backtest-engine/main.py` |
| Modify | `requirements.txt` | Add ibkr-core + engine dependencies |
| Modify | `.gitignore` | Add `.venv/`, engine log dirs, `__pycache__` in packages |
| Create | `IRT/.venv` | Python virtual environment (not committed) |
| Install | pip commands | `pip install -e packages/ibkr-core && pip install -e packages/backtest-engine && pip install -r requirements.txt` |
