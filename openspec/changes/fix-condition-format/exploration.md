# Exploration: fix-condition-format

## Current State

The strategy-translator skill instructs LLMs to include shift notation `(N)` inside `cond` strings when the same indicator appears on both sides. This contradicts the engine's parser, which expects bare indicator names (used as DataFrame column keys via `cond.split()`).

**Three translator files contain the bad instruction:**

1. **`.claude/skills/strategy-translator/SKILL.md`** (line 58):
   ```
   Same indicator at different shifts: "LOW_6H(1) < LOW_6H(2)", never "LOW_6H < LOW_6H"
   ```

2. **`.claude/skills/strategy-translator/translation-rules.md`** (lines 40-41):
   ```
   "LOW_6H < LOW_6H" → "LOW_6H(0) < LOW_6H(1)"
   ```

3. **`.claude/skills/strategy-translator/schema.json`** (line 197, `cond` field description):
   ```
   "When same indicator appears on both sides with different shifts, include shift in string: LOW_6H(0) < LOW_6H(1)"
   ```

**The authoritative reference (`docs/STRATEGY_FILE_REFERENCE.md`)** does NOT use `(N)` notation anywhere. All examples use bare indicator names:
- `"CLOSE_4h > PMax_20_4h"` (ind_relation, different indicators)
- `"ADX_20_4h < 20"` (num_relation)
- `"RSI_14_4h above 30"` (cross_num_relation)
- `"BBAND_upperband_4h upwards"` (ind_direction)

**Production strategies (1001, 1009, 1015, 1017)** all use bare indicator names in `cond` strings. None contain `(N)`.

**The engine** (external, in ops-worker-v0.1.0) parses `cond` via `cond.split()` to extract column names for DataFrame lookups. Tokens like `"LOW_4h(1)"` don't match any column, causing NaN fill, all-False comparisons, and 0 trades.

### How the ambiguity case works in the engine

When the same indicator appears on both sides (e.g., `"LOW_4h < LOW_4h"`), the engine uses `shift_1` and `shift_2` fields to look up different shifted values from the indicator column. The `cond` string is only for: (a) identifying which columns to read, and (b) which operator to apply. The `cond` string does NOT encode shift information -- that's what `shift_1`/`shift_2` are for.

## Affected Areas

- `.claude/skills/strategy-translator/SKILL.md` -- contains bad `(N)` instruction (line 58)
- `.claude/skills/strategy-translator/translation-rules.md` -- contains bad `(N)` rule (lines 40-41)
- `.claude/skills/strategy-translator/schema.json` -- `cond` field description instructs `(N)` (line 197)
- `frontend/src/components/strategies/draft-sections/ConditionsSection.tsx` -- currently displays `cond` string verbatim; needs to show shifts visually since they won't be in the string anymore
- Any existing drafts in the database with `(N)` in their `cond` strings -- need data migration

**NOT affected:**
- `docs/STRATEGY_FILE_REFERENCE.md` -- already correct, no `(N)` notation
- `frontend/src/types/draft-data.ts` -- `Condition` interface is fine (has `shift_1`, `shift_2` fields)
- Example strategy files (1001, 1009, 1015, 1017) -- already correct
- `worker/engine.py` -- just invokes the external engine, no parsing
- The external engine itself -- it's correct; the bug is in our translator instructions

## Translator Changes Needed

### 1. `.claude/skills/strategy-translator/SKILL.md`

**Line 58** -- Replace:
```
- Same indicator at different shifts: `"LOW_6H(1) < LOW_6H(2)"`, never `"LOW_6H < LOW_6H"`
```
With:
```
- Same indicator at different shifts: `"LOW_6H < LOW_6H"` with `shift_1` and `shift_2` differentiating them. Never put shift notation like `(N)` inside the `cond` string.
```

### 2. `.claude/skills/strategy-translator/translation-rules.md`

**Lines 39-41** -- Replace:
```
- **El campo `cond` debe ser inequivoco cuando se compara el mismo indicador a diferentes shifts.**
  **Origen**: El translator genero `"LOW_6H < LOW_6H"` con shift_1=0, shift_2=1. Parece que compara algo consigo mismo.
  **Ejemplo**: `"LOW_6H < LOW_6H"` → `"LOW_6H(0) < LOW_6H(1)"`
```
With:
```
- **El campo `cond` debe usar nombres de indicador bare (sin notacion de shift).**
  **Origen**: El translator genero `"LOW_6H(0) < LOW_6H(1)"` con shift notation dentro del cond string. Esto rompe el parser del engine que usa cond.split() para buscar columnas en el DataFrame.
  **Ejemplo correcto**: `"LOW_6H < LOW_6H"` con `"shift_1": 1, "shift_2": 2` — los shifts van en campos separados, no en el string.
```

### 3. `.claude/skills/strategy-translator/schema.json`

**Line 197** (`cond` property description) -- Replace:
```json
"description": "Human-readable condition. When same indicator appears on both sides with different shifts, include shift in string: LOW_6H(0) < LOW_6H(1)"
```
With:
```json
"description": "Human-readable condition using bare indicator names. Shifts are encoded in shift_1/shift_2 fields, never in this string. Example: LOW_6H < LOW_6H (with shift_1=1, shift_2=2)"
```

## Frontend Display Logic

