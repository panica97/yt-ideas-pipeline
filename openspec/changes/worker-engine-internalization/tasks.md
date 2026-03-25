# Tasks: Worker Engine Internalization

## Phase 1: Foundation -- Copy files, create directory structure

### 1.1 Create `packages/` directory structure
- [x] Create `packages/ibkr-core/ibkr_core/` directory
- [x] Create `packages/ibkr-core/ibkr_core/custom_indicators/` directory
- [x] Create `packages/backtest-engine/engine/` directory
- [x] Create `packages/backtest-engine/data/` directory

### 1.2 Copy ibkr-core package (14 files + 1 extra)
Source: `C:/Users/Pablo Nieto/codigos/Operations-Platform/packages/ibkr-core/`

- [x] Copy `pyproject.toml` -> `packages/ibkr-core/pyproject.toml`
- [x] Copy `ibkr_core/__init__.py` -> `packages/ibkr-core/ibkr_core/__init__.py`
- [x] Copy `ibkr_core/_compat.py` -> `packages/ibkr-core/ibkr_core/_compat.py`
- [x] Copy `ibkr_core/indicators.py` -> `packages/ibkr-core/ibkr_core/indicators.py`
- [x] Copy `ibkr_core/logger.py` -> `packages/ibkr-core/ibkr_core/logger.py`
- [x] Copy `ibkr_core/market_data.py` -> `packages/ibkr-core/ibkr_core/market_data.py`
- [x] Copy `ibkr_core/schema.json` -> `packages/ibkr-core/ibkr_core/schema.json`
- [x] Copy `ibkr_core/sl_tp.py` -> `packages/ibkr-core/ibkr_core/sl_tp.py`
- [x] Copy `ibkr_core/strat_loader.py` -> `packages/ibkr-core/ibkr_core/strat_loader.py`
- [x] Copy `ibkr_core/strategies.py` -> `packages/ibkr-core/ibkr_core/strategies.py`
- [x] Copy `ibkr_core/trading_calendar.json` -> `packages/ibkr-core/ibkr_core/trading_calendar.json`
- [x] Copy `ibkr_core/trading_calendar.py` -> `packages/ibkr-core/ibkr_core/trading_calendar.py`
- [x] Copy `ibkr_core/custom_indicators/__init__.py` -> `packages/ibkr-core/ibkr_core/custom_indicators/__init__.py`
- [x] Copy `ibkr_core/custom_indicators/kama.py` -> `packages/ibkr-core/ibkr_core/custom_indicators/kama.py`
- [x] Copy `ibkr_core/trading_calendar.json` -> `packages/ibkr-core/trading_calendar.json` (extra copy at parent level for `Path(__file__).parent.parent` resolution in `trading_calendar.py`)

### 1.3 Copy backtest-engine package (22 files)
Source: `C:/Users/Pablo Nieto/codigos/Operations-Platform/packages/backtest-engine/`

- [x] Copy `pyproject.toml` -> `packages/backtest-engine/pyproject.toml`
- [x] Copy `main.py` -> `packages/backtest-engine/main.py`
- [x] Copy `constants.py` -> `packages/backtest-engine/constants.py`
- [x] Copy `logger.py` -> `packages/backtest-engine/logger.py`
- [x] Copy `data/margin_data.json` -> `packages/backtest-engine/data/margin_data.json`
- [x] Copy `engine/__init__.py` -> `packages/backtest-engine/engine/__init__.py`
- [x] Copy `engine/_00_constants.py` -> `packages/backtest-engine/engine/_00_constants.py`
- [x] Copy `engine/_01_data_processor.py` -> `packages/backtest-engine/engine/_01_data_processor.py`
- [x] Copy `engine/_02_strategy_manager.py` -> `packages/backtest-engine/engine/_02_strategy_manager.py`
- [x] Copy `engine/_03_price_utils.py` -> `packages/backtest-engine/engine/_03_price_utils.py`
- [x] Copy `engine/_03b_warmup_utils.py` -> `packages/backtest-engine/engine/_03b_warmup_utils.py`
- [x] Copy `engine/_04_trading_hours.py` -> `packages/backtest-engine/engine/_04_trading_hours.py`
- [x] Copy `engine/_05_sl_tp_manager.py` -> `packages/backtest-engine/engine/_05_sl_tp_manager.py`
- [x] Copy `engine/_06_position_manager.py` -> `packages/backtest-engine/engine/_06_position_manager.py`
- [x] Copy `engine/_07_exit_simulation.py` -> `packages/backtest-engine/engine/_07_exit_simulation.py`
- [x] Copy `engine/_08_metrics_reporter.py` -> `packages/backtest-engine/engine/_08_metrics_reporter.py`
- [x] Copy `engine/_09_position_sizer.py` -> `packages/backtest-engine/engine/_09_position_sizer.py`
- [x] Copy `engine/_10_backtester.py` -> `packages/backtest-engine/engine/_10_backtester.py`
- [x] Copy `engine/_11_portfolio_state.py` -> `packages/backtest-engine/engine/_11_portfolio_state.py`
- [x] Copy `engine/_12_portfolio_orchestrator.py` -> `packages/backtest-engine/engine/_12_portfolio_orchestrator.py`
- [x] Copy `engine/_13_margin_calculator.py` -> `packages/backtest-engine/engine/_13_margin_calculator.py`
- [x] Copy `engine/_14_portfolio_metrics.py` -> `packages/backtest-engine/engine/_14_portfolio_metrics.py`
- [x] Copy `engine/_15_portfolio_reporter.py` -> `packages/backtest-engine/engine/_15_portfolio_reporter.py`
- [x] Copy `engine/_16_vectorized_signals.py` -> `packages/backtest-engine/engine/_16_vectorized_signals.py`

