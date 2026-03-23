# Spec: strategy-translator — Fix Condition Format

**Change**: fix-condition-format
**Domain**: strategy-translator
**Status**: draft
**Depends on**: proposal.md

## Overview

The `cond` field in translated strategy conditions MUST contain only bare indicator names. Shift notation `(N)` MUST NOT appear in `cond` strings. Shifts are exclusively expressed via the `shift_1` and `shift_2` integer fields.

This spec covers ALL condition types produced by the translator.

---

## Requirements

### REQ-T1: Bare indicator names in `cond`

The `cond` field MUST contain only bare indicator names (e.g., `"LOW_4h"`, `"RSI_N_4h"`). It MUST NOT contain shift notation such as `(0)`, `(1)`, or `(2)` appended to any token.

### REQ-T2: Shifts in dedicated fields only

Shift values MUST only be specified in the `shift_1` (left operand) and `shift_2` (right operand) integer fields. These fields are the sole mechanism for expressing temporal offset.

### REQ-T3: Applies to all condition types

Requirements REQ-T1 and REQ-T2 apply uniformly to every `cond_type`:
- `ind_relation`
- `num_relation`
- `price_relation`
- `p2p_relation`
- `cross_above`
- `cross_bellow`
- `ind_direction`
- `num_bars`

---

## Scenarios

### SC-T1: ind_relation — same indicator, different shifts

**Given** a variant rule: "current bar LOW is less than previous bar LOW on 4h"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "ind_relation",
  "cond": "LOW_4h < LOW_4h",
  "condCode": "c001",
  "shift_1": 1,
  "shift_2": 2
}
```
**And** the `cond` field MUST NOT contain `"LOW_4h(1) < LOW_4h(2)"`.

### SC-T2: ind_relation — different indicators

**Given** a variant rule: "RSI is above SMA on 1h"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "ind_relation",
  "cond": "RSI_N_1h > SMA_1h",
  "condCode": "c002",
  "shift_1": 1,
  "shift_2": 1
}
```

### SC-T3: num_relation — indicator vs number

**Given** a variant rule: "RSI on 4h is below 30, looking back 2 bars"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "num_relation",
  "cond": "RSI_N_4h < 30",
  "condCode": "c003",
  "shift_1": 2,
  "shift_2": 0
}
```
**And** the `cond` field MUST NOT contain `"RSI_N_4h(2) < 30"`.

### SC-T4: price_relation — indicator vs price

**Given** a variant rule: "CLOSE is above EMA on daily"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "price_relation",
  "cond": "CLOSE > EMA_1D",
  "condCode": "c004",
  "shift_1": 1,
  "shift_2": 1
}
```
**And** the `cond` field MUST NOT contain `"CLOSE(1) > EMA_1D(1)"`.

### SC-T5: p2p_relation — price vs price

**Given** a variant rule: "current HIGH is above previous HIGH on 4h"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "p2p_relation",
  "cond": "HIGH_4h > HIGH_4h",
  "condCode": "c005",
  "shift_1": 1,
  "shift_2": 2
}
```
**And** the `cond` field MUST NOT contain `"HIGH_4h(1) > HIGH_4h(2)"`.

### SC-T6: cross_above — indicator crosses above indicator

**Given** a variant rule: "MACD line crosses above signal line on 1h"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "cross_above",
  "cond": "MACD_macd_1h above MACD_macdsignal_1h",
  "condCode": "c006",
  "shift_1": 1,
  "shift_2": 1
}
```
**And** the `cond` field MUST NOT contain any `(N)` notation.

### SC-T7: cross_bellow — indicator crosses below number

**Given** a variant rule: "RSI crosses below 70 on 4h"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "cross_bellow",
  "cond": "RSI_N_4h bellow 70",
  "condCode": "c007",
  "shift_1": 1,
  "shift_2": 0
}
```
**And** the `cond` field MUST NOT contain `"RSI_N_4h(1) bellow 70"`.

### SC-T8: ind_direction — indicator direction

**Given** a variant rule: "EMA on daily is moving upwards"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "ind_direction",
  "cond": "EMA_1D upwards",
  "condCode": "c008",
  "shift_1": 1,
  "shift_2": 0
}
```
**And** the `cond` field MUST NOT contain `"EMA_1D(1) upwards"`.

### SC-T9: num_bars — bar count exit

**Given** a variant rule: "exit after 10 bars"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "num_bars",
  "cond": "10",
  "condCode": "c009",
  "shift_1": 0,
  "shift_2": 0
}
```
**And** the `cond` field MUST be a plain number string with no notation.

### SC-T10: cross_above — same indicator, different shifts

**Given** a variant rule: "SMA on current bar crosses above SMA on previous bar"
**When** the translator produces the condition
**Then** the output MUST be:
```json
{
  "cond_type": "cross_above",
  "cond": "SMA_4h above SMA_4h",
  "condCode": "c010",
  "shift_1": 1,
  "shift_2": 2
}
```
**And** the `cond` field MUST NOT contain `"SMA_4h(1) above SMA_4h(2)"`.

---

## Negative Scenarios

### SC-T-NEG1: Reject shift notation in cond

**Given** any condition produced by the translator
**When** the `cond` string is inspected
**Then** it MUST NOT match the regex `\(\d+\)` anywhere in the string.

### SC-T-NEG2: Existing (N) notation is the bug, not the fix

**Given** the translation-rules.md previously instructed adding `(0)` / `(1)` to disambiguate
**When** this spec is applied
**Then** that rule MUST be reversed — the bare name format is correct, the `(N)` format is the bug.

---

## Validation Rule

A post-translation validation SHOULD check that no `cond` field in the output JSON matches the pattern `\w+\(\d+\)`. If any match is found, the translator SHOULD flag it as a format error.
