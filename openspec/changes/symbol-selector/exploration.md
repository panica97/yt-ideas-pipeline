# Exploration: symbol-selector

## Feature Goal

Add a dropdown in the draft's Instrument section that lets the user change the symbol. When a new symbol is selected, auto-update `multiplier`, `minTick`, `secType`, `exchange`, and `currency` from the instruments table.

---

## Current Architecture

### Frontend

#### `InstrumentSection.tsx`
- Pure display component. Receives `{ data: DraftData, todoFields: string[] }`.
- Renders a grid of instrument fields: symbol, secType, exchange, currency, multiplier, minTick, process_freq, rolling_days, UTC_tz, trading_hours.
- No interactivity, no callbacks, no mutations. Symbol is shown as a static cyan badge.
- Does NOT receive any mutation function or `onSymbolChange` callback.

#### `DraftViewer.tsx`
- Parent component. Receives `{ draft: DraftDetail }`.
- Parses `draft.data` via `parseDraftData()` into a typed `DraftData` object.
- Has a single mutation using `updateDraftData(draft.strat_code, data)` for the inline JSON editor.
- Passes `parsed` (DraftData) and `todoFields` to `InstrumentSection`.
- Does NOT pass mutation functions to section components — only the JSON editor uses mutations.
- Invalidates query keys: `['draft', strat_code]`, `['drafts']`, `['drafts-by-strategy']`.

#### `instruments.ts` (service)
- `getInstruments()` → `GET /instruments` → `InstrumentsListResponse { total, instruments[] }`
- Already used in `InstrumentsPage.tsx` with react-query key `['instruments']`.

#### `strategies.ts` (service)
- `updateDraftData(stratCode, data)` → `PUT /drafts/{stratCode}/data` → sends `{ data: Record<string, unknown> }`.
- No `fillTodo` function exists in the frontend service (the endpoint exists in backend but is not wired in the frontend).

### Types

#### `Instrument` (from instruments table)
```
symbol: string, sec_type: string, exchange: string, currency: string,
multiplier: number, min_tick: number, description: string | null
```

#### `DraftData` (draft JSON blob)
```
symbol: string, secType: string, exchange: string, currency: string,
multiplier: number, minTick: number
```

**Field name mapping (Instrument → DraftData):**
| Instrument  | DraftData   |
|-------------|-------------|
| `symbol`    | `symbol`    |
| `sec_type`  | `secType`   |
| `exchange`  | `exchange`  |
| `currency`  | `currency`  |
| `multiplier`| `multiplier`|
| `min_tick`  | `minTick`   |

### Backend

#### `strategy_service.py`
- `fill_todo(db, strat_code, path, value)` — Replaces a single value at a dot/bracket path in the draft JSONB. Recalculates TODO metadata. Designed for `_TODO` sentinels but works for any field.
- `update_draft_data(db, strat_code, data)` — Replaces the ENTIRE draft data blob. Validates structure (required keys: strat_name, symbol, secType, exchange, currency, strat_code). Recalculates TODO metadata.

#### `strategies.py` (router)
- `PATCH /drafts/{strat_code}/fill-todo` → body: `{ path, value }`
- `PUT /drafts/{strat_code}/data` → body: `{ data: dict }`

---

## Approach Analysis

### Approach A: Multiple `fillTodo` calls

**Mechanism:** When user selects a new symbol, fire 6 sequential (or parallel) PATCH requests to `/fill-todo`, one per field: `symbol`, `multiplier`, `minTick`, `secType`, `exchange`, `currency`.

**Pros:**
- Granular — each field is updated independently.
- `fillTodo` is designed for targeted field updates.

**Cons:**
- 6 HTTP requests for one user action — poor UX (latency, potential partial failure).
- No transactional guarantee: if request 3 fails, fields 1-2 are updated but 3-6 are stale → inconsistent state.
- `fillTodo` doesn't exist in the frontend service — would need to be added.
- Each call recalculates TODO metadata independently (wasted work).
- Race conditions if parallel: later responses may overwrite earlier ones depending on ORM refresh behavior.

**Verdict: NOT recommended.**

### Approach B: Single `updateDraftData` call (RECOMMENDED)

**Mechanism:** When user selects a new symbol, read current `draft.data`, merge the 6 instrument fields from the selected `Instrument`, and send one PUT request with the full updated blob.

**Pros:**
- Single atomic HTTP request — all-or-nothing, no inconsistent state.
- Already wired in the frontend (`updateDraftData` in `strategies.ts`).
- Already used by `DraftViewer.tsx` for the JSON editor — same mutation pattern.
- TODO metadata recalculated once.
- Simpler error handling (one request, one response).

**Cons:**
- Sends the entire data blob even though only 6 fields changed. Acceptable given draft blobs are small (< 5 KB typically).
- Needs structural validation to pass (but the fields we're setting are the exact required keys, so no issue).

**Verdict: RECOMMENDED. Reuses existing infrastructure with zero backend changes.**

---

## Implementation Sketch (Approach B)

### Changes Required

1. **`InstrumentSection.tsx`** — Add props for instruments list and an `onSymbolChange` callback. Replace the static symbol badge with a `<select>` dropdown. When selection changes, call `onSymbolChange(selectedInstrument)`.

2. **`DraftViewer.tsx`** — Fetch instruments via `useQuery(['instruments'], getInstruments)`. Pass instruments and a handler to `InstrumentSection`. The handler:
   - Takes the selected `Instrument`.
   - Merges fields into current `draft.data` (mapping `sec_type` → `secType`, `min_tick` → `minTick`).
   - Calls the existing `mutation.mutate(mergedData)`.

3. **No backend changes needed.**

4. **No new API calls needed** — `getInstruments` and `updateDraftData` already exist.

### Field Mapping Logic (frontend)
```ts
const updated = {
  ...draft.data,
  symbol: instrument.symbol,
  secType: instrument.sec_type,
  exchange: instrument.exchange,
  currency: instrument.currency,
  multiplier: instrument.multiplier,
  minTick: instrument.min_tick,
};
mutation.mutate(updated);
```

### UX Considerations
- Dropdown should show current symbol as selected by default.
- Consider showing `symbol (exchange)` in dropdown options for disambiguation (e.g., "ES (CME)", "NQ (CME)").
- The mutation already handles query invalidation and error display via the existing JSON editor pattern.
- The dropdown should be disabled while mutation is pending.

---

## Risks

1. **Field name mismatch** — The Instrument type uses `sec_type`/`min_tick` (snake_case) while DraftData uses `secType`/`minTick` (camelCase). The mapping must be explicit. Low risk if done correctly.
2. **Instruments not loaded** — If the instruments query fails or is empty, the dropdown should fall back to displaying the current symbol as static text. Low risk.
3. **Stale data race** — If user edits JSON and changes symbol simultaneously, one could overwrite the other. Mitigated by the existing query invalidation pattern. Low risk.
4. **`control_params.symbol`** — DraftData also has `control_params.strategy_filename` which may contain the symbol. This field is NOT part of the instrument table and should NOT be auto-updated. Need to verify no other symbol references exist in the blob. Low risk but worth checking during implementation.
