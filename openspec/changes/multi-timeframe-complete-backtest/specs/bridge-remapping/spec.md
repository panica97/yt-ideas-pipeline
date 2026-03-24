# Bridge Remapping Specification

## Purpose

Defines the behavior of the timeframe remapping logic in the bridge layer. When a user requests a backtest on a timeframe different from the draft's `process_freq`, the bridge MUST transform the draft JSON so all timeframe-dependent fields reference the target timeframe. No engine code is modified -- all remapping is bridge-side.

## Requirements

### Requirement: Suffix Mapping Table

The system MUST define a canonical mapping between human-readable timeframe labels and engine suffixes. The supported timeframes and their suffixes are:

| Label    | Suffix |
|----------|--------|
| 1 min    | 1m     |
| 5 min    | 5m     |
| 15 min   | 15m    |
| 30 min   | 30m    |
| 1 hour   | 1H     |
| 4 hours  | 4H     |
| 8 hours  | 8H     |
| 1 day    | 1D     |

The system MUST reject any timeframe not present in this table.

#### Scenario: Valid timeframe suffix lookup

- GIVEN the suffix mapping table is defined
- WHEN `remap_timeframe()` receives `target_timeframe="5m"`
- THEN it resolves the suffix `5m` and proceeds with remapping

#### Scenario: Invalid timeframe rejected

- GIVEN the suffix mapping table is defined
- WHEN `remap_timeframe()` receives `target_timeframe="2H"`
- THEN it raises a `ValueError` with message containing "Unsupported timeframe: 2H"
- AND the draft JSON is not modified

### Requirement: remap_timeframe() Function Signature

The system MUST provide a function `remap_timeframe(draft_data: dict, target_timeframe: str) -> dict` in `worker/bridge.py`.

The function MUST return a deep copy of the input dict with all timeframe-dependent fields remapped. The original `draft_data` dict MUST NOT be mutated.

#### Scenario: Same timeframe is a no-op

- GIVEN a draft JSON with `process_freq: "1H"`
- WHEN `remap_timeframe(draft_data, "1H")` is called
- THEN the returned dict is a deep copy identical to the input
- AND no fields are modified

#### Scenario: Different timeframe triggers full remapping

- GIVEN a draft JSON with `process_freq: "1H"` and indicators using `_1H` suffixes
- WHEN `remap_timeframe(draft_data, "5m")` is called
- THEN the returned dict has `process_freq: "5m"` and all `_1H` suffixes replaced with `_5m`

### Requirement: process_freq Remapping

The system MUST replace the `process_freq` value in the draft JSON with the target timeframe suffix.

#### Scenario: process_freq updated

- GIVEN a draft JSON with `process_freq: "1H"`
- WHEN remapping to target timeframe `5m`
- THEN the output dict has `process_freq: "5m"`

### Requirement: ind_list Keys Remapping

The system MUST remap all keys in the `ind_list` dictionary. Keys in `ind_list` are formatted as `{indicator_name}_{timeframe_suffix}` (e.g., `EMA_1H`, `RSI_1H`). The system MUST replace the original timeframe suffix with the target suffix.

#### Scenario: ind_list keys remapped

- GIVEN a draft JSON with `ind_list` containing keys `["EMA_1H", "RSI_1H", "ATR_1H"]`
- WHEN remapping from `1H` to `5m`
- THEN the output `ind_list` has keys `["EMA_5m", "RSI_5m", "ATR_5m"]`
- AND the values (indicator parameters) are preserved unchanged

#### Scenario: ind_list with multiple suffixes (only source suffix replaced)

- GIVEN a draft JSON with `process_freq: "1H"` and `ind_list` containing a key `EMA_1D` (different timeframe)
- WHEN remapping from `1H` to `5m`
- THEN only keys ending with `_1H` are remapped to `_5m`
- AND `EMA_1D` remains unchanged

### Requirement: indCode Suffix Remapping

The system MUST remap `indCode` values within each indicator's parameter dictionary inside `ind_list`. The `indCode` field typically contains values like `EMA_1H` and MUST have its timeframe suffix replaced.

#### Scenario: indCode values remapped

- GIVEN an indicator entry with `indCode: "EMA_1H"`
- WHEN remapping from `1H` to `15m`
- THEN the output has `indCode: "EMA_15m"`

### Requirement: cond Strings Remapping

