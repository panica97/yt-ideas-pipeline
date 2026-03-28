"""Job Executor -- orchestrates draft export, engine run, and result reporting.

This module ties together the bridge (draft export), engine (subprocess run),
and result reporting (HTTP calls back to the IRT API). It handles cleanup
and error reporting so the main poll loop stays clean.

Supports three modes:
- **simple**: Engine runs with --metrics-json only (unchanged).
- **complete**: Bridge remaps timeframe, engine runs with --save --metrics-json,
  worker reads trades.parquet and posts trades alongside metrics.
- **montecarlo**: Bridge remaps timeframe (if needed), MC runner simulates
  N paths and returns summary metrics. No trades parquet produced.
"""

import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

from worker.bridge import export_draft_to_file, remap_timeframe, validate_remapped_json
from worker.config import Config
from worker.engine import run_engine
from worker.mc_engine import run_montecarlo

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


def _read_parquet_trades(parquet_path: str) -> list[dict]:
    """Read trades.parquet and return a simplified list of trade dicts.

    Tries polars first, falls back to pandas. Simplifies to 9 fields:
    entry_date, exit_date, side, entry_fill_price, exit_fill_price,
    pnl, exit_reason, bars_held, cumulative_pnl.
    """
    # Column mapping from parquet names to our simplified names
    # The exact column names depend on the engine output; we try common variants
    COLUMN_MAP = {
        "entry_date": "entry_date",
        "exit_date": "exit_date",
        "direction": "side",
        "side": "side",
        "entry_price": "entry_fill_price",
        "entry_fill_price": "entry_fill_price",
        "exit_price": "exit_fill_price",
        "exit_fill_price": "exit_fill_price",
        "pnl": "pnl",
        "exit_reason": "exit_reason",
        "bars_held": "bars_held",
        "cumulative_pnl": "cumulative_pnl",
    }

    TARGET_FIELDS = {
        "entry_date", "exit_date", "side", "entry_fill_price",
        "exit_fill_price", "pnl", "exit_reason", "bars_held", "cumulative_pnl",
    }

    try:
        import polars as pl

        df = pl.read_parquet(parquet_path)
        if df.is_empty():
            return []

        # Convert to list of dicts
        records = df.to_dicts()
    except ImportError:
        logger.info("polars not available, falling back to pandas for parquet reading")
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        if df.empty:
            return []

        records = df.to_dict(orient="records")

    # Simplify and sanitize records
    simplified: list[dict] = []
    for record in records:
        trade: dict = {}
        for src_col, dest_col in COLUMN_MAP.items():
            if src_col in record:
                trade[dest_col] = record[src_col]

        # Convert datetime objects to ISO 8601 strings
        for dt_field in ("entry_date", "exit_date"):
            val = trade.get(dt_field)
            if val is not None and not isinstance(val, str):
                try:
                    trade[dt_field] = val.isoformat() if hasattr(val, "isoformat") else str(val)
                except Exception:
                    trade[dt_field] = str(val)

        # Sanitize NaN/Inf float values
        for key, val in trade.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                trade[key] = None

        # Ensure bars_held is int if present
        if "bars_held" in trade and trade["bars_held"] is not None:
            try:
                trade["bars_held"] = int(trade["bars_held"])
            except (ValueError, TypeError):
                pass

        simplified.append(trade)

    return simplified


def _save_debug_json(
    data: dict, strat_code: int, timeframe: str
) -> None:
    """Save remapped JSON for debugging.

    Writes to data/backtests/debug/{strat_code}_{timeframe}_{timestamp}.json.
    Never raises -- logs warning on failure.
    """
    try:
        debug_dir = Path("data/backtests/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{strat_code}_{timeframe}_{timestamp}.json"
        filepath = debug_dir / filename

        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Debug JSON saved to %s", filepath)
    except Exception:
        logger.warning("Failed to save debug JSON", exc_info=True)


def execute_backtest_job(job: dict, config: Config) -> None:
    """Execute a single backtest job end-to-end.

    Steps:
    1. Export draft data to a temp JSON file (bridge).
    2. For complete mode: remap timeframe, validate, optionally save debug JSON.
    3. Run the backtest engine as a subprocess (engine).
    4. For complete mode: read trades.parquet via polars/pandas.
    5. Report results (success) or error (failure) back to the API.
    6. Clean up temp files regardless of outcome.

    This function never raises -- all exceptions are caught, logged,
    and reported as job failures so the main poll loop continues.
    """
    job_id = job["id"]
    strat_code = job["draft_strat_code"]
    mode = job.get("mode", "simple")
    is_complete = mode == "complete"
    is_montecarlo = mode == "montecarlo"
    start_time = time.time()

    strategies_path: str | None = None
    parquet_path: str | None = None

    try:
        # 1. Export draft to temp file
        strategies_path = export_draft_to_file(job, config)

        # 2. Timeframe remapping (complete and montecarlo modes)
        if is_complete or is_montecarlo:
            target_tf = job.get("timeframe", "")
            if not target_tf:
                raise ValueError(f"{mode} mode requires a timeframe in the job")

            # Read the exported JSON to get draft data for remapping
            strat_file = Path(strategies_path) / f"{strat_code}.json"
            draft_data = json.loads(strat_file.read_text(encoding="utf-8"))

            # Remap timeframe
            remapped = remap_timeframe(draft_data, target_tf)

            # Validate
            validation_errors = validate_remapped_json(remapped)
            if validation_errors:
                raise ValueError(
                    f"Remapped JSON validation failed: {'; '.join(validation_errors)}"
                )

            # Debug save (job flag or global env var)
            if job.get("debug") or config.worker_debug:
                _save_debug_json(remapped, strat_code, target_tf)

            # Overwrite the temp file with the remapped JSON
            strat_file.write_text(
                json.dumps(remapped, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("Wrote remapped JSON to %s", strat_file)

        # 3. Run engine (backtest or MC)
        if is_montecarlo:
            metrics = run_montecarlo(job, strategies_path, config)
            trades: list[dict] = []  # MC doesn't produce trades
        else:
            metrics = run_engine(
                job, strategies_path, config, save=is_complete
            )

            # 4. Extract trades
            trades = []

            if is_complete:
                # Read trades from parquet file
                parquet_path = metrics.pop("_parquet_path", None) if isinstance(metrics, dict) else None
                if parquet_path and Path(parquet_path).exists():
                    trades = _read_parquet_trades(parquet_path)
                    logger.info("Read %d trades from parquet", len(trades))
                else:
                    logger.warning("trades.parquet not found; returning empty trades list")
            else:
                # Simple mode: extract trades from metrics if present (legacy behavior)
                if isinstance(metrics, dict) and "trades" in metrics:
                    trades = metrics.pop("trades", [])

        # 5. Report success
        _report_success(config, job_id, metrics, trades)

        duration = time.time() - start_time
        logger.info(
            "Job %d completed successfully in %.1fs (strat_code=%d, mode=%s)",
            job_id, duration, strat_code, mode,
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
        # Clean up parquet file if it exists
        if parquet_path:
            try:
                p = Path(parquet_path)
                if p.exists():
                    p.unlink()
                    logger.debug("Cleaned up parquet file %s", parquet_path)
            except OSError:
                logger.warning("Failed to clean up parquet file %s", parquet_path)
