"""Monte Carlo Engine Runner -- invokes the MC runner as a subprocess and parses output.

The MC runner is called via its CLI with ``--metrics-json``, which causes
it to emit a JSON block delimited by markers in stdout (same protocol as
the backtest engine):

    ###METRICS_JSON_START###{...json...}###METRICS_JSON_END###

This module builds the CLI command, runs the subprocess, and extracts the
parsed metrics dict.
"""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from worker.config import Config
from worker.engine import METRICS_END, METRICS_START, _resolve_python, _sanitize_for_json

logger = logging.getLogger("irt-worker.mc-engine")

# Default MC timeout: 2 hours (MC simulations with many paths take long)
MC_TIMEOUT = 7200


def run_montecarlo(
    job: dict, strategies_path: str, config: Config
) -> dict:
    """Run the Monte Carlo runner subprocess and return parsed metrics.

    Parameters
    ----------
    job : dict
        Backtest job dict with ``draft_strat_code``, ``n_paths``, ``fit_years``.
    strategies_path : str
        Path to directory containing the strategy JSON file.
    config : Config
        Worker configuration (mc_runner_path, hist_data_path).

    Returns
    -------
    dict
        Parsed metrics/summary dict from MC runner output.

    Raises
    ------
    RuntimeError
        On subprocess timeout, non-zero exit, missing markers, or JSON parse error.
    """
    strat_code = job["draft_strat_code"]
    n_paths = job.get("n_paths") or 1000
    fit_years = job.get("fit_years") or 10

    python_exe = _resolve_python()
    mc_runner_path = config.mc_runner_path

    cmd = [
        python_exe,
        mc_runner_path,
        "--mode", "path_based",
        "--strategy", str(strat_code),
        "--n-paths", str(n_paths),
        "--fit-years", str(fit_years),
        "--metrics-json",
        "--save",
        "--hist-data-path", config.hist_data_path,
        "--strategies-path", strategies_path,
    ]

    logger.info("Running MC: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Monte Carlo timed out after {MC_TIMEOUT}s"
        )

    # Log stderr for debugging
    if result.stderr:
        for line in result.stderr.strip().splitlines()[-20:]:
            logger.debug("mc stderr: %s", line)

    # Check exit code
    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"MC runner exited with code {result.returncode}: {stderr_tail}"
        )

    # Parse metrics from stdout markers
    match = re.search(
        re.escape(METRICS_START) + r"(.+?)" + re.escape(METRICS_END),
        result.stdout,
        re.DOTALL,
    )
    if not match:
        stdout_tail = result.stdout[-500:] if result.stdout else "(no stdout)"
        raise RuntimeError(
            f"No metrics markers found in MC stdout. Tail: {stdout_tail}"
        )

    raw_json = match.group(1).strip()
    try:
        metrics = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse MC metrics JSON: {exc}. Raw: {raw_json[:500]}"
        )

    # Sanitize NaN/Inf values
    metrics = _sanitize_for_json(metrics)

    logger.info(
        "MC completed for strat_code=%d — %d keys in metrics",
        strat_code,
        len(metrics) if isinstance(metrics, dict) else 0,
    )
    return metrics
