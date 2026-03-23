# Design: Fix Backtest Condition Format

## Technical Approach

Two independent tasks that ship together:

1. **Translator skill fix** -- Remove `(N)` shift notation instructions from 3 skill files so newly translated strategies produce bare indicator names in `cond` strings.
2. **Frontend display fix** -- Add a `formatCondDisplay` function to `ConditionBlock` that renders shift notation visually for disambiguation, without modifying the stored data.

Both tasks are text-level edits with no architectural changes, no new dependencies, and no API/DB schema modifications.

## Architecture Decisions

### Why a display function vs. storing formatted text

The `cond` field is consumed by the backtest engine via `cond.split()` to extract DataFrame column names. Storing `(N)` notation breaks column lookups. The correct design is:
- **Storage**: bare indicator names only (e.g., `"LOW_4h < LOW_4h"`)
- **Display**: a pure function that combines `cond` + `shift_1` + `shift_2` for human readability

This keeps the data contract clean and puts the formatting concern where it belongs -- in the UI layer.

### Why handle ALL condition types (not just ind_relation)

The `formatCondDisplay` function checks for same-indicator-on-both-sides across all relation types, not just `ind_relation`. While `ind_relation` is the most common case, `cross_ind_relation` and theoretically `price_relation` / `p2p_relation` could also have the same token on both sides. A universal approach costs no extra complexity and prevents future edge-case bugs.

## File Changes

### 1. `.claude/skills/strategy-translator/SKILL.md` (line 58)

**Old text:**
```
- Same indicator at different shifts: `"LOW_6H(1) < LOW_6H(2)"`, never `"LOW_6H < LOW_6H"`
```

**New text:**
```
- Same indicator at different shifts: `"LOW_6H < LOW_6H"` with `shift_1` and `shift_2` differentiating them. Never put shift notation like `(N)` inside the `cond` string.
```

### 2. `.claude/skills/strategy-translator/translation-rules.md` (lines 39-41)

**Old text:**
```
- **El campo `cond` debe ser inequivoco cuando se compara el mismo indicador a diferentes shifts.**
  **Origen**: El translator genero `"LOW_6H < LOW_6H"` con shift_1=0, shift_2=1. Parece que compara algo consigo mismo.
  **Ejemplo**: `"LOW_6H < LOW_6H"` → `"LOW_6H(0) < LOW_6H(1)"`
```

**New text:**
```
- **El campo `cond` debe usar nombres de indicador bare (sin notacion de shift).**
  **Origen**: El translator genero `"LOW_6H(0) < LOW_6H(1)"` con shift notation dentro del cond string. Esto rompe el parser del engine que usa cond.split() para buscar columnas en el DataFrame.
  **Ejemplo correcto**: `"LOW_6H < LOW_6H"` con `"shift_1": 1, "shift_2": 2` — los shifts van en campos separados, no en el string.
```

### 3. `.claude/skills/strategy-translator/schema.json` (line 197)

**Old text:**
```json
"cond": { "type": "string", "description": "Human-readable condition. When same indicator appears on both sides with different shifts, include shift in string: LOW_6H(0) < LOW_6H(1)" },
```

**New text:**
```json
"cond": { "type": "string", "description": "Human-readable condition using bare indicator names. Shifts are encoded in shift_1/shift_2 fields, never in this string. Example: LOW_6H < LOW_6H (with shift_1=1, shift_2=2)" },
```

### 4. `frontend/src/components/strategies/draft-sections/ConditionsSection.tsx` (lines 9-12)

**Old text:**
```typescript
function ConditionBlock({ cond }: { cond: Condition }) {
  const displayCond = cond.cond_type === 'num_bars'
    ? `Exit after ${cond.cond} bars`
    : cond.cond;
```

