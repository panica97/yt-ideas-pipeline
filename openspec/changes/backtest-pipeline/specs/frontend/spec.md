# Delta for Frontend

## ADDED Requirements

### Requirement: Pipeline Mode Tab

The BacktestPanel MUST include a 6th "Pipeline" mode tab alongside existing mode buttons.

#### Scenario: User selects Pipeline mode

- GIVEN the user is on a strategy's backtest panel
- WHEN they click the "Pipeline" tab
- THEN the form SHALL show shared params (symbol, timeframe, dates)
- AND collapsible sections for Monte Carlo params (n_paths, fit_years)
- AND collapsible sections for Monkey Test params (n_simulations, monkey_mode)
- AND collapsible sections for Stress Test params (test_name, param_overrides, single_overrides, max_parallel)

#### Scenario: User submits pipeline

- GIVEN all required fields are filled
- WHEN the user clicks "Run Pipeline"
- THEN the frontend SHALL generate a UUID v4 for pipeline_group
- AND send a POST request with mode="complete", pipeline_group, and pipeline_config containing all mode-specific params

#### Scenario: Pipeline form validation

- GIVEN the Pipeline tab is active
- WHEN the user submits with missing required fields
- THEN validation errors SHALL be shown for each missing field
- AND the request SHALL NOT be sent

### Requirement: Pipeline Status Row

Pipeline jobs in the job history MUST be displayed as a single compact row grouped by pipeline_group.

#### Scenario: Pipeline in progress

- GIVEN a pipeline with backtest completed, MC running, Monkey completed, Stress running
- WHEN the job list renders
- THEN it SHALL show one row: "Pipeline: Backtest checkmark . MC spinner . Monkey checkmark . Stress spinner"

#### Scenario: Pipeline completed

- GIVEN all 4 jobs completed
- WHEN the job list renders
- THEN the row SHALL show all checkmarks and a green overall status

#### Scenario: Pipeline failed

- GIVEN one job failed
- WHEN the job list renders
- THEN the row SHALL show which step failed with a red indicator

#### Scenario: Individual jobs hidden from main list

- GIVEN jobs belong to a pipeline_group
- WHEN the job list renders
- THEN individual pipeline jobs SHALL NOT appear as separate rows
- AND SHALL only appear as the grouped pipeline status row

### Requirement: Pipeline Report Drawer

Clicking a completed pipeline row MUST open a dedicated Pipeline Report drawer.

#### Scenario: View pipeline report

- GIVEN a completed pipeline
- WHEN the user clicks the pipeline status row
- THEN a drawer SHALL open showing a scrollable single view
- AND it SHALL contain a summary section at the top
- AND sections for Backtest results, MC results, Monkey results, Stress results
- AND each section SHALL reuse existing result components

#### Scenario: Pipeline report with failed step

- GIVEN a failed pipeline
- WHEN the user clicks the pipeline status row
- THEN the drawer SHALL show results for completed steps
- AND an error message for the failed step
