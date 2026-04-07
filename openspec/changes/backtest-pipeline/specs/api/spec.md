# Delta for API

## ADDED Requirements

### Requirement: Pipeline Job Creation

The `POST /api/backtests` endpoint MUST accept optional `pipeline_group` (UUID) and `pipeline_config` (JSONB) fields.

#### Scenario: Create pipeline parent job

- GIVEN a request with mode="complete", pipeline_group=UUID, pipeline_config={montecarlo:{...}, monkey:{...}, stress:{...}}
- WHEN the endpoint processes the request
- THEN it SHALL create one backtest job with the pipeline_group and pipeline_config stored
- AND return 201 with the job response including pipeline_group

#### Scenario: Create standard job (no pipeline)

- GIVEN a request without pipeline_group
- WHEN the endpoint processes the request
- THEN it SHALL create the job as before with pipeline_group=NULL

### Requirement: Pipeline Orchestration on Results

When backtest results are submitted via `POST /api/backtests/{id}/results`, the API service MUST check if the completed job has a `pipeline_group` AND `pipeline_config`. If yes, it MUST auto-create 3 child jobs.

#### Scenario: Backtest completes with pipeline config

- GIVEN a completed job with pipeline_group=UUID and pipeline_config containing MC, Monkey, Stress params
- WHEN results are submitted
- THEN the service SHALL create 3 new jobs:
  - mode="montecarlo" with params from pipeline_config.montecarlo
  - mode="monkey" with params from pipeline_config.monkey
  - mode="stress" with params from pipeline_config.stress
- AND all 3 jobs SHALL share the same pipeline_group
- AND all 3 jobs SHALL inherit symbol, timeframe, start_date, end_date from the parent

#### Scenario: Backtest completes without pipeline

- GIVEN a completed job with pipeline_group=NULL
- WHEN results are submitted
- THEN no additional jobs SHALL be created

#### Scenario: Backtest fails with pipeline config

- GIVEN a job with pipeline_group and pipeline_config that fails
- WHEN failure is reported via PATCH /api/backtests/{id}/fail
- THEN no child jobs SHALL be created
- AND the pipeline is considered failed

### Requirement: Pipeline Status Endpoint

A `GET /api/backtests/pipeline/{group_id}` endpoint MUST return all jobs belonging to the pipeline.

#### Scenario: Fetch pipeline jobs

- GIVEN a valid pipeline_group UUID with 4 associated jobs
- WHEN the endpoint is called
- THEN it SHALL return all 4 jobs with their current statuses

#### Scenario: Invalid pipeline group

- GIVEN a UUID that matches no jobs
- WHEN the endpoint is called
- THEN it SHALL return an empty list

### Requirement: Pipeline Status Derivation

The pipeline status MUST be derived from child job statuses.

#### Scenario: All jobs completed

- GIVEN all 4 jobs in a pipeline have status="completed"
- WHEN pipeline status is derived
- THEN overall status SHALL be "completed"

#### Scenario: Any job failed

- GIVEN 1 job has status="failed" and others are "completed"
- WHEN pipeline status is derived
- THEN overall status SHALL be "failed"

#### Scenario: Jobs still running

- GIVEN some jobs are "running" or "pending" and none have failed
- WHEN pipeline status is derived
- THEN overall status SHALL be "running"

### Requirement: Pipeline Failure Propagation

When any child job in a pipeline fails, the remaining running/pending child jobs SHOULD be cancelled.

#### Scenario: MC fails while Monkey and Stress are running

- GIVEN MC job fails
- WHEN the failure is reported
- THEN Monkey and Stress jobs SHOULD be marked as "failed" with error_message="Pipeline cancelled: montecarlo failed"
