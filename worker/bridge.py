"""Draft Export Bridge -- fetches draft data from IRT API and writes to temp file.

The backtest engine expects strategy definitions as JSON files in a directory,
loadable by ibkr-core's StratOBJ loader. This module bridges the IRT draft
(stored as JSONB in PostgreSQL) to a temporary file the engine can consume.

Also provides timeframe remapping and validation for multi-timeframe backtests.
"""

import copy
import json
import logging
import re
import tempfile
from pathlib import Path

from worker.config import Config

logger = logging.getLogger("irt-worker.bridge")

# Canonical mapping: human-readable timeframe label -> engine indCode suffix
TIMEFRAME_SUFFIX: dict[str, str] = {
    "1 min": "1m",
    "5 min": "5m",
    "15 min": "15m",
    "30 min": "30m",
    "1 hour": "1H",
    "4 hours": "4H",
    "8 hours": "8H",
    "1 day": "1D",
}

# Reverse mapping: suffix -> label (for validation lookups)
_SUFFIX_TO_LABEL: dict[str, str] = {v: k for k, v in TIMEFRAME_SUFFIX.items()}

# All valid suffixes (for validation)
_VALID_SUFFIXES: set[str] = set(TIMEFRAME_SUFFIX.values())


def _resolve_suffix(timeframe: str) -> str:
    """Resolve a timeframe string to its engine suffix.

    Accepts either a label ("5 min") or a raw suffix ("5m").
    Raises ValueError if not recognized.
    """
    if timeframe in TIMEFRAME_SUFFIX:
        return TIMEFRAME_SUFFIX[timeframe]
    if timeframe in _SUFFIX_TO_LABEL:
        return timeframe  # already a suffix
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _resolve_label(timeframe: str) -> str:
    """Resolve a timeframe string to its human-readable label.

    Accepts either a label ("5 min") or a raw suffix ("5m").
    Raises ValueError if not recognized.
    """
    if timeframe in TIMEFRAME_SUFFIX:
        return timeframe
    if timeframe in _SUFFIX_TO_LABEL:
        return _SUFFIX_TO_LABEL[timeframe]
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def remap_timeframe(data: dict, target_tf: str) -> dict:
    """Remap a strategy JSON from its current process_freq to target_tf.

    Parameters
    ----------
    data : dict
        The draft JSON data (will NOT be mutated).
    target_tf : str
        Target timeframe key (e.g. "5 min", "5m", "1 hour", "1H").

    Returns
    -------
    dict
        Remapped strategy JSON (deep copy).

    Raises
    ------
    ValueError
        If source or target timeframe is not in TIMEFRAME_SUFFIX.
    """
    result = copy.deepcopy(data)

    source_tf_raw = result.get("process_freq", "")
    source_suffix = _resolve_suffix(source_tf_raw)
    target_suffix = _resolve_suffix(target_tf)

    source_label = _resolve_label(source_tf_raw)
    target_label = _resolve_label(target_tf)

    # No-op if same timeframe
    if source_suffix == target_suffix:
        return result

    old_sfx = f"_{source_suffix}"
    new_sfx = f"_{target_suffix}"

    # 1. Remap process_freq
    result["process_freq"] = target_suffix

    # 2. Remap ind_list keys and indCode values
    ind_list = result.get("ind_list", {})
    new_ind_list: dict = {}
    for key, indicators in ind_list.items():
        # Remap the key if it matches source label or has source suffix
        if key == source_label:
            new_key = target_label
        elif key.endswith(old_sfx):
            new_key = key[: -len(old_sfx)] + new_sfx
        else:
            new_key = key

        # Remap indCode in each indicator
        if isinstance(indicators, list):
            new_indicators = []
            for ind in indicators:
                ind_copy = dict(ind)
                if "indCode" in ind_copy and isinstance(ind_copy["indCode"], str):
                    if ind_copy["indCode"].endswith(old_sfx):
                        ind_copy["indCode"] = ind_copy["indCode"][: -len(old_sfx)] + new_sfx
                # Also check nested params.indCode
                params = ind_copy.get("params", {})
                if isinstance(params, dict) and "indCode" in params:
                    if isinstance(params["indCode"], str) and params["indCode"].endswith(old_sfx):
                        params["indCode"] = params["indCode"][: -len(old_sfx)] + new_sfx
                new_indicators.append(ind_copy)
            new_ind_list[new_key] = new_indicators
        elif isinstance(indicators, dict):
            ind_copy = dict(indicators)
            if "indCode" in ind_copy and isinstance(ind_copy["indCode"], str):
                if ind_copy["indCode"].endswith(old_sfx):
                    ind_copy["indCode"] = ind_copy["indCode"][: -len(old_sfx)] + new_sfx
            new_ind_list[new_key] = ind_copy
        else:
            new_ind_list[new_key] = indicators

    result["ind_list"] = new_ind_list

    # 3. Remap cond strings in long_conds, short_conds, exit_conds
    for cond_key in ("long_conds", "short_conds", "exit_conds"):
        conds = result.get(cond_key, [])
        if isinstance(conds, list):
            for cond_entry in conds:
                if isinstance(cond_entry, dict) and "cond" in cond_entry:
                    cond_entry["cond"] = cond_entry["cond"].replace(old_sfx, new_sfx)

    # 4. Remap max_shift if it's a list with timeframe label
    max_shift = result.get("max_shift")
    if isinstance(max_shift, list) and len(max_shift) >= 2:
        if max_shift[1] == source_label:
            max_shift[1] = target_label

    # 5. Remap stop_loss_init / take_profit_init indicator_params
    for sl_tp_key in ("stop_loss_init", "take_profit_init"):
        sl_tp = result.get(sl_tp_key)
        if isinstance(sl_tp, dict):
            ip = sl_tp.get("indicator_params")
            if isinstance(ip, dict):
                # tf field
                if ip.get("tf") == source_label:
                    ip["tf"] = target_label
                elif ip.get("tf") == source_suffix:
                    ip["tf"] = target_suffix
                # col field (suffix replacement)
                col = ip.get("col", "")
                if isinstance(col, str) and col.endswith(old_sfx):
                    ip["col"] = col[: -len(old_sfx)] + new_sfx
                # Also handle col values like "ATR_20_1D_SL" where suffix is not at end
                elif isinstance(col, str) and old_sfx in col:
                    ip["col"] = col.replace(old_sfx, new_sfx)

    # 6. Remap control_params.primary_timeframe
    cp = result.get("control_params")
    if isinstance(cp, dict):
        pt = cp.get("primary_timeframe", "")
        if pt == source_label:
            cp["primary_timeframe"] = target_label
        elif pt == source_suffix:
            cp["primary_timeframe"] = target_suffix

    logger.info(
        "Remapped timeframe: %s (%s) -> %s (%s)",
        source_label, source_suffix, target_label, target_suffix,
    )
    return result


