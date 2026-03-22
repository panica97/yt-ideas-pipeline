# Design: symbol-selector

**Status:** draft
**Proposal:** proposal.md
**Spec:** specs/frontend/spec.md

---

## Technical Approach

The implementation modifies exactly two frontend files with zero backend changes. The pattern reuses the existing `updateDraftData` mutation already wired in `DraftViewer`.

1. **DraftViewer** fetches the instruments list via `useQuery(['instruments'], getInstruments)` with `staleTime: Infinity` (the instruments table rarely changes). It defines a `handleSymbolChange` callback that maps `Instrument` fields to `DraftData` fields, merges them into the current `draft.data`, and calls the existing `mutation.mutate()`. It passes the instruments list, callback, and mutation pending state as props to `InstrumentSection`.

2. **InstrumentSection** receives optional props (`instruments`, `onSymbolChange`, `isMutating`). When instruments are available, it renders a `<select>` dropdown in place of the static symbol badge. When instruments are unavailable or empty, it falls back to the current static text display.

---

## Architecture Decisions

### AD-1: Lift instrument query to DraftViewer

**Decision:** The `useQuery` for instruments lives in `DraftViewer`, not `InstrumentSection`.

**Rationale:** `InstrumentSection` is a presentational component — it receives data via props and renders UI. Keeping data-fetching in `DraftViewer` (which already owns the mutation) maintains this separation. `DraftViewer` is the natural owner because it needs both the instruments list (to pass down) and the mutation (to execute the update).

### AD-2: Use updateDraftData (full replace) instead of fillTodo (per-field)

**Decision:** Reuse the existing `updateDraftData` mutation for a single atomic PUT.

**Rationale:** `updateDraftData` replaces the entire `draft.data` object in one request. This is simpler than calling `fillTodo` six times (once per field). It matches the pattern already used by the inline JSON editor. The mutation already handles query invalidation for `['draft', stratCode]`, `['drafts']`, and `['drafts-by-strategy']`.

### AD-3: No-op guard for same symbol

**Decision:** The `handleSymbolChange` callback checks if the selected instrument's symbol matches the current `data.symbol` and returns early without triggering a mutation.

**Rationale:** Avoids unnecessary network requests when the user re-selects the current instrument (SC-4 in the spec).

---

## Data Flow

```
User selects instrument in <select>
  → InstrumentSection calls onSymbolChange(selectedInstrument)
  → DraftViewer.handleSymbolChange(instrument: Instrument)
    → Guard: if instrument.symbol === draft.data.symbol → return (no-op)
    → Map instrument fields to DraftData fields via INSTRUMENT_TO_DRAFT_MAP
    → Merge: { ...draft.data, ...mappedFields }
    → mutation.mutate(mergedData)
  → API: PUT /strategies/drafts/{strat_code}/data
  → onSuccess:
    → invalidateQueries(['draft', strat_code])
    → invalidateQueries(['drafts'])
    → invalidateQueries(['drafts-by-strategy'])
  → React Query refetches → UI reflects updated instrument fields
```

---

## File Changes

### `frontend/src/components/strategies/DraftViewer.tsx` — Modified

Changes:
1. Add import for `useQuery` (from `@tanstack/react-query`, already partially imported)
2. Add import for `getInstruments` (from `../../services/instruments`)
3. Add import for `Instrument` type (from `../../types/instrument`)
4. Add `useQuery(['instruments'], getInstruments, { staleTime: Infinity })` call
5. Define `handleSymbolChange` callback using `useCallback`
6. Pass three new props to `<InstrumentSection>`: `instruments`, `onSymbolChange`, `isMutating`

### `frontend/src/components/strategies/draft-sections/InstrumentSection.tsx` — Modified

Changes:
1. Add import for `Instrument` type
2. Extend `Props` interface with three optional fields
3. Replace static symbol badge with conditional: `<select>` dropdown when instruments available, static badge otherwise
4. Add `handleChange` local handler that finds the selected instrument by symbol and calls `onSymbolChange`

---

## Interfaces

### InstrumentSection Props (extended)

```typescript
interface Props {
  data: DraftData;
  todoFields: string[];
  // New optional props for symbol selection
  instruments?: Instrument[];
  onSymbolChange?: (instrument: Instrument) => void;
  isMutating?: boolean;
}
```

### Field Mapping Constant (in DraftViewer)

```typescript
const INSTRUMENT_TO_DRAFT_MAP: Record<keyof Pick<Instrument, 'symbol' | 'sec_type' | 'exchange' | 'currency' | 'multiplier' | 'min_tick'>, keyof Pick<DraftData, 'symbol' | 'secType' | 'exchange' | 'currency' | 'multiplier' | 'minTick'>> = {
  symbol: 'symbol',
  sec_type: 'secType',
  exchange: 'exchange',
  currency: 'currency',
  multiplier: 'multiplier',
  min_tick: 'minTick',
};
```

Simplified for readability, this can also be a plain object:

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

### handleSymbolChange Callback (in DraftViewer)

```typescript
const handleSymbolChange = useCallback((instrument: Instrument) => {
  if (instrument.symbol === draft.data?.symbol) return; // no-op guard

  const mappedFields: Record<string, unknown> = {};
  for (const [instKey, draftKey] of Object.entries(INSTRUMENT_FIELD_MAP)) {
    mappedFields[draftKey] = instrument[instKey as keyof Instrument];
  }

  const mergedData = { ...draft.data, ...mappedFields };
  mutation.mutate(mergedData);
}, [draft.data, mutation]);
```

### Select Dropdown (in InstrumentSection)

```tsx
{instruments && instruments.length > 0 && onSymbolChange ? (
  <select
    value={data.symbol}
    disabled={isMutating}
    onChange={(e) => {
      const selected = instruments.find(i => i.symbol === e.target.value);
      if (selected) onSymbolChange(selected);
    }}
    className="text-lg font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-400 disabled:opacity-50"
  >
    {!instruments.some(i => i.symbol === data.symbol) && (
      <option value={data.symbol} disabled>{data.symbol} (not found)</option>
    )}
    {instruments.map(i => (
      <option key={i.symbol} value={i.symbol}>
        {i.symbol} ({i.exchange})
      </option>
    ))}
  </select>
) : (
  <span className="inline-block text-lg font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-1">
    {data.symbol}
  </span>
)}
```

---

## Edge Cases

| Case | Handling |
|------|----------|
| Instruments query loading | `instruments` is `undefined` → static badge rendered |
| Instruments query error | `instruments` is `undefined` → static badge rendered (graceful degradation) |
| Instruments list empty (`total: 0`) | `instruments.length === 0` → static badge rendered |
| Current symbol not in instruments list (SC-3) | Render a disabled placeholder `<option>` with the current symbol + "(not found)" |
| User re-selects same symbol (SC-4) | `handleSymbolChange` returns early, no mutation fired |
| Mutation fails (SC-6) | Dropdown re-enables (`isMutating` becomes false), draft data unchanged (query not invalidated on error), dropdown shows original symbol because `draft.data` hasn't changed |

---

## Testing

Manual testing only (no test framework in the project):

1. Open a draft with a known symbol (e.g., "ES") → verify dropdown renders with all instruments
2. Select a different instrument (e.g., "NQ") → verify all 6 fields update
3. Re-select the same instrument → verify no network request fires
4. Stop the API → verify dropdown falls back to static badge
5. Verify dropdown is disabled during mutation (add artificial delay to API if needed)

---

## No Migration Needed

All data structures, API endpoints, and database tables remain unchanged. This is a purely frontend change.
