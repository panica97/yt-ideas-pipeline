# Spec: backtest/data-model

**Change**: simple-backtesting
**Domain**: data-model
**Type**: FULL (new domain, no prior spec)

---

## 1. Overview

Two new PostgreSQL tables (`backtest_jobs`, `backtest_results`) provide the persistence layer for the backtesting feature. They form a job-queue pattern where `backtest_jobs` tracks lifecycle state and `backtest_results` stores engine output. Both tables are created via Alembic migration `007_add_backtesting.py`.

---

## 2. Requirements

### 2.1 backtest_jobs Table

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | `SERIAL` | `PRIMARY KEY` | Auto-incrementing job identifier |
| `draft_strat_code` | `INTEGER` | `NOT NULL`, `REFERENCES drafts(strat_code)` | FK to the draft being backtested |
| `symbol` | `VARCHAR(20)` | `NOT NULL` | Trading symbol (e.g., "ES", "NQ") |
| `timeframe` | `VARCHAR(10)` | `NOT NULL` | Bar timeframe (e.g., "1h", "15m", "1d") |
| `start_date` | `DATE` | `NOT NULL` | Backtest period start |
| `end_date` | `DATE` | `NOT NULL` | Backtest period end |
| `status` | `VARCHAR(20)` | `NOT NULL`, `DEFAULT 'pending'` | One of: `pending`, `running`, `completed`, `failed` |
| `error_message` | `TEXT` | `NULLABLE` | Error details when `status = 'failed'` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()` | Job creation timestamp |
| `started_at` | `TIMESTAMPTZ` | `NULLABLE` | When worker claimed the job |
| `completed_at` | `TIMESTAMPTZ` | `NULLABLE` | When job finished (success or failure) |

**REQ-DM-01**: The `status` column MUST only contain values from the set `{pending, running, completed, failed}`. This SHOULD be enforced via a `CHECK` constraint.

**REQ-DM-02**: `draft_strat_code` MUST reference `drafts.strat_code`. If the referenced draft is deleted, the backtest job rows MUST remain (no cascade delete) -- use `ON DELETE SET NULL` or reject deletion at the API layer.

**REQ-DM-03**: `start_date` MUST be strictly before `end_date`. This MUST be enforced via a `CHECK` constraint: `CHECK (start_date < end_date)`.

**REQ-DM-04**: `error_message` MUST be `NULL` when `status` is not `failed`. It SHOULD be populated when `status = 'failed'`.

**REQ-DM-05**: An index MUST exist on `(status, created_at)` to support the worker polling query pattern (`WHERE status = 'pending' ORDER BY created_at`).

### 2.2 backtest_results Table

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | `SERIAL` | `PRIMARY KEY` | Auto-incrementing result identifier |
| `job_id` | `INTEGER` | `NOT NULL`, `UNIQUE`, `REFERENCES backtest_jobs(id) ON DELETE CASCADE` | One-to-one with job |
| `metrics` | `JSONB` | `NOT NULL` | Engine output: net_pnl, win_rate, max_drawdown, sharpe, total_trades, etc. |
| `trades` | `JSONB` | `NOT NULL`, `DEFAULT '[]'::jsonb` | Array of individual trade records |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()` | When results were stored |

**REQ-DM-06**: `job_id` MUST have a `UNIQUE` constraint, enforcing a one-to-one relationship between jobs and results.

**REQ-DM-07**: When a `backtest_jobs` row is deleted, the corresponding `backtest_results` row MUST be cascade-deleted.

**REQ-DM-08**: The `metrics` JSONB MUST contain at minimum the keys: `net_pnl` (float), `win_rate` (float 0-1), `max_drawdown` (float), `sharpe_ratio` (float), `total_trades` (int). Additional keys from the engine output MAY be stored.

**REQ-DM-09**: The `trades` JSONB MUST be a JSON array. Each element SHOULD contain at minimum: `entry_date`, `exit_date`, `direction` (long/short), `entry_price`, `exit_price`, `pnl`.

### 2.3 Relationships

**REQ-DM-10**: Multiple `backtest_jobs` MAY exist for the same `draft_strat_code` (a user can backtest the same draft multiple times with different parameters).

**REQ-DM-11**: The relationship chain is: `strategies` -> `drafts` -> `backtest_jobs` -> `backtest_results` (one-to-many -> one-to-many -> one-to-one).

### 2.4 SQLAlchemy Models

**REQ-DM-12**: Models MUST be defined in `api/models/backtest.py` using SQLAlchemy 2.0 declarative style, consistent with existing models.

**REQ-DM-13**: Pydantic v2 schemas MUST be defined in `api/models/schemas/backtest.py` with `ConfigDict(from_attributes=True)`, consistent with existing schemas (e.g., `draft.py`, `strategy.py`).

### 2.5 Migration

**REQ-DM-14**: The Alembic migration MUST be numbered `007` and follow the existing pattern (see `006_add_instruments_table.py`). It MUST create both tables in `upgrade()` and drop both in `downgrade()`.

**REQ-DM-15**: `downgrade()` MUST drop `backtest_results` before `backtest_jobs` to respect the foreign key dependency.

---

## 3. Acceptance Scenarios

### Scenario DM-S1: Tables Created Successfully

```
Given the database has migrations through 006 applied
When `alembic upgrade head` is executed
Then the `backtest_jobs` table MUST exist with all specified columns and constraints
And the `backtest_results` table MUST exist with all specified columns and constraints
And the CHECK constraint on `status` MUST reject values outside {pending, running, completed, failed}
And the CHECK constraint on dates MUST reject start_date >= end_date
```

### Scenario DM-S2: Foreign Key to Drafts

```
Given a draft with strat_code=1001 exists in the `drafts` table
When a backtest_job is inserted with draft_strat_code=1001
Then the insert MUST succeed
And querying the job MUST allow joining to the draft row
```

### Scenario DM-S3: Foreign Key Violation

```
Given no draft with strat_code=9999 exists
When a backtest_job is inserted with draft_strat_code=9999
Then the insert MUST fail with a foreign key violation error
```

### Scenario DM-S4: One-to-One Results Constraint

```
Given a backtest_job with id=1 exists
And a backtest_result with job_id=1 already exists
When a second backtest_result is inserted with job_id=1
Then the insert MUST fail with a unique constraint violation
```

### Scenario DM-S5: Cascade Delete

```
Given a backtest_job with id=1 and its associated backtest_result exist
When the backtest_job row with id=1 is deleted
Then the associated backtest_result row MUST also be deleted
```

### Scenario DM-S6: Date Validation

```
Given valid job data with start_date='2025-01-15' and end_date='2025-01-10'
When the job is inserted
Then the insert MUST fail due to the CHECK constraint (start_date < end_date)
```

### Scenario DM-S7: Migration Rollback

```
Given migration 007 has been applied
When `alembic downgrade 006` is executed
Then the `backtest_results` table MUST be dropped first
And the `backtest_jobs` table MUST be dropped second
And no residual constraints or indexes remain
```

### Scenario DM-S8: Multiple Backtests Per Draft

```
Given a draft with strat_code=1001 exists
When two backtest_jobs are inserted for draft_strat_code=1001 with different date ranges
Then both inserts MUST succeed
And querying backtest_jobs WHERE draft_strat_code=1001 MUST return 2 rows
```