The system MUST remap timeframe suffixes within all `cond` (condition) strings in the draft JSON. Condition strings reference indicators by their suffixed names (e.g., `EMA_1H > RSI_1H`). All occurrences of the source timeframe suffix MUST be replaced with the target suffix.

#### Scenario: Condition string remapped

- GIVEN a condition string `"EMA_1H[0] > EMA_1H[1]"`
- WHEN remapping from `1H` to `5m`
- THEN the output condition is `"EMA_5m[0] > EMA_5m[1]"`

#### Scenario: Condition with mixed timeframes

- GIVEN a condition string `"EMA_1H[0] > EMA_1D[0]"`
- WHEN remapping from `1H` to `5m`
- THEN the output condition is `"EMA_5m[0] > EMA_1D[0]"`
- AND only the source timeframe suffix `_1H` is replaced

### Requirement: max_shift Remapping

The system SHOULD preserve the `max_shift` value as-is during remapping. The `max_shift` represents a number of bars (not a time duration), and bar counts remain valid across timeframes.

#### Scenario: max_shift preserved

- GIVEN a draft JSON with `max_shift: 50`
- WHEN remapping from `1H` to `5m`
- THEN the output has `max_shift: 50` (unchanged)

### Requirement: Schema Validation (Layer 1)

The system MUST validate the remapped JSON structure before passing it to the engine. Layer 1 validation checks structural correctness:

- `process_freq` MUST be a non-empty string matching a known suffix
- `ind_list` MUST be a dict with at least one entry
- Each `ind_list` value MUST be a dict containing an `indCode` key
- `cond_list` MUST exist and be a non-empty structure (list or dict)
- `symbol` MUST be a non-empty string
- `max_shift` MUST be a positive integer

The system MUST raise a `ValueError` with a descriptive message identifying the specific validation failure.

#### Scenario: Valid remapped JSON passes Layer 1

- GIVEN a remapped JSON with all required fields present and correctly typed
- WHEN `validate_remapped_json()` is called
- THEN validation passes (no exception raised)

#### Scenario: Missing process_freq fails Layer 1

- GIVEN a remapped JSON where `process_freq` is missing
- WHEN `validate_remapped_json()` is called
- THEN a `ValueError` is raised with message containing "process_freq"

#### Scenario: Empty ind_list fails Layer 1

- GIVEN a remapped JSON with `ind_list: {}`
- WHEN `validate_remapped_json()` is called
- THEN a `ValueError` is raised with message containing "ind_list"

### Requirement: Consistency Validation (Layer 2)

The system MUST validate cross-field consistency after remapping. Layer 2 checks:

- All `indCode` suffixes within `ind_list` values MUST match the `process_freq` (or be a recognized multi-timeframe suffix from the mapping table)
- All `ind_list` keys' suffixes MUST be consistent with their corresponding `indCode` values
- All indicator references in `cond` strings MUST correspond to keys present in `ind_list`

The system MUST raise a `ValueError` with a descriptive message identifying the inconsistency.

#### Scenario: indCode suffix mismatch detected

- GIVEN a remapped JSON with `process_freq: "5m"` but an `indCode: "EMA_1H"` in `ind_list`
- WHEN `validate_remapped_json()` Layer 2 runs
- THEN a `ValueError` is raised with message identifying the mismatched indicator

#### Scenario: cond references non-existent indicator

- GIVEN a remapped JSON where a `cond` string references `"RSI_5m"` but `ind_list` has no `RSI_5m` key
- WHEN `validate_remapped_json()` Layer 2 runs
- THEN a `ValueError` is raised with message identifying the missing indicator reference

#### Scenario: Consistent remapped JSON passes Layer 2

- GIVEN a remapped JSON where all suffixes match `process_freq` and all cond references exist in `ind_list`
- WHEN `validate_remapped_json()` Layer 2 runs
- THEN validation passes (no exception raised)

### Requirement: Error Propagation

The system MUST propagate all validation errors as `ValueError` exceptions with human-readable messages. The calling code (executor) catches these and reports them as job failures.

The system MUST NOT silently skip invalid fields or produce partially remapped output.

#### Scenario: Validation error becomes job failure

- GIVEN a remapped JSON that fails Layer 2 consistency validation
- WHEN the executor catches the `ValueError`
- THEN the job is marked as failed with the validation error message
- AND no engine subprocess is launched
