# Tasks: Fix Backtest Condition Format

**Change**: fix-condition-format
**Status**: phase-1-2-done
**Depends on**: specs (strategy-translator, frontend-display), design.md

---

## Phase 1: Fix strategy-translator skill files

These three tasks remove the `(N)` shift notation instructions from translator skill files so that newly translated strategies produce bare indicator names in `cond` strings.

### 1.1 Update SKILL.md — remove (N) notation instruction

**File**: `.claude/skills/strategy-translator/SKILL.md`
**Line**: ~58
**Action**: Replace the instruction that says to use `"LOW_6H(1) < LOW_6H(2)"` with one that says to use `"LOW_6H < LOW_6H"` with `shift_1`/`shift_2` differentiating them. Explicitly state that `(N)` notation MUST NOT appear in `cond` strings.

**Old text** (approximate):
```
- Same indicator at different shifts: `"LOW_6H(1) < LOW_6H(2)"`, never `"LOW_6H < LOW_6H"`
```

**New text**:
```
- Same indicator at different shifts: `"LOW_6H < LOW_6H"` with `shift_1` and `shift_2` differentiating them. Never put shift notation like `(N)` inside the `cond` string.
```

**Spec reference**: REQ-T1, REQ-T2 (strategy-translator spec)

---

### 1.2 Update translation-rules.md — reverse the (N) rule

**File**: `.claude/skills/strategy-translator/translation-rules.md`
**Lines**: ~39-41
**Action**: Reverse the existing rule. The old "fix" that added `(0)`/`(1)` to cond strings was actually the bug. Replace it with a rule that states bare names are correct and shifts go in separate fields.

**Old text** (approximate):
```
- **El campo `cond` debe ser inequivoco cuando se compara el mismo indicador a diferentes shifts.**
  **Origen**: El translator genero `"LOW_6H < LOW_6H"` con shift_1=0, shift_2=1. Parece que compara algo consigo mismo.
  **Ejemplo**: `"LOW_6H < LOW_6H"` → `"LOW_6H(0) < LOW_6H(1)"`
```

**New text**:
```
- **El campo `cond` debe usar nombres de indicador bare (sin notacion de shift).**
  **Origen**: El translator genero `"LOW_6H(0) < LOW_6H(1)"` con shift notation dentro del cond string. Esto rompe el parser del engine que usa cond.split() para buscar columnas en el DataFrame.
  **Ejemplo correcto**: `"LOW_6H < LOW_6H"` con `"shift_1": 1, "shift_2": 2` — los shifts van en campos separados, no en el string.
```

**Spec reference**: REQ-T1, SC-T-NEG2 (strategy-translator spec)

---

### 1.3 Update schema.json — remove (N) from cond description

**File**: `.claude/skills/strategy-translator/schema.json`
**Line**: ~197
**Action**: Update the `cond` field description to state that bare indicator names are required and shifts are encoded in `shift_1`/`shift_2` fields only.

**Old text** (approximate):
```json
"cond": { "type": "string", "description": "Human-readable condition. When same indicator appears on both sides with different shifts, include shift in string: LOW_6H(0) < LOW_6H(1)" },
```

**New text**:
```json
"cond": { "type": "string", "description": "Human-readable condition using bare indicator names. Shifts are encoded in shift_1/shift_2 fields, never in this string. Example: LOW_6H < LOW_6H (with shift_1=1, shift_2=2)" },
```

**Spec reference**: REQ-T1, REQ-T2 (strategy-translator spec)

---

## Phase 2: Fix frontend condition display

These tasks add a display function that renders shift notation visually in the ConditionBlock component, without modifying stored data.

### 2.1 Add `formatCondDisplay` function

**File**: `frontend/src/components/strategies/draft-sections/ConditionsSection.tsx`
**Location**: Before the `ConditionBlock` function (around line 9)
**Action**: Add a new pure function `formatCondDisplay(cond: Condition): string` that produces a human-readable display string with shift notation appended to indicator/price tokens.

**Function logic**:

1. **`num_bars`**: Early return `"Exit after ${cond.cond} bars"` — no shift annotation.

2. **`ind_direction`**: Parse as `[indicator, direction]`. Append `(shift_1)` to indicator only. Example: `"EMA_1D(1) upwards"`.

3. **Relation types** (`ind_relation`, `price_relation`, `p2p_relation`): Parse as `[left, operator, right]`. Append `(shift_1)` to left token, `(shift_2)` to right token. Example: `"LOW_4h(1) < LOW_4h(2)"`, `"CLOSE(1) > EMA_1D(1)"`.

4. **`num_relation`**: Parse as `[indicator, operator, number]`. Append `(shift_1)` to indicator only. Do NOT append shift to the numeric token. Example: `"RSI_N_4h(2) < 30"`.

