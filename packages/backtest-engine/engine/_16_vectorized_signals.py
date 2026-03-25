"""
Vectorized Entry Signal Compiler (Phase 3)

Pre-computes entry condition boolean masks over the full time series,
enabling the bar loop to skip flat bars (no position + no entry signal).

Each condition type is evaluated as a vectorized numpy operation instead
of per-bar scalar extraction + comparison. NaN comparisons naturally
return False, matching the per-bar _safe_scalar → None → result=False behavior.
"""

import numpy as np
from typing import Dict, Tuple, Optional, List

import polars as pl


# Vectorized comparison operators (mirror strategies.py _OPERATORS)
_VEC_OPS = {
    '>': np.greater,
    '<': np.less,
    '>=': np.greater_equal,
    '<=': np.less_equal,
    '==': np.equal,
    '!=': np.not_equal,
}


def _shift_array(arr: np.ndarray, shift: int) -> np.ndarray:
    """Shift array right by `shift` positions, filling leading values with NaN.

    shift=0 → no change
    shift=1 → [nan, a0, a1, ..., a_{n-2}]
    shift=2 → [nan, nan, a0, ..., a_{n-3}]
    """
    if shift <= 0:
        return arr
    result = np.empty_like(arr, dtype=np.float64)
    result[:shift] = np.nan
    result[shift:] = arr[:-shift]
    return result