The `ConditionBlock` component currently shows `cond` verbatim plus shift badges below. After removing `(N)` from cond strings, the display should build a richer visual representation from `cond` + `shift_1` + `shift_2`.

**For each condition type, the display format:**

| cond_type | Current display | Proposed display |
|-----------|----------------|-----------------|
| `num_relation` | `ADX_20_4h < 20` | `ADX_20_4h < 20` (no change -- shift_2 irrelevant) |
| `ind_relation` (different indicators) | `CLOSE_4h > PMax_20_4h` | `CLOSE_4h > PMax_20_4h` (no change -- already unambiguous) |
| `ind_relation` (same indicator) | `LOW_4h < LOW_4h` | `LOW_4h(1) < LOW_4h(2)` (rendered with shifts for clarity) |
| `price_relation` | `EMA_20_4h > close_4h` | `EMA_20_4h > close_4h` (shifts shown in badges) |
| `p2p_relation` | `close_4h > high_1D` | `close_4h > high_1D` (shifts shown in badges) |
| `cross_num_relation` | `RSI_14_4h above 30` | `RSI_14_4h above 30` (no change) |
| `cross_ind_relation` | `macd_1D above macdsignal_1D` | `macd_1D above macdsignal_1D` (no change) |
| `cross_price_relation` | `EMA_20_4h above close_1D` | `EMA_20_4h above close_1D` (no change) |
| `ind_direction` | `RSI_MED_14_1D downwards` | `RSI_MED_14_1D downwards` (no change) |
| `num_bars` | `Exit after 12 bars` | `Exit after 12 bars` (no change) |

**Key insight:** The frontend should detect when the same indicator name appears on both sides of the operator and append `(shift_1)` / `(shift_2)` to the display string for visual disambiguation. This is a display-only concern -- the stored `cond` must remain bare.

**Implementation approach for `ConditionBlock`:**

```typescript
function formatCondDisplay(cond: Condition): string {
  if (cond.cond_type === 'num_bars') return `Exit after ${cond.cond} bars`;

  // For relation types, check if same indicator on both sides
  const parts = cond.cond.split(/\s+/);
  if (parts.length === 3) {
    const [left, op, right] = parts;
    if (left === right && cond.shift_1 != null && cond.shift_2 != null) {
      return `${left}(${cond.shift_1}) ${op} ${right}(${cond.shift_2})`;
    }
  }

  return cond.cond;
}
```

This keeps shift badges as-is (they still provide value for all condition types) while making same-indicator comparisons readable in the main display.

## Example Transformations

### ind_relation (same indicator, different shifts)
**Before (translator output):**
```json
{
  "cond_type": "ind_relation",
  "cond": "LOW_4h(1) < LOW_4h(2)",
  "shift_1": 1,
  "shift_2": 2,
  "condCode": "long_1"
}
```
**After (corrected):**
```json
{
  "cond_type": "ind_relation",
  "cond": "LOW_4h < LOW_4h",
  "shift_1": 1,
  "shift_2": 2,
  "condCode": "long_1"
}
```
**Frontend renders:** `LOW_4h(1) < LOW_4h(2)` (shifts appended visually)

### ind_relation (different indicators)
**Before:** `"CLOSE_4h > PMax_20_4h"` -- already correct, no change needed.

### num_relation
**Before:** `"ADX_20_4h < 20"` -- already correct, no `(N)` applies.

### cross_ind_relation
**Before:** `"macd_1D above macdsignal_1D"` -- already correct. Even if same indicator were used on both sides of a cross, the `cond` stays bare.

### price_relation
**Before:** `"EMA_20_4h > close_4h"` -- already correct. Price tokens are not indicators.

### ind_direction
**Before:** `"RSI_MED_14_1D downwards"` -- single operand, no ambiguity possible.

### num_bars
**Before:** `"12"` -- no indicators involved.

## Risks

1. **Existing drafts in DB** -- Any drafts already created by the translator with `(N)` in their `cond` strings will fail backtesting until migrated. Task 3 (data migration) addresses this, but the scope of affected drafts is unknown without a DB query.

2. **Same-indicator ambiguity in `cond` string** -- With bare names, `"LOW_4h < LOW_4h"` looks like it compares something to itself. This is only a human readability issue (the engine handles it correctly via shift fields), but could confuse users reviewing strategies. The frontend display fix (task 2) mitigates this.

3. **Future translator runs** -- After fixing the translator instructions, new drafts will be correct. But if the translator skill files are cached or an older version is used, wrong cond strings could reappear. Low risk since skills are read fresh each invocation.

4. **Cross-type conditions with same indicator** -- Edge case: `cross_ind_relation` with the same indicator on both sides (e.g., `"EMA_20_4h above EMA_20_4h"`). Same fix applies -- bare names, shifts in fields. The frontend display logic handles this via the same-name detection.

5. **No regression risk to engine** -- The engine is external and unchanged. We're only fixing the data we feed it to match its expected format.

## Ready for Proposal

Yes. All three tasks are well-scoped quick fixes:
1. **Translator fix** -- 3 files, specific lines identified, straightforward text changes
2. **Frontend display fix** -- 1 component, ~10 lines of logic in `ConditionBlock`
3. **DB migration** -- strip `(N)` regex from JSONB cond strings (scope TBD by DB query)