5. **Cross types** (`cross_above`, `cross_bellow`): Parse as `[left, above/bellow, right]`. Append `(shift_1)` to left. If right is numeric, do NOT append shift. If right is an indicator/price name, append `(shift_2)`. Example: `"MACD_macd_1h(1) above MACD_macdsignal_1h(1)"`, `"RSI_N_4h(1) bellow 70"`.

6. **Fallback**: If parsing fails or `cond_type` is unrecognized, return `cond.cond` as-is.

**Key implementation detail**: To distinguish numeric tokens from indicator/price tokens, check if the token matches `/^\d+(\.\d+)?$/` (a plain number). Numbers do not get shift annotation.

**Spec reference**: REQ-F1, REQ-F2, REQ-F3, REQ-F4, REQ-F5 (frontend-display spec)

---

### 2.2 Update `ConditionBlock` to use `formatCondDisplay`

**File**: `frontend/src/components/strategies/draft-sections/ConditionsSection.tsx`
**Location**: Inside the `ConditionBlock` component (lines ~9-12)
**Action**: Replace the existing inline display logic with a call to `formatCondDisplay`.

**Old code** (approximate):
```typescript
function ConditionBlock({ cond }: { cond: Condition }) {
  const displayCond = cond.cond_type === 'num_bars'
    ? `Exit after ${cond.cond} bars`
    : cond.cond;
```

**New code**:
```typescript
function ConditionBlock({ cond }: { cond: Condition }) {
  const displayCond = formatCondDisplay(cond);
```

**Spec reference**: REQ-F1 (frontend-display spec)

---

## Phase 3: Verification

### 3.1 Verify translator skill files

**Action**: Read each of the 3 modified skill files and confirm:
- [ ] No `(N)` notation instruction exists in `SKILL.md`
- [ ] `translation-rules.md` states bare names are correct, `(N)` is the bug
- [ ] `schema.json` cond description says "bare indicator names" and "never in this string"
- [ ] No contradictory instructions remain in any of the three files

**Spec reference**: SC-T-NEG1 (strategy-translator spec) — no `cond` should match `\(\d+\)`

### 3.2 Verify frontend display function

**Action**: Review `ConditionsSection.tsx` and confirm:
- [ ] `formatCondDisplay` is a pure function (no side effects, no mutations)
- [ ] `num_bars` returns `"Exit after N bars"` with no shift
- [ ] `ind_direction` appends `(shift_1)` to indicator only
- [ ] Relation types append `(shift_1)` to left, `(shift_2)` to right
- [ ] `num_relation` does NOT append shift to numeric token
- [ ] Cross types handle both indicator and numeric right-side tokens
- [ ] Fallback returns raw `cond.cond` for unparseable strings
- [ ] TypeScript compiles without errors

**Spec reference**: All SC-F scenarios (frontend-display spec)

### 3.3 Visual verification in browser

**Action**: Load the dashboard at `http://localhost:5173`, navigate to a strategy draft with conditions, and confirm:
- [ ] Same-indicator conditions display with shift notation (e.g., `LOW_4h(1) < LOW_4h(2)`)
- [ ] Different-indicator conditions display with shifts on both sides (e.g., `RSI_N_1h(1) > SMA_1h(1)`)
- [ ] Numeric conditions show shift only on indicator (e.g., `RSI_N_4h(2) < 30`)
- [ ] `num_bars` conditions show `"Exit after N bars"`
- [ ] Direction conditions show shift on indicator (e.g., `EMA_1D(1) upwards`)
- [ ] Shift badges below condition text still render correctly

---

## Task Summary

| ID | Phase | File | Action | Risk |
|----|-------|------|--------|------|
| 1.1 | Translator | `.claude/skills/strategy-translator/SKILL.md` | Replace (N) instruction | Low | [x] |
| 1.2 | Translator | `.claude/skills/strategy-translator/translation-rules.md` | Reverse (N) rule | Low | [x] |
| 1.3 | Translator | `.claude/skills/strategy-translator/schema.json` | Update cond description | Low | [x] |
| 2.1 | Frontend | `frontend/src/.../ConditionsSection.tsx` | Add `formatCondDisplay` function | Medium | [x] |
| 2.2 | Frontend | `frontend/src/.../ConditionsSection.tsx` | Wire function into ConditionBlock | Low | [x] |
| 3.1 | Verify | 3 skill files | Check no (N) instructions remain | — |
| 3.2 | Verify | `ConditionsSection.tsx` | Review function correctness | — |
| 3.3 | Verify | Browser | Visual check in dashboard | — |

**Total**: 5 implementation tasks + 3 verification tasks across 2 phases.

**Dependencies**: Phase 1 and Phase 2 are independent and can be executed in parallel. Phase 3 runs after both are complete.
