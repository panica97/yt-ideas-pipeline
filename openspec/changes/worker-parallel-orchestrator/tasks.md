# Tasks: Worker Parallel Orchestrator

## Phase 1: Core Implementation

- [x] 1.1 Create `worker/orchestrator.py` — Port from `Operations-Platform/worker/orchestrator.py` keeping only: `WorkUnit` dataclass (fields: `job_id: int`, `job: dict`, `label: str`), `Orchestrator` class with N slot threads, fair-sharing logic, poll loop with `claim-all-pending`, and graceful shutdown via `threading.Event`. **Remove**: `SubprocessResult`, `JobState`, `JobTracker`, all finalization methods, S3/upload logic, `_resolve_python`, subprocess command building, all Ops job-type decomposition (`_decompose_single`, `_decompose_portfolio`, etc.), `_sanitize_for_json`, bucket/config references. Each slot worker thread: polls API via `get_pending_job()` + `claim_job()` (moved from `main.py`), then calls `execute_backtest_job(unit.job, config)` from `worker/executor.py`. Add `_decompose_job(job) -> list[WorkUnit]`: for IRT both `simple` and `complete` modes produce exactly 1 WorkUnit. Use `config.poll_interval` for sleep between polls. Reference files: `C:/Users/Pablo Nieto/codigos/Operations-Platform/worker/orchestrator.py` (source to adapt), `worker/executor.py` (slot target), `worker/main.py` (functions to move).

- [x] 1.2 Add `num_slots: int` field to `worker/config.py` — Read from `WORKER_NUM_SLOTS` env var with default `3`. Include in `log_summary()` output string as `num_slots={self.num_slots}`.

- [x] 1.3 Rewrite `worker/main.py` — Remove `get_pending_job()`, `claim_job()`, `_running` global, `_shutdown()` handler, and the `while _running` poll loop. Replace with: instantiate `Config`, instantiate `Orchestrator(config)`, call `orchestrator.run()`. Signal handlers (`SIGTERM`, `SIGINT`) call `orchestrator.stop()`. Target: ~35 lines total. Keep logging setup and `if __name__ == "__main__"` block.

- [x] 1.4 Add `WORKER_NUM_SLOTS=3` to `worker/.env` and add `WORKER_NUM_SLOTS=3` with comment to `worker/.env.example` (below `WORKER_JOB_TIMEOUT`).

## Phase 2: Validation

- [ ] 2.1 Start worker (`python -m worker.main`), verify log output shows "N slots" and polling begins without errors.
- [ ] 2.2 Run a single simple-mode backtest job — verify metrics returned correctly and job marked completed in API.
- [ ] 2.3 Run a single complete-mode backtest with timeframe remapping — verify trades + equity curve data returned in results.
- [ ] 2.4 Queue 2+ backtest jobs simultaneously — verify parallel execution visible in logs (multiple "Claimed job" lines before first "Job completed").
- [ ] 2.5 Test graceful shutdown (Ctrl+C / SIGINT) — verify current running job(s) finish before worker exits, log shows "shut down gracefully".
