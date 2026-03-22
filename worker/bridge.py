"""Draft Export Bridge -- fetches draft data from IRT API and writes to temp file.

The backtest engine expects strategy definitions as JSON files in a directory,
loadable by ibkr-core's StratOBJ loader. This module bridges the IRT draft
(stored as JSONB in PostgreSQL) to a temporary file the engine can consume.
"""

import json
import logging
import tempfile
from pathlib import Path

from worker.config import Config

logger = logging.getLogger("irt-worker.bridge")


def export_draft_to_file(job: dict, config: Config) -> str:
    """Fetch draft data from the IRT API and write it to a temp JSON file.

    Parameters
    ----------
    job : dict
        The backtest job dict (must contain ``draft_strat_code``).
    config : Config
        Worker configuration (provides ``api_url`` and authenticated ``session``).

    Returns
    -------
    str
        Path to the temp directory containing the strategy JSON file.
        This is the value to pass as ``--strategies-path`` to the engine.

    Raises
    ------
    RuntimeError
        If the draft cannot be fetched or has no data field.
    """
    strat_code = job["draft_strat_code"]
    url = f"{config.api_url}/api/strategies/drafts/{strat_code}"

    logger.info("Fetching draft data for strat_code=%d", strat_code)
    resp = config.session.get(url, timeout=15)

    if resp.status_code == 404:
        raise RuntimeError(f"Draft with strat_code={strat_code} not found (deleted?)")
    resp.raise_for_status()

    draft = resp.json()
    data = draft.get("data")
    if not data:
        raise RuntimeError(f"Draft strat_code={strat_code} has no data field")

    # Ensure symbol has @ prefix (engine looks for @MNQ_1M_edit.txt, not MNQ_1M_edit.txt)
    symbol = data.get("symbol", "")
    if symbol and not symbol.startswith("@"):
        data["symbol"] = f"@{symbol}"
        logger.info("Prepended @ to symbol: %s -> %s", symbol, data["symbol"])

    # Write to a temp directory: {tmp}/irt-backtests/{strat_code}.json
    tmp_dir = Path(tempfile.gettempdir()) / "irt-backtests"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    strat_file = tmp_dir / f"{strat_code}.json"
    strat_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    logger.info("Exported draft to %s", strat_file)
    return str(tmp_dir)
