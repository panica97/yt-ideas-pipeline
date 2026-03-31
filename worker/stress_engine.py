"""Stress Test Engine Runner -- invokes the stress-test runner as a subprocess and parses output.

The runner is called via its CLI with ``--metrics-json``, which causes
it to emit a JSON block delimited by markers in stdout (same protocol as
the backtest engine and MC runner):

    ###METRICS_JSON_START###{...json...}###METRICS_JSON_END###

Progress updates are emitted as:

    ###MC_PROGRESS###{"completed": N, "total": M}###MC_PROGRESS_END###

This module builds the CLI command, writes a temp config JSON file,
runs the subprocess, and extracts the parsed metrics dict.
"""

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from worker.config import Config
from worker.engine import METRICS_END, METRICS_START, _resolve_python, _sanitize_for_json

logger = logging.getLogger("irt-worker.stress-engine")

# Stress test timeout: 2 hours (many variations to run)
STRESS_TIMEOUT = 7200

# Progress markers (same as MC runner emits)
PROGRESS_START = "###MC_PROGRESS###"
PROGRESS_END = "###MC_PROGRESS_END###"


def run_stress_test(
    job: dict,
    strategies_path: str,
    config: Config,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Run the stress-test runner subprocess and return parsed metrics.

    Parameters
    ----------
    job : dict
        Backtest job dict with ``draft_strat_code``, ``start_date``, ``end_date``,
        ``stress_test_name``, ``stress_param_overrides``, ``stress_single_overrides``,
        ``stress_max_parallel``.
    strategies_path : str
        Path to directory containing the strategy JSON file.
    config : Config
        Worker configuration (hist_data_path).
    progress_callback : callable, optional
        Called with (completed, total) as progress markers are parsed.

    Returns
    -------
    dict
        Parsed metrics/summary dict from stress-test runner output.

    Raises
    ------
    RuntimeError
        On subprocess timeout, non-zero exit, missing markers, or JSON parse error.
    """
    strat_code = job["draft_strat_code"]
    start_date = job.get("start_date", "")
    end_date = job.get("end_date", "")

    # Build stress config JSON
    stress_config = {
        "test_name": job.get("stress_test_name", "unnamed"),
        "start_date": start_date,
        "end_date": end_date,
        "param_overrides": job.get("stress_param_overrides", {}),
        "single_overrides": job.get("stress_single_overrides", {}),
        "max_parallel": job.get("stress_max_parallel", 4),
    }

    # Write config to a temp file
    config_dir = Path(tempfile.gettempdir()) / "irt-backtests"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / f"stress_config_{strat_code}.json"

    try:
        config_file.write_text(
            json.dumps(stress_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        python_exe = _resolve_python()

        # Resolve runner path relative to this file, same pattern as monkey_engine
        runner_path = str(
            Path(__file__).resolve().parent.parent
            / "packages"
            / "stress-test"
            / "runner.py"
        )

        cmd = [
            python_exe,
            runner_path,
            "--strategy", str(strat_code),
            "--config", str(config_file),
            "--hist-data-path", config.hist_data_path,
            "--strategies-path", strategies_path,
            "--metrics-json",
            "--save",
        ]

        logger.info("Running stress test: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=STRESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Stress test timed out after {STRESS_TIMEOUT}s"
            )

        # Parse progress markers from stdout (best-effort, for logging)
        if progress_callback and result.stdout:
            for m in re.finditer(
                re.escape(PROGRESS_START) + r"(.+?)" + re.escape(PROGRESS_END),
                result.stdout,
            ):
                try:
                    progress = json.loads(m.group(1).strip())
                    progress_callback(progress["completed"], progress["total"])
                except (json.JSONDecodeError, KeyError):
                    pass

        # Log stderr for debugging
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-20:]:
                logger.debug("stress stderr: %s", line)

        # Check exit code
        if result.returncode != 0:
            stderr_tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
            raise RuntimeError(
                f"Stress test runner exited with code {result.returncode}: {stderr_tail}"
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
                f"No metrics markers found in stress test stdout. Tail: {stdout_tail}"
            )

        raw_json = match.group(1).strip()
        try:
            metrics = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse stress test metrics JSON: {exc}. Raw: {raw_json[:500]}"
            )

        # Sanitize NaN/Inf values
        metrics = _sanitize_for_json(metrics)

        logger.info(
            "Stress test completed for strat_code=%d — %d keys in metrics",
            strat_code,
            len(metrics) if isinstance(metrics, dict) else 0,
        )
        return metrics

    finally:
        # Clean up the temp config file
        try:
            if config_file.exists():
                config_file.unlink()
                logger.debug("Cleaned up temp config file %s", config_file)
        except OSError:
            logger.warning("Failed to clean up temp config file %s", config_file)
