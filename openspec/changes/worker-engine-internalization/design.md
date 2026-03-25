# Design: Worker Engine Internalization

## Technical Approach

Make IRT fully self-contained by copying `backtest-engine` and `ibkr-core` packages from Operations-Platform into `IRT/packages/`, creating a local `.venv` with all dependencies, and rewriting `_resolve_python()` to use that local venv. The subprocess invocation pattern is preserved -- the only thing that changes is WHERE the engine lives and WHICH Python runs it.

Key principle: **zero modifications to engine or ibkr-core source code**. They are copied verbatim. All adaptation happens in the IRT worker layer and environment configuration.

---

## Architecture Decisions

### Decision: Keep subprocess invocation pattern (no in-process import)

**Choice**: Continue invoking the engine as `subprocess.run([python_exe, engine_main_py, ...])`.

**Alternatives considered**:
- Import the engine directly into the worker process (eliminates subprocess overhead).
- Use `runpy.run_path()` to run `main.py` in the same process.

**Rationale**: The engine uses bare imports (`from constants import ...`, `from engine._10_backtester import ...`) that rely on `sys.path` manipulation at startup. Running it in-process would pollute the worker's `sys.path` and risk import conflicts. The subprocess boundary is clean and proven. The overhead (~200ms startup) is negligible compared to backtest duration (seconds to minutes).

### Decision: Resolve venv from `__file__` location, not ENGINE_PATH

**Choice**: `_resolve_python()` navigates from `worker/engine.py` to `IRT/.venv` using `Path(__file__).resolve().parent.parent` (worker/ -> IRT root).

**Alternatives considered**:
- Derive venv from `ENGINE_PATH` (current approach, navigating upward from engine location).
- Add a dedicated `VENV_PATH` environment variable.
- Use `sys.executable` unconditionally (requires activating the venv before running the worker).

**Rationale**: Navigating from `__file__` is deterministic -- it always resolves correctly regardless of how `ENGINE_PATH` is configured. No extra env var needed. The `sys.executable` fallback is preserved for environments where `.venv` doesn't exist (e.g., CI containers with global installs).

### Decision: Use relative ENGINE_PATH (relative to project root)

**Choice**: `ENGINE_PATH=packages/backtest-engine/main.py` (relative path).

**Alternatives considered**:
- Absolute path (`C:/Users/.../IRT/packages/backtest-engine/main.py`).
- No `ENGINE_PATH` at all (hardcode in `config.py`).

**Rationale**: Relative path is portable across machines and developers. The worker is always launched from the IRT project root (`python -m worker.main`), so relative paths resolve correctly. `ENGINE_PATH` remains a config variable for flexibility (e.g., pointing to a different engine version for testing).

### Decision: Single .venv at IRT root with editable installs

**Choice**: One `.venv` at `IRT/.venv`. Both `ibkr-core` and `backtest-engine` installed via `pip install -e`.

**Alternatives considered**:
- Separate venvs per package.
- No editable install; rely solely on `sys.path` manipulation.
- Install packages as non-editable wheels.

**Rationale**: A single venv keeps the setup simple. Editable installs make `ibkr_core` importable (the engine imports it via standard `import ibkr_core`). The engine's own `sys.path.insert(0, PROJECT_ROOT)` handles its bare internal imports. Non-editable installs would work too, but editable installs are better during development since changes to the copied files take effect immediately.

### Decision: Do not install ib_async

**Choice**: Omit `ib_async` from requirements. Rely on `ibkr_core/_compat.py`'s `HAS_IB = False` guard.

**Alternatives considered**:
- Install `ib_async` anyway "just in case".

**Rationale**: IRT only uses backtest mode. `_compat.py` already handles missing `ib_async` gracefully -- it sets `HAS_IB = False` and provides `_require_ib()` which raises a clear error only if live-trading features are called. Installing it would add unnecessary dependencies (`ib_async` pulls in `eventkit`, etc.) and could cause confusion about IRT's capabilities.

---

## Data Flow

