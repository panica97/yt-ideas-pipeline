"""IRT Backtest Worker -- polls the IRT API for pending jobs and executes them.

Entry point: ``python -m worker.main``

The worker runs on the HOST machine (not inside Docker). It communicates
with the IRT API via HTTP to discover, claim, and report backtest jobs.
"""

import signal
import sys
import time
import logging

import requests

from worker.config import Config
from worker.executor import execute_backtest_job

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("irt-worker")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_running: bool = True


def _shutdown(signum, frame):  # noqa: ANN001
    global _running
    logger.info("Received signal %s, finishing current job then shutting down...", signum)
    _running = False


# ---------------------------------------------------------------------------
# Poll helpers
# ---------------------------------------------------------------------------

def get_pending_job(config: Config) -> dict | None:
    """Fetch the next pending job from the API.

    Returns the job dict or None if no work is available (HTTP 204).
    """
    resp = config.session.get(f"{config.api_url}/api/backtests/pending", timeout=10)
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


def claim_job(config: Config, job_id: int) -> dict:
    """Atomically claim a pending job by transitioning it to 'running'."""
    resp = config.session.patch(f"{config.api_url}/api/backtests/{job_id}/claim", timeout=10)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    config = Config()
    logger.info("Worker started | %s", config.log_summary())

    while _running:
        try:
            job = get_pending_job(config)
            if job is None:
                time.sleep(config.poll_interval)
                continue

            job_id = job["id"]
            logger.info("Found pending job %d (draft=%d, symbol=%s)", job_id, job["draft_strat_code"], job["symbol"])

            # Claim the job (transition to running)
            try:
                job = claim_job(config, job_id)
                logger.info("Claimed job %d — status is now 'running'", job_id)
            except requests.HTTPError as exc:
                # Another worker may have claimed it first (409), skip
                logger.warning("Failed to claim job %d: %s", job_id, exc)
                continue

            # Execute
            execute_backtest_job(job, config)

        except requests.ConnectionError:
            logger.error("Cannot reach API at %s — retrying in %ds", config.api_url, config.poll_interval)
            time.sleep(config.poll_interval)
        except Exception:
            logger.exception("Unexpected error in poll loop")
            time.sleep(config.poll_interval)

    logger.info("Worker shut down gracefully.")


if __name__ == "__main__":
    main()
