# Spec: symbol-selector / frontend

**Domain:** frontend
**Status:** draft
**Proposal:** ../proposal.md

---

## Overview

Replace the static symbol badge in `InstrumentSection` with a dropdown populated from the instruments table. On selection, auto-update the six instrument-related fields in the draft via a single `updateDraftData` mutation call.

## Affected Files

| File | Change type |
|------|-------------|
| `frontend/src/components/strategies/DraftViewer.tsx` | Modified |
| `frontend/src/components/strategies/draft-sections/InstrumentSection.tsx` | Modified |

## Requirements

### REQ-1: Instrument Selector Dropdown

The `InstrumentSection` component MUST render a `<select>` dropdown containing all instruments returned by the `getInstruments` API. Each option MUST display the instrument symbol. The dropdown MUST pre-select the option matching the current `data.symbol` value.

### REQ-2: Auto-populate Draft Fields on Selection

When the user selects a new instrument from the dropdown, the system MUST update the following draft fields atomically (single PUT via `updateDraftData`):

| Instrument field (snake_case) | Draft field (camelCase) |
|-------------------------------|-------------------------|
| `symbol`                      | `symbol`                |
| `sec_type`                    | `secType`               |
| `exchange`                    | `exchange`              |
| `currency`                    | `currency`              |
| `multiplier`                  | `multiplier`            |
| `min_tick`                    | `minTick`               |

The mutation MUST merge these six fields into the existing `draft.data` object, preserving all other fields unchanged.

### REQ-3: Graceful Degradation

If the instruments query fails or returns an empty list, the `InstrumentSection` SHOULD fall back to displaying the symbol as static text (the current behavior). No error SHOULD be shown to the user in this case.

### REQ-4: Dropdown Disabled During Mutation

The dropdown MUST be disabled while the `updateDraftData` mutation is in a pending state, preventing concurrent submissions.

### REQ-5: Data Flow via Props

`DraftViewer` MUST fetch the instruments list via `useQuery(['instruments'], getInstruments)` and pass the following new props to `InstrumentSection`:

- `instruments?: Instrument[]` -- the list of available instruments (undefined if query failed/loading)
- `onSymbolChange?: (instrument: Instrument) => void` -- callback to trigger the mutation
- `isMutating?: boolean` -- whether the mutation is currently pending

These props MUST be optional so that `InstrumentSection` degrades gracefully when they are absent.

---

## Scenarios

### SC-1: Happy path -- user selects a new instrument

```gherkin
Given the draft has symbol "ES" and the instruments list has loaded successfully
  And the instruments list contains "ES", "NQ", "CL", "GC"
When the user selects "NQ" from the instrument dropdown
Then the system MUST call updateDraftData with the full draft.data merged with:
  | field      | value from NQ instrument |
  | symbol     | NQ                       |
  | secType    | sec_type of NQ           |
  | exchange   | exchange of NQ           |
  | currency   | currency of NQ           |
  | multiplier | multiplier of NQ         |
  | minTick    | min_tick of NQ           |
  And the dropdown MUST be disabled until the mutation completes
  And on success, the draft queries MUST be invalidated (queryKey: ['draft', stratCode], ['drafts'], ['drafts-by-strategy'])
  And the UI MUST reflect the updated instrument fields
```

### SC-2: Instruments API fails -- fallback to static display

```gherkin
Given the instruments query has failed or returned an error
When the InstrumentSection renders
Then it MUST display the symbol as a static text badge (current behavior)
  And no dropdown SHOULD be rendered
  And no error message SHOULD be displayed to the user
```

### SC-3: Selected symbol not in instruments list

```gherkin
Given the draft has symbol "ZZ" which does not exist in the instruments list
  And the instruments list has loaded successfully with ["ES", "NQ", "CL"]
When the InstrumentSection renders
Then the dropdown MUST be rendered with no option pre-selected (or a placeholder option)
  And the user MUST still be able to select any instrument from the list
  And selecting an instrument MUST update the draft fields per REQ-2
```

### SC-4: User selects the same symbol (no-op)

```gherkin
Given the draft has symbol "ES"
  And the instruments list has loaded with "ES" among its entries
  And "ES" is currently selected in the dropdown
When the user selects "ES" again from the dropdown
Then the system MUST NOT call updateDraftData
  And no mutation SHOULD be triggered
  And the UI MUST remain unchanged
```

### SC-5: Instruments list is empty

```gherkin
Given the instruments query succeeds but returns an empty list (total: 0)
When the InstrumentSection renders
Then it MUST fall back to static text display (same as SC-2)
  And no dropdown SHOULD be rendered
```

### SC-6: Mutation fails

```gherkin
Given the user selects a new instrument "CL" from the dropdown
When the updateDraftData mutation fails with an error
Then the dropdown MUST be re-enabled
  And the draft data MUST NOT change (queries are not invalidated on error)
  And the dropdown MUST revert to showing the original symbol
```

---

## Non-functional Requirements

- **NFR-1:** The instruments query SHOULD use `staleTime: Infinity` or a long cache duration since the instruments table rarely changes. This avoids redundant fetches when switching between drafts.
- **NFR-2:** The dropdown option text format MUST be `"SYMBOL (EXCHANGE)"` for disambiguation when the same symbol exists on multiple exchanges.

---

## Out of Scope

- Creating new instruments from the dropdown
- Batch-editing instruments across multiple drafts
- Any backend changes (all required endpoints already exist)
- Updating `control_params.strategy_filename` or any field outside the six listed in REQ-2