```
Worker launch
=============
  python -m worker.main          (from IRT project root)
       |
       v
  Config() loads worker/.env
       |  ENGINE_PATH = "packages/backtest-engine/main.py"
       |  HIST_DATA_PATH = "D:/HistData/futures"
       v
  Orchestrator.run()
       |
       v  (per job, in slot thread)
  execute_backtest_job(job, config)
       |
       v
  run_engine(job, strategies_path, config)
       |
       |  1. _resolve_python()
       |     Path(__file__)             = IRT/worker/engine.py
       |     .parent.parent             = IRT/
       |     + .venv/Scripts/python.exe = IRT/.venv/Scripts/python.exe
       |
       |  2. Build command:
       |     [IRT/.venv/Scripts/python.exe,
       |      packages/backtest-engine/main.py,
       |      --mode, single, --strategy, 1001, ...]
       |
       |  3. subprocess.run(cmd, ...)
       |
       v
  Engine subprocess (separate process)
  =====================================
    main.py startup:
      PROJECT_ROOT = Path(__file__).parent   # packages/backtest-engine/
      sys.path.insert(0, PROJECT_ROOT)       # bare imports work
      ENGINE_PATH  = PROJECT_ROOT / 'engine'
      sys.path.insert(0, ENGINE_PATH)        # engine.* imports work

    import ibkr_core   <-- resolved from .venv editable install
    from constants import ...   <-- resolved from sys.path[0]
    from engine._10_backtester import ...  <-- resolved from sys.path

    Engine runs backtest, writes:
      stdout: ###METRICS_JSON_START###{...}###METRICS_JSON_END###
      disk:   packages/backtest-engine/logs_backtest/  (if --save)
       |
       v
  Worker reads stdout markers, parses JSON
  Worker reads logs_backtest/ for trades.parquet (if --save)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `packages/ibkr-core/` | CREATE (14 files) | Copy ibkr-core package from Ops-Platform (verbatim) |
| `packages/ibkr-core/trading_calendar.json` | CREATE (duplicate) | Extra copy at parent level for `Path(__file__).parent.parent` resolution in `trading_calendar.py` |
| `packages/backtest-engine/` | CREATE (22 files) | Copy backtest-engine from Ops-Platform (verbatim) |
| `worker/engine.py` | MODIFY | Rewrite `_resolve_python()` to use IRT root `.venv` |
| `worker/.env.example` | MODIFY | Update `ENGINE_PATH` to `packages/backtest-engine/main.py` |
| `requirements.txt` | MODIFY | Merge all dependencies (IRT + worker + ibkr-core + engine) |
| `.gitignore` | MODIFY | Add `.venv/`, engine log dirs, package bytecode |

**Files NOT modified** (already complete from prior work):
- `worker/main.py` -- orchestrator entry point (no changes needed)
- `worker/config.py` -- reads `ENGINE_PATH` from env (no changes needed)
- `worker/orchestrator.py` -- parallel job orchestrator (no changes needed)
- `worker/executor.py` -- calls `run_engine()` (no changes needed)

---

## Interfaces / Contracts

### `_resolve_python()` -- New Implementation

```python
def _resolve_python() -> str:
    """Resolve the Python executable to use for the engine subprocess.

    Uses the .venv at the IRT project root (parent of worker/ directory)
    so that ibkr_core and other engine dependencies are available.
    Falls back to sys.executable if .venv is not found.
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

**Contract**: Returns the absolute path to the Python executable. Caller (`run_engine()`) uses it as `cmd[0]` in `subprocess.run()`. The returned Python MUST have `ibkr_core`, `polars`, `numpy`, `pandas`, `TA-Lib`, and all other engine deps installed.

### ENGINE_PATH Contract

**Value**: `packages/backtest-engine/main.py` (relative to IRT project root).

**Resolution**: `config.engine_path` stores the raw string. It is used directly in `subprocess.run()` command list. Since the worker runs from IRT root (`python -m worker.main`), the relative path resolves correctly via the OS.

**Used by**:
- `run_engine()` in `worker/engine.py` line 93: `cmd = [python_exe, config.engine_path, "--mode", ...]`
- `_find_parquet()` in `worker/engine.py` line 179: `Path(Config().engine_path).parent` -> `packages/backtest-engine/` -> looks for `logs_backtest/` there.

### requirements.txt -- Full Merged Contents

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

**Note**: `ibkr-core` and `backtest-engine` themselves are NOT listed here -- they are installed separately via `pip install -e packages/ibkr-core` and `pip install -e packages/backtest-engine`. This file covers their transitive dependencies that are pip-installable from PyPI.

### .gitignore Additions

```gitignore
# Python virtual environment
.venv/

# Engine runtime artifacts (generated by backtest runs)
packages/backtest-engine/logs_backtest/
packages/backtest-engine/logs_portfolio/
packages/backtest-engine/logs_system/
packages/backtest-engine/logs_integration_test/
packages/backtest-engine/logs_comparison/
packages/backtest-engine/logs_stress_test/

# Package bytecode
packages/**/__pycache__/

# Debug JSON output from worker
data/backtests/debug/
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Smoke | `.venv` exists and `_resolve_python()` finds it | Run `python -c "from worker.engine import _resolve_python; print(_resolve_python())"` -- should print `.venv/Scripts/python.exe` |
| Import | `ibkr_core` importable from the venv | Run `IRT/.venv/Scripts/python -c "import ibkr_core; print(ibkr_core.__all__)"` |
| Import | Engine bare imports work | Run `IRT/.venv/Scripts/python packages/backtest-engine/main.py --help` -- should print usage, not ImportError |
| Compat | `HAS_IB` is False, no crash | Run `IRT/.venv/Scripts/python -c "from ibkr_core._compat import HAS_IB; assert not HAS_IB; print('OK')"` |
| Integration | Single backtest completes | Start worker, submit a job via API, verify metrics returned. Uses a known strategy + hist data on the dev machine. |
| Parquet | `_find_parquet()` locates output | Submit a "complete" mode job, verify `trades.parquet` found under `packages/backtest-engine/logs_backtest/` |
| Fallback | Missing `.venv` falls back gracefully | Temporarily rename `.venv`, run `_resolve_python()`, verify it returns `sys.executable` |

---

## Migration / Rollout

### Fresh Machine Setup (step by step)

```bash
# 1. Clone IRT
git clone <irt-repo-url>
cd IRT

# 2. Install TA-Lib C library (system prerequisite)
#    Windows: download wheel from https://github.com/cgohlke/talib-build/releases
#             pip install TA_Lib-{version}-cp312-win_amd64.whl
#    Linux:   sudo apt-get install libta-lib-dev

# 3. Create virtual environment
python -m venv .venv

# 4. Activate
#    Windows: .venv\Scripts\activate
#    Linux:   source .venv/bin/activate

# 5. Install local packages in editable mode
pip install -e packages/ibkr-core
pip install -e packages/backtest-engine

# 6. Install all other dependencies
pip install -r requirements.txt

# 7. Configure worker environment
cp worker/.env.example worker/.env
# Edit worker/.env: set IRT_API_URL, IRT_API_KEY, HIST_DATA_PATH
# ENGINE_PATH is already set to packages/backtest-engine/main.py

# 8. Verify setup
python -c "import ibkr_core; print('ibkr_core OK')"
python packages/backtest-engine/main.py --help
python -c "from worker.engine import _resolve_python; print(_resolve_python())"

# 9. Run worker
python -m worker.main
```

### Existing Dev Machine (upgrade path)

```bash
cd C:/Users/Pablo Nieto/codigos/IRT

# 1. Pull the branch with internalized packages
git pull

# 2. Create .venv if it doesn't exist
python -m venv .venv
.venv/Scripts/activate

# 3. Install
pip install -e packages/ibkr-core
pip install -e packages/backtest-engine
pip install -r requirements.txt

# 4. Update worker/.env
#    Change ENGINE_PATH from absolute Ops-Platform path to:
#    ENGINE_PATH=packages/backtest-engine/main.py

# 5. Verify
python -m worker.main
```

---

## Open Questions

1. **COPIED_FROM marker** -- Should we add a comment to each copied `pyproject.toml` with the source commit hash from Ops-Platform? The exploration suggests it for traceability. This is low-effort but useful for future audits. **Recommendation**: Yes, add it.

2. **TA-Lib on CI/Docker** -- If IRT eventually runs in CI or Docker (Phase 14), TA-Lib's C library needs to be available. Should we document the Docker install steps now or defer? **Recommendation**: Defer to Phase 14; document only the dev machine steps now.

3. **Syncing future engine changes** -- The proposal explicitly says this is an intentional fork. If a critical bug is fixed in Ops-Platform's engine, the fix must be manually applied to IRT's copy. Is this acceptable? **Recommendation**: Yes, per Phase 12.1 design intent. The `COPIED_FROM` marker helps identify drift.