def _get_aligned_values(
    col_name: str,
    col_tf: Optional[str],
    shift: int,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Get column values aligned to primary bar indices with shift applied.

    For primary TF columns: direct shift.
    For secondary TF columns: gather via tf_index_map, then shift.

    Returns float64 numpy array of length total_bars with NaN for invalid positions.
    """
    if col_tf is None or col_tf == primary_tf:
        # Primary TF: direct access
        df = precomputed_data[primary_tf]
        if col_name not in df.columns:
            return np.full(total_bars, np.nan)
        raw = df[col_name].cast(pl.Float64).to_numpy()
        # Replace Polars nulls (which become NaN in float cast)
        return _shift_array(raw, shift)

    # Secondary TF: align via index map
    if col_tf not in precomputed_data or col_tf not in tf_index_map:
        return np.full(total_bars, np.nan)

    sec_df = precomputed_data[col_tf]
    if col_name not in sec_df.columns:
        return np.full(total_bars, np.nan)

    sec_values = sec_df[col_name].cast(pl.Float64).to_numpy()
    sec_counts = tf_index_map[col_tf]  # row count per primary bar

    # Row index in secondary TF for each primary bar (before shift)
    sec_indices = sec_counts.astype(np.int64) - 1  # last available row

    # Apply shift (reading further back in the secondary TF window)
    sec_indices = sec_indices - shift

    # Gather with bounds checking
    result = np.full(total_bars, np.nan)
    valid = (sec_indices >= 0) & (sec_indices < len(sec_values))
    result[valid] = sec_values[sec_indices[valid]]
    return result


def _find_column_tf(
    col_name: str,
    precomputed_data: Dict[str, pl.DataFrame],
) -> Optional[str]:
    """Find which timeframe contains the given column (first match)."""
    for tf, df in precomputed_data.items():
        if col_name in df.columns:
            return tf
    return None


def _resolve_price_tf(price_token: str) -> Tuple[str, str]:
    """Parse price token like 'close_1d' into (price_type, timeframe).

    Returns (column_name, timeframe_key).
    The timeframe_key is the raw suffix (e.g., '1d', '1h', '30m').
    Caller must map this to actual TF keys in precomputed_data.
    """
    parts = price_token.split("_")
    price_type = parts[0]  # 'open', 'high', 'low', 'close'
    price_tf = parts[-1]   # '1d', '1h', etc.
    return price_type, price_tf


def _match_tf_key(short_tf: str, precomputed_data: Dict[str, pl.DataFrame]) -> Optional[str]:
    """Match a short TF identifier (e.g., '1d') to actual precomputed_data key (e.g., '1 day').

    Strategy conditions use short codes like '1d', '1h', '30m'.
    precomputed_data keys are full names like '1 day', '1 hour', '30 mins'.
    """
    # Direct match first
    if short_tf in precomputed_data:
        return short_tf

    # Common mappings
    _TF_MAP = {
        '1d': '1 day', '1day': '1 day', 'day': '1 day',
        '1h': '1 hour', '1hour': '1 hour', 'hour': '1 hour',
        '4h': '4 hours', '4hours': '4 hours',
        '2h': '2 hours', '2hours': '2 hours',
        '30m': '30 mins', '30min': '30 mins', '30mins': '30 mins',
        '15m': '15 mins', '15min': '15 mins', '15mins': '15 mins',
        '5m': '5 mins', '5min': '5 mins', '5mins': '5 mins',
        '1m': '1 min', '1min': '1 min',
        '1w': '1 week', '1week': '1 week', 'week': '1 week',
    }

    mapped = _TF_MAP.get(short_tf.lower())
    if mapped and mapped in precomputed_data:
        return mapped

    # Fuzzy: check if short_tf appears as substring in any key
    for key in precomputed_data:
        if short_tf.lower() in key.lower():
            return key

    return None


# --- Condition vectorizers ---

def _vec_num_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND op NUM (e.g., 'RSI_14 > 70')."""
    ind_1, operator, threshold = cond_dict['cond'].split()
    shift = int(cond_dict.get('shift_1', 0) or 0)
    thresh_val = float(threshold)

    col_tf = _find_column_tf(ind_1, precomputed_data)
    values = _get_aligned_values(ind_1, col_tf, shift, precomputed_data, tf_index_map, primary_tf, total_bars)

    vec_op = _VEC_OPS.get(operator)
    if vec_op is None:
        return np.zeros(total_bars, dtype=bool)

    with np.errstate(invalid='ignore'):
        return vec_op(values, thresh_val)


def _vec_ind_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND1 op IND2 (e.g., 'SMA_20 > SMA_50')."""
    ind_1, operator, ind_2 = cond_dict['cond'].split()
    shift_1 = int(cond_dict.get('shift_1', 0) or 0)
    shift_2 = int(cond_dict.get('shift_2', 0) or 0)

    tf_1 = _find_column_tf(ind_1, precomputed_data)
    tf_2 = _find_column_tf(ind_2, precomputed_data)
    vals_1 = _get_aligned_values(ind_1, tf_1, shift_1, precomputed_data, tf_index_map, primary_tf, total_bars)
    vals_2 = _get_aligned_values(ind_2, tf_2, shift_2, precomputed_data, tf_index_map, primary_tf, total_bars)

    vec_op = _VEC_OPS.get(operator)
    if vec_op is None:
        return np.zeros(total_bars, dtype=bool)

    with np.errstate(invalid='ignore'):
        return vec_op(vals_1, vals_2)


def _vec_price_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND op PRICE_TF (e.g., 'RSI_14 > close_1d')."""
    ind_1, operator, price_token = cond_dict['cond'].split()
    shift_1 = int(cond_dict.get('shift_1', 0) or 0)
    shift_2 = int(cond_dict.get('shift_2', 0) or 0)

    price_type, price_tf_short = _resolve_price_tf(price_token)
    price_tf = _match_tf_key(price_tf_short, precomputed_data)

    ind_tf = _find_column_tf(ind_1, precomputed_data)
    vals_ind = _get_aligned_values(ind_1, ind_tf, shift_1, precomputed_data, tf_index_map, primary_tf, total_bars)
    vals_price = _get_aligned_values(price_type, price_tf, shift_2, precomputed_data, tf_index_map, primary_tf, total_bars)

    vec_op = _VEC_OPS.get(operator)
    if vec_op is None:
        return np.zeros(total_bars, dtype=bool)

    with np.errstate(invalid='ignore'):
        return vec_op(vals_ind, vals_price)


def _vec_p2p_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: PRICE1_TF1 op PRICE2_TF2 (e.g., 'open_1d > close_1h')."""
    price_1, operator, price_2 = cond_dict['cond'].split()
    shift_1 = int(cond_dict.get('shift_1', 0) or 0)
    shift_2 = int(cond_dict.get('shift_2', 0) or 0)

    p1_type, p1_tf_short = _resolve_price_tf(price_1)
    p2_type, p2_tf_short = _resolve_price_tf(price_2)
    p1_tf = _match_tf_key(p1_tf_short, precomputed_data)
    p2_tf = _match_tf_key(p2_tf_short, precomputed_data)

    vals_1 = _get_aligned_values(p1_type, p1_tf, shift_1, precomputed_data, tf_index_map, primary_tf, total_bars)
    vals_2 = _get_aligned_values(p2_type, p2_tf, shift_2, precomputed_data, tf_index_map, primary_tf, total_bars)

    vec_op = _VEC_OPS.get(operator)
    if vec_op is None:
        return np.zeros(total_bars, dtype=bool)

    with np.errstate(invalid='ignore'):
        return vec_op(vals_1, vals_2)


def _vec_cross_ind_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND1 above/bellow IND2 (crossover detection)."""
    ind_1, operator, ind_2 = cond_dict['cond'].split()
    shift_1 = int(cond_dict.get('shift_1', 0) or 0)
    shift_2 = int(cond_dict.get('shift_2', 0) or 0)

    tf_1 = _find_column_tf(ind_1, precomputed_data)
    tf_2 = _find_column_tf(ind_2, precomputed_data)

    # Current values
    ind1_curr = _get_aligned_values(ind_1, tf_1, shift_1, precomputed_data, tf_index_map, primary_tf, total_bars)
    ind2_curr = _get_aligned_values(ind_2, tf_2, shift_2, precomputed_data, tf_index_map, primary_tf, total_bars)
    # Past values (one bar further back)
    ind1_past = _get_aligned_values(ind_1, tf_1, shift_1 + 1, precomputed_data, tf_index_map, primary_tf, total_bars)
    ind2_past = _get_aligned_values(ind_2, tf_2, shift_2 + 1, precomputed_data, tf_index_map, primary_tf, total_bars)

    with np.errstate(invalid='ignore'):
        if operator == 'above':
            # Cross above: was NOT above, now IS above
            return (~(ind1_past > ind2_past)) & (ind1_curr > ind2_curr)
        elif operator == 'bellow':
            # Cross below: was NOT below, now IS below
            return (~(ind1_past < ind2_past)) & (ind1_curr < ind2_curr)

    return np.zeros(total_bars, dtype=bool)


def _vec_cross_num_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND above/bellow NUM (e.g., 'RSI_14 above 70')."""
    ind_1, operator, threshold = cond_dict['cond'].split()
    shift = int(cond_dict.get('shift_1', 0) or 0)
    thresh_val = float(threshold)

    col_tf = _find_column_tf(ind_1, precomputed_data)
    ind_curr = _get_aligned_values(ind_1, col_tf, shift, precomputed_data, tf_index_map, primary_tf, total_bars)
    ind_past = _get_aligned_values(ind_1, col_tf, shift + 1, precomputed_data, tf_index_map, primary_tf, total_bars)

    with np.errstate(invalid='ignore'):
        if operator == 'above':
            return (~(ind_past > thresh_val)) & (ind_curr > thresh_val)
        elif operator == 'bellow':
            return (~(ind_past < thresh_val)) & (ind_curr < thresh_val)

    return np.zeros(total_bars, dtype=bool)


def _vec_cross_price_relation(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND above/bellow PRICE_TF (e.g., 'SMA_20 above close_1d')."""
    ind_1, operator, price_token = cond_dict['cond'].split()
    shift_1 = int(cond_dict.get('shift_1', 0) or 0)
    shift_2 = int(cond_dict.get('shift_2', 0) or 0)

    price_type, price_tf_short = _resolve_price_tf(price_token)
    price_tf = _match_tf_key(price_tf_short, precomputed_data)
    ind_tf = _find_column_tf(ind_1, precomputed_data)

    ind_curr = _get_aligned_values(ind_1, ind_tf, shift_1, precomputed_data, tf_index_map, primary_tf, total_bars)
    ind_past = _get_aligned_values(ind_1, ind_tf, shift_1 + 1, precomputed_data, tf_index_map, primary_tf, total_bars)
    price_curr = _get_aligned_values(price_type, price_tf, shift_2, precomputed_data, tf_index_map, primary_tf, total_bars)
    price_past = _get_aligned_values(price_type, price_tf, shift_2 + 1, precomputed_data, tf_index_map, primary_tf, total_bars)

    with np.errstate(invalid='ignore'):
        if operator == 'above':
            return (~(ind_past > price_past)) & (ind_curr > price_curr)
        elif operator == 'bellow':
            return (~(ind_past < price_past)) & (ind_curr < price_curr)

    return np.zeros(total_bars, dtype=bool)


def _vec_ind_direction(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> np.ndarray:
    """Vectorize: IND upwards/downwards (momentum reversal detection)."""
    ind_1, operator = cond_dict['cond'].split()
    shift = int(cond_dict.get('shift_1', 0) or 0)

    col_tf = _find_column_tf(ind_1, precomputed_data)
    # Three consecutive values: t-2, t-1, t (relative to shift)
    val_curr = _get_aligned_values(ind_1, col_tf, shift, precomputed_data, tf_index_map, primary_tf, total_bars)
    val_past = _get_aligned_values(ind_1, col_tf, shift + 1, precomputed_data, tf_index_map, primary_tf, total_bars)
    val_prev = _get_aligned_values(ind_1, col_tf, shift + 2, precomputed_data, tf_index_map, primary_tf, total_bars)

    with np.errstate(invalid='ignore'):
        if operator == 'upwards':
            # Was going down (prev > past), now going up (past < curr)
            return (val_prev > val_past) & (val_past < val_curr)
        elif operator == 'downwards':
            # Was going up (prev < past), now going down (past > curr)
            return (val_prev < val_past) & (val_past > val_curr)

    return np.zeros(total_bars, dtype=bool)


# Dispatcher mapping condition types to vectorizers
_VECTORIZERS = {
    'num_relation': _vec_num_relation,
    'ind_relation': _vec_ind_relation,
    'price_relation': _vec_price_relation,
    'p2p_relation': _vec_p2p_relation,
    'cross_ind_relation': _vec_cross_ind_relation,
    'cross_num_relation': _vec_cross_num_relation,
    'cross_price_relation': _vec_cross_price_relation,
    'ind_direction': _vec_ind_direction,
}


def _vectorize_condition(
    cond_dict: dict,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> Optional[np.ndarray]:
    """Vectorize a single condition. Returns boolean array or None if unsupported."""
    cond_type = cond_dict.get('cond_type', '')
    vectorizer = _VECTORIZERS.get(cond_type)
    if vectorizer is None:
        return None
    try:
        return vectorizer(cond_dict, precomputed_data, tf_index_map, primary_tf, total_bars)
    except Exception:
        # If vectorization fails for any reason, return None (caller falls back)
        return None


def compile_entry_signals(
    stratOBJ,
    strategy: int,
    precomputed_data: Dict[str, pl.DataFrame],
    tf_index_map: Dict[str, np.ndarray],
    primary_tf: str,
    total_bars: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compile vectorized entry signal masks for long and short conditions.

    Returns:
        (long_mask, short_mask): boolean numpy arrays of length total_bars.
        long_mask[i] = True if all long entry conditions fire at bar i.
        short_mask[i] = True if all short entry conditions fire at bar i.

    If any condition cannot be vectorized, the corresponding mask is all-True
    (conservative: forces per-bar evaluation for those bars via the fallback path).
    """
    long_conds = stratOBJ.long_conds(strategy) or []
    short_conds = stratOBJ.short_conds(strategy) or []

    def _compile_mask(conds_list: List[dict]) -> Tuple[np.ndarray, bool]:
        """AND all conditions into a single mask.

        Returns (mask, is_complete) where is_complete=False if any condition
        couldn't be vectorized (mask is unreliable as a standalone signal).
        """
        if not conds_list:
            return np.zeros(total_bars, dtype=bool), True

        combined = np.ones(total_bars, dtype=bool)
        all_compiled = True

        for cond in conds_list:
            cond_mask = _vectorize_condition(
                cond, precomputed_data, tf_index_map, primary_tf, total_bars
            )
            if cond_mask is None:
                # Can't vectorize this condition — mark mask as incomplete
                all_compiled = False
                # Don't AND a None mask (would incorrectly filter)
                continue
            combined &= cond_mask

        return combined, all_compiled

    long_mask, long_complete = _compile_mask(long_conds)
    short_mask, short_complete = _compile_mask(short_conds)

    return long_mask, short_mask, long_complete, short_complete
