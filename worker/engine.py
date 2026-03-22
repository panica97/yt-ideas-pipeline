"""Engine Runner -- invokes the backtest engine as a subprocess and parses output.

The engine is called via its CLI interface with ``--metrics-json``, which causes
it to emit a JSON block delimited by markers in stdout:

    ###METRICS_JSON_START###{...json...}###METRICS_JSON_END###

This module builds the CLI command, runs the subprocess, and extracts the
parsed metrics dict.
"""

import json
import logging
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from worker.config import Config

logger = logging.getLogger("irt-worker.engine")

# Marker constants (must match the engine output format)
METRICS_START = "###METRICS_JSON_START###"
METRICS_END = "###METRICS_JSON_END###"


def _resolve_python() -> str:
    """Resolve the Python executable to use for the engine subprocess.

    Prefers the venv Python from the ops-worker installation so that
    ibkr_core and other engine dependencies are available.
    """
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


def _sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Inf float values with None for valid JSON storage."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def run_engine(job: dict, strategies_path: str, config: Config) -> dict:
    """Run the backtest engine subprocess and return parsed metrics.

    Parameters
    ----------
    job : dict
        Backtest job dict with ``draft_strat_code``, ``start_date``, ``end_date``.
    strategies_path : str
        Path to directory containing the strategy JSON file.
    config : Config
        Worker configuration (engine_path, hist_data_path, job_timeout).

    Returns
    -------
    dict
        Parsed metrics dict from engine output.

    Raises
    ------
    RuntimeError
        On subprocess timeout, non-zero exit, missing markers, or JSON parse error.
    """
    strat_code = job["draft_strat_code"]
    python_exe = _resolve_python()

    cmd = [
        python_exe,
        config.engine_path,
        "--mode", "single",
        "--strategy", str(strat_code),
        "--start", job["start_date"],
        "--end", job["end_date"],
        "--metrics-json",
        "--hist-data-path", config.hist_data_path,
        "--strategies-path", strategies_path,
    ]

    logger.info("Running engine: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.job_timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Backtest timed out after {config.job_timeout}s"
        )

    # Log stderr for debugging (engine prints logs there)
    if result.stderr:
        for line in result.stderr.strip().splitlines()[-10:]:
            logger.debug("engine stderr: %s", line)

    # Check exit code
    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"Engine exited with code {result.returncode}: {stderr_tail}"
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
            f"No metrics markers found in engine stdout. Tail: {stdout_tail}"
        )

    raw_json = match.group(1).strip()
    try:
        metrics = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse metrics JSON: {exc}. Raw: {raw_json[:500]}"
        )

    # Sanitize NaN/Inf values
    metrics = _sanitize_for_json(metrics)

    logger.info(
        "Engine completed for strat_code=%d — %d keys in metrics",
        strat_code,
        len(metrics) if isinstance(metrics, dict) else 0,
    )
    return metrics
