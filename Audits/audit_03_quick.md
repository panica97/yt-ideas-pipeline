# Audit 03 (Quick) - Phase 10.3 Frontend Backtest Enhancements

**Date**: 2026-03-23
**Scope**: Frontend backtest area — `BacktestPanel.tsx`, `backtest.ts` types, `backtests.ts` service, Recharts equity curve
**Auditor**: Claude Opus 4.6 (1M context)
**Status**: Complete

---

## Tracking Table

| # | Severity | Category | Finding | File(s) | Status |
|---|----------|----------|---------|---------|--------|
| 01 | MEDIUM | Edge Case | Return/DD ratio uses signed division — negative return with negative DD produces misleading positive ratio | `BacktestPanel.tsx:94-101` | Open |
| 02 | MEDIUM | Type Safety | `return_pct` and `max_drawdown_pct` accessed via `as number \| undefined` cast instead of proper type narrowing | `BacktestPanel.tsx:90-91` | Open |
| 03 | MEDIUM | Edge Case | Equity curve sorts by `exit_date` string comparison, not Date parsing — breaks with inconsistent date formats | `BacktestPanel.tsx:135-137` | Open |
| 04 | LOW | UX | XAxis renders raw date strings without formatting — long ISO timestamps will overlap and be unreadable | `BacktestPanel.tsx:150-153` | Open |
| 05 | LOW | Type Safety | `BacktestMetrics` index signature `[key: string]: unknown` weakens type safety on known fields | `backtest.ts:15` | Open |
| 06 | LOW | Performance | Equity curve `useMemo` dep array only includes `trades` reference — no issue currently but relies on React Query returning new array refs on refetch | `BacktestPanel.tsx:134-143` | Open |

---

## Findings by Severity

### MEDIUM (3 findings)

#### M-01: Return/DD ratio division can produce misleading positive ratio

- **File**: `frontend/src/components/strategies/BacktestPanel.tsx:94-101`
- **Detail**: The Return/DD ratio calculation at line 95 does `returnPct / maxDdPct`. If the engine returns both values as negative (e.g., `return_pct = -15`, `max_drawdown_pct = -20`), the division produces `0.75` (positive), which is displayed as if the strategy is profitable relative to its risk. The fallback path at line 99 uses `Math.abs()` to handle this, but the primary path does not. Additionally, if `return_pct` is positive and `max_drawdown_pct` is negative (a plausible engine convention where DD is expressed as a negative percentage), the ratio will be negative, which is semantically wrong.
- **Risk**: Misleading metric display — users may evaluate strategy quality based on an incorrect ratio.
- **Route**: quick fix — normalize both values with `Math.abs()` before dividing, or define a clear contract on the sign convention from the engine.

#### M-02: Unsafe type assertion for optional metrics fields

- **File**: `frontend/src/components/strategies/BacktestPanel.tsx:90-91`
- **Detail**: `const returnPct = metrics.return_pct as number | undefined` and `const maxDdPct = metrics.max_drawdown_pct as number | undefined`. These fields are already typed as optional in `BacktestMetrics` (`return_pct?: number`), so the `as` cast is redundant. However, the real issue is that the engine output is an arbitrary JSON dict stored in a JSONB column. There is no server-side validation that `return_pct` is actually a `number` — it could be a string, `null`, or any JSON value. The `as` cast silences TypeScript but doesn't provide runtime safety.
- **Risk**: If the engine returns a non-number value (e.g., `"N/A"` string), the `!= null` check passes, and the division will produce `NaN`, which gets displayed as `"NaN"`.
- **Route**: quick fix — add a runtime `typeof` check: `typeof metrics.return_pct === 'number'` instead of `!= null`.

#### M-03: Equity curve date sorting relies on string comparison

- **File**: `frontend/src/components/strategies/BacktestPanel.tsx:135-137`
- **Detail**: The sort uses `new Date(a.exit_date).getTime() - new Date(b.exit_date).getTime()`. This correctly parses dates, so it works for valid ISO date strings. However, `BacktestTrade.exit_date` is typed as `string` with no format guarantee. If the engine returns dates in a non-ISO format (e.g., `"03/23/2026"` or epoch timestamps), `new Date()` may parse them incorrectly or return `NaN`, causing the sort to silently produce wrong ordering and a garbled equity curve.
- **Risk**: Equity curve displays trades in wrong order if date format changes. No error is shown — the chart just looks wrong.
- **Route**: quick fix — add a guard: if any `getTime()` returns `NaN`, log a warning or skip sorting.

