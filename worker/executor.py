"""Job Executor -- orchestrates draft export, engine run, and result reporting.

This module ties together the bridge (draft export), engine (subprocess run),
and result reporting (HTTP calls back to the IRT API). It handles cleanup
and error reporting so the main poll loop stays clean.
"""

import logging
import time
from pathlib import Path

from worker.bridge import export_draft_to_file
from worker.config import Config
from worker.engine import run_engine

logger = logging.getLogger("irt-worker.executor")


def _report_success(config: Config, job_id: int, metrics: dict, trades: list) -> None:
    """Post backtest results to the API."""
    resp = config.session.post(
        f"{config.api_url}/api/backtests/{job_id}/results",
        json={"metrics": metrics, "trades": trades},
        timeout=15,
    )
    resp.raise_for_status()


def _report_failure(config: Config, job_id: int, error_message: str) -> None:
    """Mark a backtest job as failed via the API."""
    # Truncate to 2000 chars to avoid unbounded storage
    truncated = error_message[-2000:] if len(error_message) > 2000 else error_message
    try:
        resp = config.session.patch(
            f"{config.api_url}/api/backtests/{job_id}/fail",
            json={"error_message": truncated},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to report failure for job %d", job_id)


def _cleanup_temp_file(strat_code: int) -> None:
    """Remove the temporary strategy file if it exists."""
    import tempfile
    strat_file = Path(tempfile.gettempdir()) / "irt-backtests" / f"{strat_code}.json"
    try:
        if strat_file.exists():
            strat_file.unlink()
            logger.debug("Cleaned up temp file %s", strat_file)
    except OSError:
        logger.warning("Failed to clean up temp file %s", strat_file)


def execute_backtest_job(job: dict, config: Config) -> None:
    """Execute a single backtest job end-to-end.

    Steps:
    1. Export draft data to a temp JSON file (bridge).
    2. Run the backtest engine as a subprocess (engine).
    3. Report results (success) or error (failure) back to the API.
    4. Clean up temp files regardless of outcome.

    This function never raises -- all exceptions are caught, logged,
    and reported as job failures so the main poll loop continues.
    """
    job_id = job["id"]
    strat_code = job["draft_strat_code"]
    start_time = time.time()

    strategies_path: str | None = None

    try:
        # 1. Export draft to temp file
        strategies_path = export_draft_to_file(job, config)

        # 2. Run engine
        metrics = run_engine(job, strategies_path, config)

        # 3. Extract trades if present in metrics (engine may include them)
        trades = []
        if isinstance(metrics, dict) and "trades" in metrics:
            trades = metrics.pop("trades", [])

        # 4. Report success
        _report_success(config, job_id, metrics, trades)

        duration = time.time() - start_time
        logger.info(
            "Job %d completed successfully in %.1fs (strat_code=%d)",
            job_id, duration, strat_code,
        )

    except Exception as exc:
        duration = time.time() - start_time
        error_msg = str(exc)
        logger.error(
            "Job %d failed after %.1fs: %s", job_id, duration, error_msg
        )
        _report_failure(config, job_id, error_msg)

    finally:
        _cleanup_temp_file(strat_code)
