# Spec: frontend-display — Fix Condition Format Display

**Change**: fix-condition-format
**Domain**: frontend-display
**Status**: draft
**Depends on**: proposal.md

## Overview

The ConditionBlock component MUST visually render shift notation when displaying conditions, so that users can distinguish operands at different shifts. This is a display-only transformation — the underlying condition data MUST NOT be modified.

---

## Requirements

### REQ-F1: Display shifts visually

The ConditionBlock component MUST append `(shift_N)` to indicator and price tokens when rendering the `cond` string for display purposes.

### REQ-F2: Format by condition type

The display format MUST vary by `cond_type` as specified in the scenarios below.

### REQ-F3: Show shift 0

When a shift value is `0`, it SHOULD still be displayed as `(0)`. Shift 0 means "current bar" and is semantically meaningful.

### REQ-F4: No data mutation

The display function MUST NOT modify the underlying condition object. It SHALL operate on a copy or produce a new display string without side effects.

### REQ-F5: Graceful fallback

If the `cond` string cannot be parsed into the expected format for its `cond_type`, the component SHOULD display the raw `cond` string unchanged.

---

## Scenarios

### SC-F1: ind_relation — same indicator, different shifts

**Given** a condition:
```json
{
  "cond_type": "ind_relation",
  "cond": "LOW_4h < LOW_4h",
  "shift_1": 1,
  "shift_2": 2
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"LOW_4h(1) < LOW_4h(2)"`

### SC-F2: ind_relation — different indicators

**Given** a condition:
```json
{
  "cond_type": "ind_relation",
  "cond": "RSI_N_1h > SMA_1h",
  "shift_1": 1,
  "shift_2": 1
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"RSI_N_1h(1) > SMA_1h(1)"`

### SC-F3: num_relation — indicator vs number

**Given** a condition:
```json
{
  "cond_type": "num_relation",
  "cond": "RSI_N_4h < 30",
  "shift_1": 2,
  "shift_2": 0
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"RSI_N_4h(2) < 30"`
**And** the number `30` MUST NOT have shift notation appended.

### SC-F4: num_relation — shift 0

**Given** a condition:
```json
{
  "cond_type": "num_relation",
  "cond": "RSI_N_4h > 70",
  "shift_1": 0,
  "shift_2": 0
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"RSI_N_4h(0) > 70"`

### SC-F5: price_relation — indicator vs price

**Given** a condition:
```json
{
  "cond_type": "price_relation",
  "cond": "CLOSE > EMA_1D",
  "shift_1": 1,
  "shift_2": 1
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"CLOSE(1) > EMA_1D(1)"`

### SC-F6: p2p_relation — price vs price

**Given** a condition:
```json
{
  "cond_type": "p2p_relation",
  "cond": "HIGH_4h > HIGH_4h",
  "shift_1": 1,
  "shift_2": 2
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"HIGH_4h(1) > HIGH_4h(2)"`

### SC-F7: cross_above — indicator crosses above indicator

**Given** a condition:
```json
{
  "cond_type": "cross_above",
  "cond": "MACD_macd_1h above MACD_macdsignal_1h",
  "shift_1": 1,
  "shift_2": 1
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"MACD_macd_1h(1) above MACD_macdsignal_1h(1)"`

### SC-F8: cross_bellow — indicator crosses below number

**Given** a condition:
```json
{
  "cond_type": "cross_bellow",
  "cond": "RSI_N_4h bellow 70",
  "shift_1": 1,
  "shift_2": 0
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"RSI_N_4h(1) bellow 70"`
**And** the number `70` MUST NOT have shift notation appended.

### SC-F9: cross_above — indicator crosses above price

**Given** a condition:
```json
{
  "cond_type": "cross_above",
  "cond": "EMA_4h above CLOSE",
  "shift_1": 1,
  "shift_2": 1
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"EMA_4h(1) above CLOSE(1)"`

### SC-F10: ind_direction — indicator direction

**Given** a condition:
```json
{
  "cond_type": "ind_direction",
  "cond": "EMA_1D upwards",
  "shift_1": 1,
  "shift_2": 0
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"EMA_1D(1) upwards"`
**And** only `shift_1` SHALL be appended (direction has a single operand).

### SC-F11: num_bars — bar count exit

**Given** a condition:
```json
{
  "cond_type": "num_bars",
  "cond": "10",
  "shift_1": 0,
  "shift_2": 0
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"Exit after 10 bars"`
**And** no shift annotation SHALL be added.

### SC-F12: cross_bellow — same indicator, different shifts

**Given** a condition:
```json
{
  "cond_type": "cross_bellow",
  "cond": "SMA_4h bellow SMA_4h",
  "shift_1": 1,
  "shift_2": 2
}
```
**When** the ConditionBlock renders the display string
**Then** it MUST display: `"SMA_4h(1) bellow SMA_4h(2)"`

---

## Negative Scenarios

### SC-F-NEG1: Must not mutate data

**Given** a condition object passed to ConditionBlock
**When** the display string is computed
**Then** the original condition object's `cond` field MUST remain unchanged after rendering.

### SC-F-NEG2: Unparseable cond string fallback

**Given** a condition with a `cond` string that does not match expected patterns (e.g., `"some unknown format"`)
**When** the ConditionBlock renders the display string
**Then** it MUST display the raw `cond` string as-is, without error.

---

## Display Format Summary

| cond_type | Display Format | Example |
|-----------|---------------|---------|
| `ind_relation` | `IND_A(shift_1) op IND_B(shift_2)` | `LOW_4h(1) < LOW_4h(2)` |
| `num_relation` | `IND(shift_1) op number` | `RSI_N_4h(2) < 30` |
| `price_relation` | `PRICE(shift_1) op IND(shift_2)` | `CLOSE(1) > EMA_1D(1)` |
| `p2p_relation` | `PRICE_1(shift_1) op PRICE_2(shift_2)` | `HIGH_4h(1) > HIGH_4h(2)` |
| `cross_above` | `IND(shift_1) above IND/num/price(shift_2)` | `MACD_macd_1h(1) above MACD_macdsignal_1h(1)` |
| `cross_bellow` | `IND(shift_1) bellow IND/num/price(shift_2)` | `RSI_N_4h(1) bellow 70` |
| `ind_direction` | `IND(shift_1) upwards/downwards` | `EMA_1D(1) upwards` |
| `num_bars` | `Exit after N bars` (no shift) | `Exit after 10 bars` |

**Note on numbers**: Plain numeric tokens (e.g., `30`, `70`, `10`) MUST NOT receive shift annotation. Only indicator names and price names receive `(shift_N)` suffixes.
