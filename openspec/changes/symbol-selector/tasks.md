# Tasks: symbol-selector

**Status:** done
**Proposal:** proposal.md
**Spec:** specs/frontend/spec.md
**Design:** design.md

---

## Phase 1: Core Implementation

### Task 1.1: Add instrument query and handler to DraftViewer [x]

**File:** `frontend/src/components/strategies/DraftViewer.tsx`
**Type:** Modified
**Depends on:** —

Steps:

1. Add missing imports:
   - `useCallback` from `react` (if not already imported)
   - `getInstruments` from `../../services/instruments`
   - `Instrument` type from `../../types/instrument`
2. Add instruments query inside the component:
   ```typescript
   const { data: instrumentsData } = useQuery(['instruments'], getInstruments, { staleTime: Infinity });
   const instruments = instrumentsData?.data;
   ```
3. Define `INSTRUMENT_FIELD_MAP` constant (can be module-level or inside component):
   ```typescript
   const INSTRUMENT_FIELD_MAP = {
     symbol: 'symbol',
     sec_type: 'secType',
     exchange: 'exchange',
     currency: 'currency',
     multiplier: 'multiplier',
     min_tick: 'minTick',
   } as const;
   ```
4. Define `handleSymbolChange` callback with `useCallback`:
   - Guard: return early if `instrument.symbol === draft.data?.symbol`
   - Map instrument fields to draft fields via `INSTRUMENT_FIELD_MAP`
   - Merge: `{ ...draft.data, ...mappedFields }`
   - Call `mutation.mutate(mergedData)`
5. Pass three new props to `<InstrumentSection>`:
   - `instruments={instruments}`
   - `onSymbolChange={handleSymbolChange}`
   - `isMutating={mutation.isLoading}`

**Acceptance:** Component compiles. New props are passed to InstrumentSection.

---

### Task 1.2: Add dropdown to InstrumentSection [x]

**File:** `frontend/src/components/strategies/draft-sections/InstrumentSection.tsx`
**Type:** Modified
**Depends on:** Task 1.1

Steps:

1. Import `Instrument` type from `../../../types/instrument`
2. Extend the `Props` interface with three optional fields:
   ```typescript
   instruments?: Instrument[];
   onSymbolChange?: (instrument: Instrument) => void;
   isMutating?: boolean;
   ```
3. Destructure the new props in the component function signature
4. Replace the static symbol badge with a conditional render:
   - **If** `instruments && instruments.length > 0 && onSymbolChange`: render a `<select>` dropdown
     - `value={data.symbol}`
     - `disabled={isMutating}`
     - `onChange` handler: find selected instrument by symbol, call `onSymbolChange` if found
     - Options: `{i.symbol} ({i.exchange})` for each instrument
     - If current `data.symbol` is not in the list, render a disabled placeholder option
   - **Else**: render the existing static badge (graceful fallback)
5. Style the `<select>` to match the existing design system (cyan accent, dark background, rounded borders)

**Acceptance:** Dropdown renders when instruments are available, static badge otherwise. Selecting an instrument triggers `onSymbolChange`. Dropdown is disabled during mutation.

---

## Phase 2: Verification

### Task 2.1: TypeScript compilation check [x]

**Depends on:** Task 1.1, Task 1.2

Run:
```bash
cd frontend && npx tsc --noEmit
```

**Acceptance:** Zero type errors.

---

### Task 2.2: Manual scenario verification

**Depends on:** Task 2.1

Verify against spec scenarios:

- [ ] **SC-1:** Select a new instrument → all 6 fields update, single PUT request
- [ ] **SC-2:** Stop API / instruments fail → static badge displayed, no error
- [ ] **SC-3:** Draft has symbol not in instruments list → placeholder shown, can still select
- [ ] **SC-4:** Re-select same symbol → no network request
- [ ] **SC-5:** Instruments list empty → static badge
- [ ] **SC-6:** Mutation fails → dropdown re-enables, original symbol preserved

**Acceptance:** All scenarios pass.

---

## Summary

| Phase | Tasks | Files touched |
|-------|-------|---------------|
| 1. Core Implementation | 1.1, 1.2 | `DraftViewer.tsx`, `InstrumentSection.tsx` |
| 2. Verification | 2.1, 2.2 | — |

**Total files modified:** 2
**Total new files:** 0
**Backend changes:** None
