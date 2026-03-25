# Proposal: Worker Engine Internalization

## Intent

The IRT worker currently depends on the Operations-Platform repository at runtime: it invokes `backtest-engine` as a subprocess pointing to Ops-Platform's file tree and resolves the Python interpreter from Ops-Platform's `.venv`. This cross-repo coupling means the worker cannot run unless the Operations-Platform repo is present, correctly set up, and at a compatible commit. Phase 12.1 requires making IRT fully self-contained with zero Ops-Platform dependency.

## Scope

### In Scope

- Copy `backtest-engine` (22 files) and `ibkr-core` (14 files + 1 extra `trading_calendar.json`) from Operations-Platform into `IRT/packages/`
- Rewrite `worker/engine.py` `_resolve_python()` to resolve the interpreter from IRT's own `.venv` instead of navigating to Ops-Platform
- Update `ENGINE_PATH` in `.env.example` and `.env` to point to `packages/backtest-engine/main.py`
- Create/update `requirements.txt` at IRT root with merged dependencies (IRT + worker + ibkr-core + backtest-engine)
- Update `.gitignore` with `.venv/`, engine log directories, and `packages/**/__pycache__/`
- Document the `.venv` setup procedure (venv creation + editable installs)
- Commit together with the already-completed parallel orchestrator work (`worker/orchestrator.py`, `worker/main.py`, `worker/config.py`)

### Out of Scope

- Modifying any backtest-engine or ibkr-core source code (copied as-is)
- Installing `ib_async` or other live-trading extras (IRT uses backtest mode only)
- Dockerization of the worker (deferred to Phase 14)
- Syncing future Ops-Platform engine changes back to IRT (intentional fork)
- Copying test suites from either package

## Approach

1. **File copy** -- Copy the 37 files (36 source + 1 duplicate `trading_calendar.json` at parent level) into `IRT/packages/ibkr-core/` and `IRT/packages/backtest-engine/`, preserving the original directory structure.

2. **Subprocess pattern preserved** -- The worker continues to invoke the engine as a subprocess (`python packages/backtest-engine/main.py --mode single ...`). This is the lowest-risk approach: no changes to engine internals, no import conflicts, and the same proven execution model.

3. **IRT root `.venv`** -- A single virtual environment at `IRT/.venv` holds all dependencies. Both `ibkr-core` and `backtest-engine` are installed in editable mode (`pip install -e`) so their packages are importable. The engine's own `sys.path` manipulation in `main.py` handles its bare internal imports.

4. **`_resolve_python()` rewrite** -- Instead of navigating from `ENGINE_PATH` upward to find Ops-Platform's venv, the new code navigates from `worker/engine.py` to its grandparent (IRT root) and uses `IRT/.venv/Scripts/python.exe` (Windows) or `IRT/.venv/bin/python` (Linux).

5. **`_find_parquet()` remains compatible** -- It derives the log directory from `Path(Config().engine_path).parent`, which resolves to `packages/backtest-engine/` -- the correct location for `logs_backtest/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `worker/engine.py` | HIGH | `_resolve_python()` rewritten; `_find_parquet()` path resolution changes implicitly via new `ENGINE_PATH` |
| `worker/.env.example` | LOW | `ENGINE_PATH` value updated to local path |
| `worker/.env` | LOW | `ENGINE_PATH` value updated to local path |
| `requirements.txt` | MEDIUM | Merged dependency list; new deps: polars, numpy, pandas, TA-Lib, pytz, icecream, jsonschema |
| `.gitignore` | LOW | New entries for `.venv/`, engine log dirs, package bytecode |
| `packages/` (new) | HIGH | 37 new files; entire backtest-engine and ibkr-core packages |
| `worker/orchestrator.py` | NONE | Already complete, committed together but not modified in this change |
| `worker/main.py` | NONE | Already complete, committed together but not modified in this change |
| `worker/config.py` | NONE | Already complete, committed together but not modified in this change |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Bare imports in backtest-engine fail in new location | LOW | Engine's `main.py` injects `PROJECT_ROOT` into `sys.path` at startup; subprocess invocation preserves this. Already verified in exploration. |
| `trading_calendar.json` not found by ibkr-core | LOW | Copy the file to both `ibkr_core/` (package level) and `packages/ibkr-core/` (parent level) to satisfy the `Path(__file__).parent.parent` resolution. |
| TA-Lib C library missing on host | MEDIUM | Document as a system prerequisite. On Windows: install pre-built wheel. On Linux (future Docker): install via package manager. Fail-fast with clear error message. |
| Dual-repo drift between IRT and Ops-Platform engine copies | LOW | Intentional by design. IRT owns its copy going forward. Add `COPIED_FROM` marker with source commit hash in each `pyproject.toml`. |
| `.venv` not created before first worker run | LOW | Document setup procedure. Worker falls back to `sys.executable` if `.venv` not found, which will fail on missing deps -- a clear signal to run setup. |
| `icecream` or other debug deps omitted | LOW | All transitive dependencies cataloged in exploration. Merged `requirements.txt` includes every package. |

## Rollback Plan

1. Delete `packages/` directory entirely
2. Revert `worker/engine.py` to the previous `_resolve_python()` that navigates to Ops-Platform
3. Revert `ENGINE_PATH` in `.env` / `.env.example` to the Ops-Platform absolute path
4. Revert `requirements.txt` and `.gitignore` to pre-change state
5. Delete `IRT/.venv` if it was created

Since the engine packages are copied (not moved) and no Ops-Platform files are modified, rollback is a clean revert with no data loss.

## Dependencies

- Operations-Platform repository must be accessible at copy time (source for the 37 files)
- TA-Lib C library must be installed at the system level before `pip install TA-Lib` succeeds
- Python 3.12 (matching existing IRT and Ops-Platform versions)
- The parallel orchestrator changes (`worker/orchestrator.py`, `worker/main.py`, `worker/config.py`) are already complete and will be committed alongside

## Success Criteria

- [ ] `packages/backtest-engine/` contains all 22 engine files + `data/margin_data.json`
- [ ] `packages/ibkr-core/` contains all 14 ibkr-core files + extra `trading_calendar.json` at parent level
- [ ] `worker/engine.py` `_resolve_python()` resolves to `IRT/.venv/Scripts/python.exe`
- [ ] `ENGINE_PATH` points to `packages/backtest-engine/main.py`
- [ ] `IRT/.venv` exists with all dependencies installed (editable installs for both packages)
- [ ] Worker starts without `ModuleNotFoundError` for `ibkr_core`
- [ ] Single-strategy backtest completes successfully via the worker
- [ ] No files in Operations-Platform are modified or referenced at runtime
- [ ] `.gitignore` excludes `.venv/`, engine log directories, and package bytecode
