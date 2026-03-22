# Proposal: symbol-selector

## Intent

Let users change a draft's instrument symbol from a dropdown in the UI, auto-updating multiplier, minTick, secType, exchange, and currency from the instruments table.

## Scope

### In scope
- Add instrument selector dropdown to `InstrumentSection` component, replacing the static symbol badge
- Auto-populate instrument fields (symbol, secType, exchange, currency, multiplier, minTick) on selection
- Use existing `updateDraftData` mutation — single atomic PUT request, no backend changes

### Out of scope
- Creating new instruments from the selector
- Changing instruments on multiple drafts at once
- Backend changes (none needed — all endpoints and services already exist)
- Updating `control_params.strategy_filename` or any other field outside the 6 instrument fields

## Approach

**Single `updateDraftData` call (Approach B from exploration)**

1. **DraftViewer.tsx**: Add a `useQuery(['instruments'], getInstruments)` call to fetch the full instruments list. Define a `handleSymbolChange(instrument: Instrument)` callback that:
   - Takes the selected `Instrument` object
   - Merges its fields into the current `draft.data`, mapping snake_case to camelCase (`sec_type` → `secType`, `min_tick` → `minTick`)
   - Calls the existing `mutation.mutate(mergedData)` (same pattern as the inline JSON editor)
   - Pass `instruments` list and `onSymbolChange` callback as new props to `InstrumentSection`

2. **InstrumentSection.tsx**: Accept new optional props (`instruments?: Instrument[]`, `onSymbolChange?: (instrument: Instrument) => void`). Replace the static symbol badge with a `<select>` dropdown when instruments are available. Show `symbol (exchange)` format in options for disambiguation. Disable dropdown while mutation is pending. Fall back to static text if instruments list is empty or undefined.

3. **No backend changes.** `getInstruments` and `updateDraftData` already exist and are sufficient.

### Field Mapping

| Instrument (snake_case) | DraftData (camelCase) |
|--------------------------|----------------------|
| `symbol`                 | `symbol`             |
| `sec_type`               | `secType`            |
| `exchange`               | `exchange`           |
| `currency`               | `currency`           |
| `multiplier`             | `multiplier`         |
| `min_tick`               | `minTick`            |

## Affected Areas

| File | Change |
|------|--------|
| `frontend/src/components/strategies/DraftViewer.tsx` | Modified — add `useQuery` for instruments, define `handleSymbolChange`, pass new props to `InstrumentSection` |
| `frontend/src/components/strategies/draft-sections/InstrumentSection.tsx` | Modified — accept instruments + callback props, render `<select>` dropdown instead of static badge |

## Risks

1. **snake_case/camelCase mapping** — The `Instrument` type uses `sec_type`/`min_tick` while `DraftData` uses `secType`/`minTick`. The mapping must be explicit in the handler. Low risk if done correctly, but easy to miss.
2. **Instruments query failure** — If the instruments fetch fails or returns empty, the dropdown should degrade gracefully to static text. Low risk.
3. **Stale data race** — If user edits via JSON editor and changes symbol simultaneously, one could overwrite the other. Mitigated by existing query invalidation. Low risk.

## Rollback

Revert 2 frontend files (`DraftViewer.tsx`, `InstrumentSection.tsx`) to their previous state. No database migrations or backend changes to undo.

## Success Criteria

- User can open a draft, see a dropdown with all available instruments in the Instrument section
- Selecting a different instrument auto-updates symbol, secType, exchange, currency, multiplier, and minTick
- The update is atomic (single PUT request) and the UI reflects the change immediately after mutation completes
- If instruments fail to load, the symbol displays as static text (current behavior) — no errors
