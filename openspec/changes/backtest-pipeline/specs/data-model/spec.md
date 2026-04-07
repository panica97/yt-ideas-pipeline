# Delta for Data Model

## ADDED Requirements

### Requirement: Pipeline Group Column

The `backtest_jobs` table MUST include a nullable `pipeline_group` column of type UUID that links jobs belonging to the same pipeline run.

#### Scenario: Job created without pipeline

- GIVEN a user creates a standard backtest (any mode)
- WHEN the job is inserted into `backtest_jobs`
- THEN `pipeline_group` SHALL be NULL

#### Scenario: Job created as part of pipeline

- GIVEN a user launches a pipeline run
- WHEN the initial backtest job is created
- THEN `pipeline_group` SHALL contain a valid UUID v4

#### Scenario: Child jobs inherit pipeline group

- GIVEN a pipeline's initial backtest has completed
- WHEN the API creates child jobs (MC, Monkey, Stress)
- THEN each child job MUST have the same `pipeline_group` as the parent

### Requirement: Pipeline Config Column

The `backtest_jobs` table MUST include a nullable `pipeline_config` column of type JSONB that stores configuration for child jobs.

#### Scenario: Config stored on parent job only

- GIVEN a pipeline run is initiated
- WHEN the initial backtest job is created
- THEN `pipeline_config` SHALL contain a JSONB object with keys: `montecarlo`, `monkey`, `stress`
- AND each key SHALL contain the mode-specific parameters

#### Scenario: Child jobs have no pipeline config

- GIVEN child jobs are created from a pipeline
- WHEN inserted into `backtest_jobs`
- THEN `pipeline_config` SHALL be NULL (params are copied to individual job fields)

### Requirement: Alembic Migration

An Alembic migration MUST add both columns as nullable with no default, requiring no data transformation of existing rows.

#### Scenario: Migration on existing data

- GIVEN the `backtest_jobs` table has existing rows
- WHEN the migration runs
- THEN all existing rows SHALL have NULL for both new columns
- AND no data loss SHALL occur