def validate_remapped_json(data: dict) -> list[str]:
    """Validate a remapped strategy JSON for correctness.

    Returns
    -------
    list[str]
        List of error messages. Empty list means valid.
    """
    errors: list[str] = []
    process_freq = data.get("process_freq")

    # --- Layer 1: Schema validation ---

    # process_freq must be a non-empty string matching a known suffix
    if not process_freq or not isinstance(process_freq, str):
        errors.append("process_freq is missing or empty")
    elif process_freq not in _VALID_SUFFIXES:
        errors.append(f"process_freq '{process_freq}' is not a recognized suffix")

    # ind_list must be a non-empty dict
    ind_list = data.get("ind_list")
    if not isinstance(ind_list, dict) or len(ind_list) == 0:
        errors.append("ind_list is missing or empty")

    # Each ind_list entry must have indCode
    if isinstance(ind_list, dict):
        for key, indicators in ind_list.items():
            if isinstance(indicators, list):
                for i, ind in enumerate(indicators):
                    if not isinstance(ind, dict):
                        errors.append(f"ind_list['{key}'][{i}] is not a dict")
                        continue
                    ind_code = ind.get("indCode") or (ind.get("params", {}) or {}).get("indCode")
                    if not ind_code:
                        errors.append(f"ind_list['{key}'][{i}] has no indCode")
            elif isinstance(indicators, dict):
                ind_code = indicators.get("indCode") or (indicators.get("params", {}) or {}).get("indCode")
                if not ind_code:
                    errors.append(f"ind_list['{key}'] has no indCode")

    # max_shift must be a positive integer (or list with positive int)
    max_shift = data.get("max_shift")
    if isinstance(max_shift, int):
        if max_shift <= 0:
            errors.append(f"max_shift must be positive, got {max_shift}")
    elif isinstance(max_shift, list) and len(max_shift) >= 1:
        if not isinstance(max_shift[0], int) or max_shift[0] <= 0:
            errors.append(f"max_shift[0] must be a positive integer, got {max_shift[0]}")

    # If Layer 1 has errors, return early (Layer 2 depends on valid structure)
    if errors:
        return errors

    # --- Layer 2: Consistency validation ---

    expected_suffix = f"_{process_freq}"

    # Collect all ind_list keys for reference checking
    all_ind_keys: set[str] = set()
    if isinstance(ind_list, dict):
        for key, indicators in ind_list.items():
            if isinstance(indicators, list):
                for ind in indicators:
                    if isinstance(ind, dict):
                        ind_code = ind.get("indCode") or (ind.get("params", {}) or {}).get("indCode", "")
                        if ind_code:
                            all_ind_keys.add(ind_code)
            elif isinstance(indicators, dict):
                ind_code = indicators.get("indCode") or (indicators.get("params", {}) or {}).get("indCode", "")
                if ind_code:
                    all_ind_keys.add(ind_code)

    # Check all indCode values end with expected suffix
    if isinstance(ind_list, dict):
        for key, indicators in ind_list.items():
            ind_entries = indicators if isinstance(indicators, list) else [indicators]
            for ind in ind_entries:
                if not isinstance(ind, dict):
                    continue
                ind_code = ind.get("indCode") or (ind.get("params", {}) or {}).get("indCode", "")
                if ind_code and not ind_code.endswith(expected_suffix):
                    # Check if it's a multi-timeframe suffix (valid but different)
                    has_valid_suffix = any(ind_code.endswith(f"_{s}") for s in _VALID_SUFFIXES)
                    if has_valid_suffix:
                        errors.append(
                            f"indCode '{ind_code}' has suffix that doesn't match "
                            f"process_freq '{process_freq}'"
                        )
                    else:
                        errors.append(
                            f"indCode '{ind_code}' doesn't end with expected suffix '{expected_suffix}'"
                        )

    # Check cond references resolve to known indCodes
    for cond_key in ("long_conds", "short_conds", "exit_conds"):
        conds = data.get(cond_key, [])
        if isinstance(conds, list):
            for cond_entry in conds:
                if isinstance(cond_entry, dict) and "cond" in cond_entry:
                    cond_str = cond_entry["cond"]
                    # Extract indicator references (word characters before [)
                    refs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\[", cond_str)
                    for ref in refs:
                        if ref not in all_ind_keys:
                            errors.append(
                                f"Condition in {cond_key} references '{ref}' "
                                f"which is not in ind_list"
                            )

    # Check stop_loss/take_profit tf matches process_freq
    for sl_tp_key in ("stop_loss_init", "take_profit_init"):
        sl_tp = data.get(sl_tp_key)
        if isinstance(sl_tp, dict):
            ip = sl_tp.get("indicator_params")
            if isinstance(ip, dict):
                tf = ip.get("tf", "")
                if tf:
                    resolved = None
                    try:
                        resolved = _resolve_suffix(tf)
                    except ValueError:
                        pass
                    if resolved and resolved != process_freq:
                        errors.append(
                            f"{sl_tp_key}.indicator_params.tf is '{tf}' "
                            f"but process_freq is '{process_freq}'"
                        )

    return errors


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