---

### LOW (3 findings)

#### L-04: XAxis date labels will overlap on dense data

- **File**: `frontend/src/components/strategies/BacktestPanel.tsx:150-153`
- **Detail**: The XAxis renders raw `date` strings (whatever the engine returns) with `fontSize: 10`. For backtests with hundreds of trades, all date labels will render and overlap. Recharts' `XAxis` does have auto-tick-interval logic, but the raw date strings (likely full ISO timestamps) are too long even for spaced ticks. No `tickFormatter` is provided to shorten dates.
- **Route**: quick fix — add a `tickFormatter` to show abbreviated dates (e.g., `MM/DD`) and optionally set `interval="preserveStartEnd"` or a custom interval.

#### L-05: Index signature weakens BacktestMetrics type safety

- **File**: `frontend/src/types/backtest.ts:15`
- **Detail**: `[key: string]: unknown` allows any key to be accessed on `BacktestMetrics` without TypeScript error. This was likely added to accommodate arbitrary engine fields, but it means typos like `metrics.retrun_pct` won't be caught at compile time. Similarly, `BacktestTrade` at line 26 has the same pattern.
- **Risk**: Low — the flexibility is intentional for forward-compatibility with engine changes, but it disables a layer of compile-time safety.
- **Route**: Consider removing the index signature and using a separate `extra?: Record<string, unknown>` field if arbitrary fields need to be preserved, or keep as-is and document the trade-off.

#### L-06: Tooltip formatter uses untyped `value` parameter

- **File**: `frontend/src/components/strategies/BacktestPanel.tsx:168`
- **Detail**: The Recharts `Tooltip` `formatter` callback receives `value` as `any` (Recharts typing). The code does `Number(value)` which is fine, but the formatter signature `(value) => [...]` loses type information. This is a Recharts API limitation, not a bug.
- **Route**: No action needed — this is idiomatic Recharts usage. Noting for completeness.

---

## Cross-Cutting Observations

### Recharts Integration Quality

The Recharts integration is clean and follows standard patterns:
- `ResponsiveContainer` wraps the chart correctly for responsive sizing.
- CSS variables are used for theming (`var(--color-border)`, `var(--color-accent)`), which integrates well with the existing design system.
- `dot={false}` on the Line prevents performance issues with many data points.
- The chart is lazily rendered (behind a toggle button), which avoids unnecessary rendering.

### Engine-Frontend Contract Gap

The biggest systemic risk in this area is the lack of a defined contract between the backtest engine output and the frontend types. The engine returns an arbitrary dict (no schema validation on the API side), which gets stored as JSONB and served to the frontend. The frontend `BacktestMetrics` type defines expected fields, but there's no guarantee the engine produces them. The Phase 10.3 additions (`return_pct`, `max_drawdown_pct`) amplify this — these fields are optional in the type, but the UI degrades to "N/A" silently rather than indicating the engine didn't produce them.

### Relationship to audit_02 Findings

- **L-14 (duplicate total_trades/trade_count)** is still present — the MetricsGrid at line 87 uses the same `metrics.total_trades ?? metrics.trade_count ?? 0` fallback.
- **M-11 (delete mutation no error handling)** is still present — `deleteMutation` at line 356-361 has no `onError`.

---

## Action Items

| # | Severity | Action Item | Effort | Route |
|---|----------|-------------|--------|-------|
| 1 | MEDIUM | Normalize Return/DD ratio with `Math.abs()` on both values | small | quick fix |
| 2 | MEDIUM | Add `typeof === 'number'` runtime checks for optional metrics fields | small | quick fix |
| 3 | MEDIUM | Add NaN guard on date parsing in equity curve sort | small | quick fix |
| 4 | LOW | Add `tickFormatter` to XAxis for abbreviated dates | small | quick fix |
| 5 | LOW | Document or refactor index signature trade-off in BacktestMetrics | small | quick fix |
| 6 | LOW | (No action) Tooltip formatter typing is idiomatic | — | — |

---

## Statistics

| Metric | Value |
|---|---|
| Total findings | 6 |
| HIGH severity | 0 |
| MEDIUM severity | 3 |
| LOW severity | 3 |
| Files audited | 3 |
