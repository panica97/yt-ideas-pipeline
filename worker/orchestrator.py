"""Worker Orchestrator -- N-slot parallel job scheduler with fair sharing.

Claims all pending jobs, decomposes them into work units,
and schedules them across worker threads in FIFO order.

Fair sharing: each job's max concurrent slots is dynamically capped to
``max(1, num_slots - num_active_jobs)`` so no single job can starve others.
When only one job is running it gets all N slots; with 2 jobs each gets
up to N-1, etc.
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from worker.config import Config
from worker.executor import execute_backtest_job

logger = logging.getLogger("irt-worker.orchestrator")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WorkUnit:
    job_id: int
    unit_id: str
    job: dict
    label: str


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Claims jobs, decomposes them into work units, and schedules
    them across worker threads with dynamic fair sharing."""

    def __init__(self, config: Config):
        self._config = config
        self._queue: queue.Queue[WorkUnit] = queue.Queue()
        self._num_slots = config.num_slots
        self._shutdown_event = threading.Event()

        # Fair-sharing: track how many slots each job is currently using
        self._active_counts: Dict[int, int] = {}  # job_id -> running units
        self._active_lock = threading.Lock()

    # -- public API --------------------------------------------------------

    def run(self) -> None:
        """Start slot threads and enter the poll loop. Blocks until stop()."""
        threads = []
        for i in range(self._num_slots):
            t = threading.Thread(
                target=self._slot_worker, name=f"slot-{i}", daemon=True)
            t.start()
            threads.append(t)
        logger.info("Started %d worker slots", self._num_slots)

        while not self._shutdown_event.is_set():
            try:
                claimed = self._claim_all_pending()
                for job in claimed:
                    try:
                        units = self._decompose_job(job)
                        if not units:
                            logger.warning(
                                "Job %d produced no work units, skipping",
                                job["id"])
                            continue

                        for unit in units:
                            self._queue.put(unit)
                        logger.info(
                            "Job %d (mode=%s) -> %d unit(s) enqueued",
                            job["id"], job.get("mode", "simple"), len(units))
                    except Exception as exc:
                        logger.error(
                            "Failed to decompose job %d: %s",
                            job["id"], exc, exc_info=True)
            except requests.ConnectionError:
                logger.error(
                    "Cannot reach API at %s — retrying in %ds",
                    self._config.api_url, self._config.poll_interval)
            except Exception as exc:
                logger.error("Error in poll loop: %s", exc, exc_info=True)

            # Sleep in small increments for responsive shutdown
            for _ in range(self._config.poll_interval * 2):
                if self._shutdown_event.is_set():
                    break
                time.sleep(0.5)

        logger.info("Shutdown signaled, waiting for active slots to finish...")
        for t in threads:
            t.join(timeout=self._config.job_timeout)
        logger.info("All slots finished.")

    def stop(self) -> None:
        """Signal all threads to stop after current work completes."""
        self._shutdown_event.set()

    # -- polling -----------------------------------------------------------

    def _claim_all_pending(self) -> List[Dict[str, Any]]:
        """Fetch all pending jobs from the API and claim them."""
        claimed: List[Dict[str, Any]] = []

        while not self._shutdown_event.is_set():
            resp = self._config.session.get(
                f"{self._config.api_url}/api/backtests/pending", timeout=10)
            if resp.status_code == 204:
                break
            resp.raise_for_status()
            job = resp.json()

            job_id = job["id"]
            logger.info(
                "Found pending job %d (draft=%d, symbol=%s)",
                job_id, job["draft_strat_code"], job["symbol"])

            # Claim the job (transition to running)
            try:
                claim_resp = self._config.session.patch(
                    f"{self._config.api_url}/api/backtests/{job_id}/claim",
                    timeout=10)
                claim_resp.raise_for_status()
                job = claim_resp.json()
                logger.info("Claimed job %d — status is now 'running'", job_id)
                claimed.append(job)
            except requests.HTTPError as exc:
                # Another worker may have claimed it first (409), skip
                logger.warning("Failed to claim job %d: %s", job_id, exc)

        return claimed

    # -- decomposition -----------------------------------------------------

    def _decompose_job(self, job: Dict[str, Any]) -> List[WorkUnit]:
        """Create WorkUnits from a claimed job.

        Both 'simple' and 'complete' modes produce exactly 1 WorkUnit.
        """
        job_id = job["id"]
        mode = job.get("mode", "simple")
        return [WorkUnit(
            job_id=job_id,
            unit_id=f"{mode}_{job_id}",
            job=job,
            label=f"{mode}:job-{job_id}",
        )]

    # -- fair sharing ------------------------------------------------------

    def _job_cap(self) -> int:
        """Dynamic per-job slot cap: max(1, num_slots - num_active_jobs).

        Called under ``_active_lock``.
        """
        active_jobs = sum(1 for c in self._active_counts.values() if c > 0)
        return max(1, self._num_slots - active_jobs)

    # -- slot thread -------------------------------------------------------

    def _slot_worker(self) -> None:
        """Runs in each of the worker threads. Dequeues and executes units,
        respecting the dynamic per-job concurrency cap."""
        while not self._shutdown_event.is_set():
            try:
                unit = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # --- Fair-sharing gate ---
            with self._active_lock:
                current = self._active_counts.get(unit.job_id, 0)
                cap = self._job_cap()
                if current >= cap:
                    # This job is at its cap -- re-queue and back off
                    self._queue.put(unit)
                    time.sleep(0.2)
                    continue
                self._active_counts[unit.job_id] = current + 1

            try:
                logger.info("[%s] Starting execution", unit.label)
                execute_backtest_job(unit.job, self._config)
                logger.info("[%s] Completed", unit.label)
            except Exception as exc:
                logger.error(
                    "[%s] Failed: %s", unit.label, exc, exc_info=True)
            finally:
                with self._active_lock:
                    self._active_counts[unit.job_id] = (
                        self._active_counts.get(unit.job_id, 1) - 1)
                    if self._active_counts.get(unit.job_id, 0) <= 0:
                        self._active_counts.pop(unit.job_id, None)
