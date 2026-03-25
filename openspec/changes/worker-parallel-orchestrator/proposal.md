# Proposal: Worker Parallel Orchestrator

## Intent

The IRT backtest worker currently processes jobs one at a time in a single-threaded poll loop. When multiple backtest jobs are queued (common when a user launches backtests for several strategies or symbols), they execute sequentially, leaving CPU and I/O capacity unused. The Operations Platform already solved this with a slot-based parallel orchestrator. This change adapts that proven pattern into IRT so the worker can run N jobs concurrently with fair sharing across users/strategies.

## Scope

### In Scope
- New `worker/orchestrator.py` -- adapted from Ops Platform with N slot threads, fair-sharing queue, WorkUnit dataclass, and shutdown handling. Each slot calls IRT's existing `execute_backtest_job()` instead of raw subprocesses.
- Rewrite `worker/main.py` -- replace the single-threaded poll-execute loop with orchestrator launch (~35 lines).
- Modify `worker/config.py` -- add `WORKER_NUM_SLOTS` config field (default 3).
- Modify `worker/.env` and `worker/.env.example` -- add `WORKER_NUM_SLOTS=3`.

### Out of Scope
- Changes to `worker/bridge.py`, `worker/engine.py`, `worker/executor.py` -- these remain untouched.
- Changes to the API or frontend -- job claiming, reporting, and UI are unchanged.
- Ops Platform artifacts: S3 upload, run records, data catalog, bucket config, all Ops-specific job types, finalization/decomposition methods -- all removed, not ported.
- Dynamic slot scaling or auto-tuning -- deferred to a future phase.
- Queue persistence or crash recovery -- the API already handles re-queuing failed/stale jobs.

## Approach

1. **Create `worker/orchestrator.py`**: Port the Ops Platform Orchestrator class, stripping all Ops-specific concerns (S3, run records, data catalog, Ops job types, finalization, decomposition). Keep: `Orchestrator` class, `WorkUnit` dataclass, slot worker threads, fair-sharing logic, graceful shutdown via threading.Event. Each slot thread polls the IRT API for a pending job, claims it, then calls `execute_backtest_job(job, config)`.

2. **Rewrite `worker/main.py`**: Remove the poll loop, `get_pending_job()`, and `claim_job()` helpers. Replace with: instantiate Config, instantiate Orchestrator(config), call `orchestrator.run()`. Signal handlers set the orchestrator's shutdown event. Move `get_pending_job` and `claim_job` into the orchestrator (they become its internal fetch mechanism).

3. **Extend `worker/config.py`**: Add `self.worker_num_slots = int(os.environ.get("WORKER_NUM_SLOTS", "3"))` and include it in `log_summary()`.

4. **Update env files**: Add `WORKER_NUM_SLOTS=3` to both `.env` and `.env.example`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `worker/orchestrator.py` | New | Parallel orchestrator with slot threads and fair sharing |
| `worker/main.py` | Modified | Replaced poll loop with orchestrator launch |
| `worker/config.py` | Modified | Added `WORKER_NUM_SLOTS` setting |
| `worker/.env` | Modified | Added `WORKER_NUM_SLOTS=3` |
| `worker/.env.example` | Modified | Added `WORKER_NUM_SLOTS=3` with documentation |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Multiple slots claim the same job (race condition) | Low | The API's `/claim` endpoint already uses atomic DB transitions; concurrent claim attempts return 409, which the orchestrator handles gracefully |
| Thread-safety issues in `execute_backtest_job` or its dependencies | Low | `execute_backtest_job` uses per-job temp files with unique strat_code names, per-job HTTP calls, and subprocess isolation via `run_engine`. No shared mutable state. |
| Resource contention (CPU/disk) with 3+ concurrent engine subprocesses | Med | Default to 3 slots (conservative). Configurable via env var so users can tune for their hardware. |
| Logging interleaving from concurrent threads | Low | Each log line already includes job ID context. Thread-safe Python logging is standard. |

## Rollback Plan

1. Revert the 4 changed/added files to their pre-change state (`git revert` or `git checkout` the commit).
2. The worker returns to single-threaded polling. No database migration, no API change, no data format change -- rollback is purely a code revert with zero side effects.

## Dependencies

- The Ops Platform orchestrator code must be accessible as reference for the port (developer has access).
- The API's `/api/backtests/pending` and `/api/backtests/{id}/claim` endpoints must continue to work correctly under concurrent access (they already do -- atomic DB claims with 409 on conflict).

## Success Criteria

- [ ] Worker starts with N slot threads (configurable via `WORKER_NUM_SLOTS`)
- [ ] With 3+ pending jobs, all 3 slots execute concurrently (visible in logs)
- [ ] Job claiming remains race-free (409 conflicts handled, no duplicate execution)
- [ ] Graceful shutdown: SIGINT/SIGTERM causes all slots to finish current work then exit
- [ ] Single pending job still works correctly (no regression from parallel infrastructure)
- [ ] `WORKER_NUM_SLOTS=1` behaves identically to the old single-threaded worker