---

## Phase 2: Configuration -- requirements.txt, .gitignore, .env, _resolve_python()

### 2.1 Update `requirements.txt` (IRT root)
File: `requirements.txt`

- [x] Add worker dependencies section: `requests`, `python-dotenv>=1.0.0`
- [x] Add ibkr-core/engine dependencies section: `polars>=1.34.0`, `numpy>=2.3.0`, `pandas>=2.3.0`, `TA-Lib>=0.6.0`, `pytz>=2025.2`, `icecream>=2.1.0`, `jsonschema>=4.0.0`
- [x] Bump `psycopg2-binary` to `psycopg2-binary>=2.9.0`
- [x] Add section comments for clarity (`# --- IRT core ---`, `# --- Worker ---`, `# --- ibkr-core (backtest engine dependency) ---`)

Final content:
```
# --- IRT core ---
yt-dlp
pyyaml
notebooklm-py
sqlalchemy>=2.0
psycopg2-binary>=2.9.0
alembic

# --- Worker ---
requests
python-dotenv>=1.0.0

# --- ibkr-core (backtest engine dependency) ---
polars>=1.34.0
numpy>=2.3.0
pandas>=2.3.0
TA-Lib>=0.6.0
pytz>=2025.2
icecream>=2.1.0
jsonschema>=4.0.0
```

### 2.2 Update `.gitignore`
File: `.gitignore`

- [x] Add `.venv/` entry
- [x] Add engine runtime artifact directories:
  - `packages/backtest-engine/logs_backtest/`
  - `packages/backtest-engine/logs_portfolio/`
  - `packages/backtest-engine/logs_system/`
  - `packages/backtest-engine/logs_integration_test/`
  - `packages/backtest-engine/logs_comparison/`
  - `packages/backtest-engine/logs_stress_test/`
- [x] Add `packages/**/__pycache__/`
- [x] Add `data/backtests/debug/`

### 2.3 Update `worker/.env.example`
File: `worker/.env.example`