**New text:**
```typescript
function formatCondDisplay(cond: Condition): string {
  if (cond.cond_type === 'num_bars') return `Exit after ${cond.cond} bars`;

  const parts = cond.cond.split(/\s+/);
  if (parts.length >= 3) {
    const [left, ...rest] = parts;
    const right = rest[rest.length - 1];
    const op = rest.slice(0, -1).join(' ');

    if (left === right && cond.shift_1 != null && cond.shift_2 != null) {
      return `${left}(${cond.shift_1}) ${op} ${right}(${cond.shift_2})`;
    }
  }

  return cond.cond;
}

function ConditionBlock({ cond }: { cond: Condition }) {
  const displayCond = formatCondDisplay(cond);
```

## Frontend Function Design

### `formatCondDisplay(cond: Condition): string`

A pure function that takes a `Condition` object and returns a display string with shift notation appended when needed for disambiguation.

**Logic by `cond_type`:**

| `cond_type` | `cond` example | Parsed tokens | Output |
|---|---|---|---|
| `num_bars` | `"12"` | N/A (early return) | `"Exit after 12 bars"` |
| `ind_relation` | `"LOW_4h < LOW_4h"` | `[LOW_4h, <, LOW_4h]` | `"LOW_4h(1) < LOW_4h(2)"` |
| `ind_relation` | `"CLOSE_4h > PMax_20_4h"` | `[CLOSE_4h, >, PMax_20_4h]` | `"CLOSE_4h > PMax_20_4h"` (different names, no change) |
| `num_relation` | `"ADX_20_4h < 20"` | `[ADX_20_4h, <, 20]` | `"ADX_20_4h < 20"` (different tokens, no change) |
| `price_relation` | `"EMA_20_4h > close_4h"` | `[EMA_20_4h, >, close_4h]` | `"EMA_20_4h > close_4h"` (different names) |
| `p2p_relation` | `"close_4h > close_4h"` | `[close_4h, >, close_4h]` | `"close_4h(1) > close_4h(2)"` (same name detected) |
| `cross_num_relation` | `"RSI_14_4h above 30"` | `[RSI_14_4h, above, 30]` | `"RSI_14_4h above 30"` (different tokens) |
| `cross_ind_relation` | `"EMA_20_4h above EMA_20_4h"` | `[EMA_20_4h, above, EMA_20_4h]` | `"EMA_20_4h(1) above EMA_20_4h(2)"` (same name) |
| `cross_price_relation` | `"EMA_20_4h above close_1D"` | `[EMA_20_4h, above, close_1D]` | `"EMA_20_4h above close_1D"` (different names) |
| `ind_direction` | `"RSI_MED_14_1D downwards"` | `[RSI_MED_14_1D, downwards]` | `"RSI_MED_14_1D downwards"` (only 2 tokens, no match) |

**Key design choices:**

1. **Split on whitespace** -- `cond.split(/\s+/)` handles any whitespace between tokens.
2. **Operator can be multi-word** -- `rest.slice(0, -1).join(' ')` handles operators like `"crosses above"` if they ever appear.
3. **Same-name detection** -- only triggers when `left === right` AND both shifts are non-null. This avoids false positives on `num_relation` (where right side is a number) and `ind_direction` (where there's only one operand).
4. **Fallback** -- any unrecognized format returns `cond.cond` as-is. No exceptions thrown.

## Testing Strategy

### Manual Verification

1. **Translator output** -- Run the translator on a test variant with same-indicator conditions. Verify the output JSON has bare indicator names in `cond` and shifts in `shift_1`/`shift_2`.
2. **Frontend display** -- Load a strategy with same-indicator conditions in the dashboard. Verify:
   - Same-indicator comparisons show `"LOW_4h(1) < LOW_4h(2)"`
   - Different-indicator comparisons show unchanged (e.g., `"CLOSE_4h > PMax_20_4h"`)
   - `num_bars` conditions show `"Exit after N bars"`
   - Shift badges still appear below the condition text
   - Cross-type conditions render correctly

### Backtest Validation

After the separate DB migration (out of scope), re-run strategy 9007 backtest and confirm:
- The engine receives bare indicator names
- Column lookups succeed (no NaN fill)
- Trades are generated (non-zero count)

## Open Questions

None. Both tasks are well-defined with exact line-level changes identified.
