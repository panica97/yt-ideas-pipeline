# Proposal: Fix Backtest Condition Format

## Intent

Fix the backtest condition format mismatch that causes the engine to produce 0 trades silently. The strategy-translator puts shift notation `(N)` inside `cond` strings, but the engine's `cond.split()` parser expects bare indicator names only. Tokens like `"LOW_4h(1)"` don't match any DataFrame column, causing NaN fill, all-False comparisons, and 0 trades.

## Scope

### In Scope
- Fix strategy-translator skill files (SKILL.md, translation-rules.md, schema.json) to stop including `(N)` shift notation in `cond` strings
- Fix frontend ConditionBlock to visually render shift notation for readability when the same indicator appears on both sides
- Both tasks ship together so the UI remains clear after the data format change

### Out of Scope
- DB migration to fix existing drafts with `(N)` in their cond strings (Phase 10.1 task 3, separate change)
- Changes to the external backtest engine (it's correct)
- Changes to `docs/STRATEGY_FILE_REFERENCE.md` (already correct, uses bare names)
- Changes to example strategy files (1001, 1009, 1015, 1017 — already correct)

## Approach

**Task 1: Fix translator skill files (3 files)**

Remove the `(N)` notation instructions from the three translator files. The `cond` field must always contain bare indicator names like `"LOW_4h < LOW_4h"` with shifts only in `shift_1`/`shift_2` fields.

Specific changes:
- `SKILL.md` line 58: Replace the instruction that says to use `"LOW_6H(1) < LOW_6H(2)"` with one that says to use `"LOW_6H < LOW_6H"` with `shift_1`/`shift_2` differentiating them
- `translation-rules.md` lines 39-41: Reverse the rule — the old "fix" (`LOW_6H` → `LOW_6H(0)`) was actually the bug
- `schema.json` line 197: Update cond field description to state bare indicator names, shifts in separate fields

**Task 2: Fix frontend ConditionBlock display (1 file)**

In `ConditionsSection.tsx`, add a `formatCondDisplay` function that detects when the same indicator name appears on both sides of the operator and appends `(shift_1)` / `(shift_2)` to the display string for visual disambiguation. This is display-only — the stored `cond` remains bare.

Display logic:
- For `ind_relation` with same indicator on both sides: `"LOW_4h(1) < LOW_4h(2)"`
- For `num_relation` with shift: `"RSI_N_4h(2) < 70"` (only if shift_1 is non-zero)
- For `num_bars`: no change needed
- For cross types: append shifts similarly when same indicator detected
- All other cases: display `cond` as-is

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.claude/skills/strategy-translator/SKILL.md` | Modified | Remove `(N)` notation instruction (line 58) |
| `.claude/skills/strategy-translator/translation-rules.md` | Modified | Reverse the `(N)` rule (lines 39-41) |
| `.claude/skills/strategy-translator/schema.json` | Modified | Remove `(N)` from cond field description (line 197) |
| `frontend/src/components/strategies/draft-sections/ConditionsSection.tsx` | Modified | Add `formatCondDisplay` function to ConditionBlock |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing drafts in DB still have `(N)` in cond strings | High | Separate DB migration (out of scope, Phase 10.1 task 3) |
| Future translator runs produce wrong format if skill files cached | Low | Skills are read fresh each invocation |
| `"LOW_4h < LOW_4h"` looks confusing without visual shifts | Medium | Frontend display fix (Task 2) renders shifts visually |
| Cross-type conditions with same indicator on both sides | Low | Same detection logic handles this edge case |

## Rollback Plan

- **Translator**: revert the 3 skill files via `git checkout` — no data is modified
- **Frontend**: revert `ConditionsSection.tsx` via `git checkout`
- No database changes, no API changes, no infrastructure changes

## Dependencies

- None. Both tasks are independent of each other but should ship together for UX consistency
- Does NOT depend on the DB migration — that is a follow-up change

## Success Criteria

- [ ] New translator runs produce `cond` strings without `(N)` notation
- [ ] Frontend displays shifts visually for same-indicator comparisons: `"LOW_4h(1) < LOW_4h(2)"`
- [ ] Frontend displays other condition types unchanged
- [ ] Backtest engine receives bare indicator names and can match DataFrame columns
- [ ] Re-running strategy 9007 backtest (after separate DB migration) produces trades