- [x] Change `ENGINE_PATH` value from `C:/Users/YourUser/path/to/backtest-engine/main.py` to `packages/backtest-engine/main.py`
- [x] Update the comment to reflect the new local path (remove "Absolute path", note it's relative to project root)

### 2.4 Rewrite `_resolve_python()` in `worker/engine.py`
File: `worker/engine.py` (lines 31-46)

- [x] Replace the current implementation that navigates from `ENGINE_PATH` to Ops-Platform venv
- [x] New implementation navigates from `Path(__file__).resolve().parent.parent` (IRT root) to `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Linux)
- [x] Preserve `sys.executable` fallback when `.venv` not found
- [x] Update the docstring to reference IRT root venv instead of ops-worker

New code:
```python
def _resolve_python() -> str:
    """Resolve the Python executable to use for the engine subprocess.

    Uses the .venv at the IRT project root (parent of worker/ directory)
    so that ibkr_core and other engine dependencies are available.
    Falls back to sys.executable if .venv is not found.
    """
    irt_root = Path(__file__).resolve().parent.parent
    venv_python = irt_root / ".venv" / (
        "Scripts" if os.name == "nt" else "bin"
    ) / ("python.exe" if os.name == "nt" else "python")
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable
```

---

## Phase 3: Environment Setup (MANUAL -- user executes these steps)

> These steps are NOT automatable by sdd-apply. The user must run them manually after Phase 1 and 2 are committed.

### 3.1 Install TA-Lib C library (system prerequisite)
- [ ] **Windows**: Download pre-built wheel from `https://github.com/cgohlke/talib-build/releases` matching Python 3.12 / win_amd64. Install with `pip install TA_Lib-{version}-cp312-win_amd64.whl`.
- [ ] **Linux (future)**: `sudo apt-get install libta-lib-dev` (defer to Phase 14 Docker work).

### 3.2 Create virtual environment
```bash
cd "C:/Users/Pablo Nieto/codigos/IRT"
python -m venv .venv
```

### 3.3 Activate and install dependencies
```bash
.venv/Scripts/activate
pip install -e packages/ibkr-core
pip install -e packages/backtest-engine
pip install -r requirements.txt
```

Order matters: editable installs first so `ibkr_core` is importable when the engine package's setup resolves its dependency.

### 3.4 Configure worker/.env
- [ ] Copy `worker/.env.example` to `worker/.env` (if not already present)
- [ ] Set `ENGINE_PATH=packages/backtest-engine/main.py`
- [ ] Set `HIST_DATA_PATH` to the actual historical data directory on the dev machine
- [ ] Set `IRT_API_URL` and any other environment-specific values

---

## Phase 4: Validation

### 4.1 Smoke test -- verify `_resolve_python()` finds the venv
```bash
cd "C:/Users/Pablo Nieto/codigos/IRT"
python -c "from worker.engine import _resolve_python; print(_resolve_python())"
```
- [ ] Output should be `C:\Users\Pablo Nieto\codigos\IRT\.venv\Scripts\python.exe`

### 4.2 Import test -- verify `ibkr_core` is importable from the venv
```bash
.venv/Scripts/python -c "import ibkr_core; print('ibkr_core OK')"
```
- [ ] No `ModuleNotFoundError`

### 4.3 Engine CLI test -- verify engine bare imports work
```bash
.venv/Scripts/python packages/backtest-engine/main.py --help
```
- [ ] Prints usage/help text, no `ImportError`

### 4.4 Compat test -- verify `HAS_IB` is False (no ib_async)
```bash
.venv/Scripts/python -c "from ibkr_core._compat import HAS_IB; assert not HAS_IB; print('HAS_IB=False OK')"
```
- [ ] Assertion passes

### 4.5 Integration test -- start worker, run a simple backtest
- [ ] Start the worker: `python -m worker.main`
- [ ] Submit a single-strategy backtest job via the API
- [ ] Verify the engine subprocess launches, completes, and returns metrics JSON
- [ ] No `ModuleNotFoundError` or path-resolution errors in worker logs

### 4.6 Integration test -- run a complete backtest (with parquet output)
- [ ] Submit a "complete" mode backtest job (with `--save` flag)
- [ ] Verify `_find_parquet()` locates `trades.parquet` under `packages/backtest-engine/logs_backtest/`
- [ ] Verify backtest results are returned to the API

---

## Phase 5: Cleanup -- COPIED_FROM markers, commit

### 5.1 Add COPIED_FROM marker to `packages/ibkr-core/pyproject.toml`
File: `packages/ibkr-core/pyproject.toml`

- [ ] Add a comment at the top of the file:
```toml
# COPIED_FROM: Operations-Platform/packages/ibkr-core @ <commit-hash>
# Date: 2026-03-25
# This is an intentional fork. IRT owns this copy going forward.
```
- [ ] Replace `<commit-hash>` with the actual HEAD commit hash from `C:/Users/Pablo Nieto/codigos/Operations-Platform` at the time of copy

### 5.2 Add COPIED_FROM marker to `packages/backtest-engine/pyproject.toml`
File: `packages/backtest-engine/pyproject.toml`

- [ ] Add a comment at the top of the file:
```toml
# COPIED_FROM: Operations-Platform/packages/backtest-engine @ <commit-hash>
# Date: 2026-03-25
# This is an intentional fork. IRT owns this copy going forward.
```
- [ ] Use the same commit hash as 5.1 (both come from the same repo)

### 5.3 Commit all changes
- [ ] Stage all new files in `packages/` (37 files)
- [ ] Stage modified files: `worker/engine.py`, `worker/.env.example`, `requirements.txt`, `.gitignore`
- [ ] Stage already-modified (uncommitted) worker files: `worker/orchestrator.py`, `worker/main.py`, `worker/config.py`
- [ ] Commit with message: `feat: internalize backtest-engine and ibkr-core into IRT (Phase 12.1)`
- [ ] Verify with `git status` that no unintended files were included
- [ ] Verify `.venv/` is NOT in the commit (should be gitignored)

---

## Notes

- **TA-Lib C library**: This is a system-level prerequisite. It cannot be installed via `pip install -r requirements.txt` alone. The `TA-Lib>=0.6.0` Python package requires the C library to already be present. See Phase 3.1 for install instructions.
- **No engine source modifications**: All 37 copied files are verbatim from Operations-Platform. The only modifications are the `COPIED_FROM` markers added to `pyproject.toml` files in Phase 5.
- **Subprocess pattern preserved**: The worker continues invoking the engine via `subprocess.run()`. No import-level changes to the engine.
- **Phases 1-2 and 5 are automatable** via sdd-apply. **Phases 3-4 are manual** (user must create the venv, install deps, and run validation commands).
