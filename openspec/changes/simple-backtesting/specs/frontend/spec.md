# Spec: backtest/frontend

**Change**: simple-backtesting
**Domain**: frontend
**Type**: FULL (new domain, no prior spec)

---

## 1. Overview

A new `BacktestPanel` React component integrates into the existing draft detail view (`DraftViewer.tsx`). It allows users to trigger backtests, monitor job progress, and view results (metrics cards and trades table). The component follows existing patterns: React Query for data fetching, Tailwind CSS for styling, Lucide React for icons, axios-based service functions.

---

## 2. Requirements

### 2.1 Service Functions

**REQ-FE-01**: A new service module `frontend/src/services/backtests.ts` MUST be created, following the pattern of `strategies.ts`. It MUST export:
- `createBacktest(params: CreateBacktestParams): Promise<BacktestJob>`
- `getBacktests(draftStratCode: number): Promise<BacktestListResponse>`
- `getBacktest(jobId: number): Promise<BacktestJobDetail>`
- `deleteBacktest(jobId: number): Promise<void>`

**REQ-FE-02**: All service functions MUST use the shared `api` axios instance from `services/api.ts`.

### 2.2 TypeScript Types

**REQ-FE-03**: Types MUST be defined in `frontend/src/types/backtest.ts`:

```typescript
interface BacktestJob {
  id: number;
  draft_strat_code: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface BacktestMetrics {
  net_pnl: number;
  win_rate: number;
  max_drawdown: number;
  sharpe_ratio: number;
  total_trades: number;
  [key: string]: number; // additional engine metrics
}

interface BacktestTrade {
  entry_date: string;
  exit_date: string;
  direction: 'long' | 'short';
  entry_price: number;
  exit_price: number;
  pnl: number;
}

interface BacktestResults {
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
}

interface BacktestJobDetail extends BacktestJob {
  results: BacktestResults | null;
}
```

### 2.3 BacktestPanel Component

**REQ-FE-04**: The `BacktestPanel` MUST be defined in `frontend/src/components/strategies/BacktestPanel.tsx`.

**REQ-FE-05**: The `BacktestPanel` MUST receive the current draft's `strat_code` as a prop. It MUST also receive a boolean `backtestable` prop indicating whether the draft meets backtesting prerequisites (strategy validated, todo_count=0).

**REQ-FE-06**: The panel MUST be integrated into `DraftViewer.tsx` as a new `SectionPanel` at the bottom of the visual sections list, with title "Backtest" and a suitable icon.

### 2.4 Trigger Form

**REQ-FE-07**: When `backtestable` is `true`, the panel MUST display a form with:
- **Symbol**: pre-filled from the draft's `data.symbol` field, editable
- **Timeframe**: dropdown select with options: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d` (default: `1h`)
- **Start Date**: date input (required)
- **End Date**: date input (required)
- **Run Backtest** button

**REQ-FE-08**: When `backtestable` is `false`, the panel MUST display a disabled state with a message explaining why backtesting is not available (e.g., "Strategy must be validated and all TODOs resolved before backtesting").

**REQ-FE-09**: The "Run Backtest" button MUST be disabled while a mutation is in progress (loading state). It SHOULD show "Running..." text during submission.

**REQ-FE-10**: Client-side validation MUST verify `start_date < end_date` before submitting. If invalid, display an inline error message without calling the API.

**REQ-FE-11**: On successful backtest creation, the panel MUST invalidate the backtests query to refresh the job list.

### 2.5 Job History List

**REQ-FE-12**: Below the trigger form, the panel MUST display a list of previous backtest jobs for the current draft, fetched via `GET /api/backtests?draft_strat_code={code}`.

**REQ-FE-13**: Each job in the list MUST show:
- Status badge with color coding: `pending` (gray), `running` (blue/animated), `completed` (green), `failed` (red)
- Date range (`start_date` -- `end_date`)
- Created timestamp (relative, e.g., "2 hours ago")
- Click action to expand/view results

**REQ-FE-14**: Jobs with `status='pending'` MUST show a delete/cancel button (calls `DELETE /api/backtests/{id}`).

### 2.6 Status Polling

**REQ-FE-15**: When any job in the list has `status='pending'` or `status='running'`, the panel MUST poll the backtests list endpoint at a 3-second interval using React Query's `refetchInterval`.

**REQ-FE-16**: Polling MUST stop when all visible jobs have terminal status (`completed` or `failed`).

**REQ-FE-17**: The running status indicator SHOULD include a subtle animation (pulse or spinner) to indicate active processing.

### 2.7 Results Display

**REQ-FE-18**: When a completed job is expanded/selected, the panel MUST display:

1. **Metrics Cards**: A grid of key metric values:
   - Net PnL (formatted as currency with +/- sign and color: green positive, red negative)
   - Win Rate (formatted as percentage, e.g., "62.0%")
   - Max Drawdown (formatted as currency, always shown as negative/red)
   - Sharpe Ratio (formatted to 2 decimal places)
   - Total Trades (integer)

2. **Trades Table** (collapsible, collapsed by default): columns for entry date, exit date, direction (Long/Short badge), entry price, exit price, PnL (color-coded).

**REQ-FE-19**: If the job has `status='failed'`, the panel MUST display the `error_message` in a red-tinted alert box instead of results.

**REQ-FE-20**: Metric values MUST use the project's existing Tailwind color tokens (`text-accent` for positive, `text-danger` for negative values).

### 2.8 Empty State

**REQ-FE-21**: If no backtest jobs exist for the draft, the panel MUST show a message like "No backtests yet. Configure parameters above and run your first backtest."

### 2.9 Error Handling

**REQ-FE-22**: API errors from the create endpoint MUST be displayed inline in the form (not as alerts/toasts). The error detail from the API response SHOULD be shown.

**REQ-FE-23**: Network errors or unexpected failures MUST show a generic "Failed to connect to server" message.

---

## 3. Acceptance Scenarios

### Scenario FE-S1: Backtestable Draft -- Form Visible

```
Given a draft with strat_code=1001, todo_count=0
And the parent strategy has status='validated'
When the DraftViewer renders with the BacktestPanel
Then the Backtest section MUST be visible
And the trigger form MUST be enabled with symbol pre-filled from draft data
And the timeframe dropdown MUST default to '1h'
And start_date and end_date inputs MUST be empty (required)
```

### Scenario FE-S2: Non-Backtestable Draft -- Disabled State

```
Given a draft with strat_code=1001, todo_count=2
When the DraftViewer renders with the BacktestPanel
Then the Backtest section MUST be visible
And the form MUST be disabled
And a message MUST explain why backtesting is unavailable
```

### Scenario FE-S3: Trigger Backtest -- Happy Path

```
Given the form is filled: symbol='ES', timeframe='1h', start_date='2025-01-01', end_date='2025-06-01'
When the user clicks "Run Backtest"
Then the button MUST show loading state ("Running...")
And a POST /api/backtests request MUST be sent
And on success, the job list MUST refresh showing the new pending job
```

### Scenario FE-S4: Trigger Backtest -- Date Validation Error

```
Given the form is filled with start_date='2025-06-01', end_date='2025-01-01'
When the user clicks "Run Backtest"
Then NO API call MUST be made
And an inline error "Start date must be before end date" MUST appear
```

### Scenario FE-S5: Polling Active Job

```
Given a backtest job with status='running' exists for the current draft
When the BacktestPanel renders
Then the job list MUST show the running job with an animated status indicator
And the panel MUST poll GET /api/backtests?draft_strat_code=1001 every 3 seconds
When the job transitions to 'completed'
Then polling MUST stop
And the results MUST become viewable
```

### Scenario FE-S6: View Completed Results

```
Given a backtest job with status='completed' and results exist
When the user clicks/expands the completed job
Then 5 metric cards MUST be displayed (PnL, Win Rate, Drawdown, Sharpe, Total Trades)
And PnL values MUST be color-coded (green positive, red negative)
And a "Show Trades" toggle MUST be available to expand the trades table
```

### Scenario FE-S7: View Failed Job

```
Given a backtest job with status='failed' and error_message='Engine timeout after 300s'
When the user clicks/expands the failed job
Then an error alert MUST display the error_message
And no metrics or trades MUST be shown
```

### Scenario FE-S8: Cancel Pending Job

```
Given a backtest job with status='pending'
When the user clicks the cancel/delete button on that job
Then DELETE /api/backtests/{id} MUST be called
And on success, the job MUST disappear from the list
```

### Scenario FE-S9: Empty State

```
Given no backtest jobs exist for draft_strat_code=1001
When the BacktestPanel renders
Then the job list area MUST show "No backtests yet" message
And the trigger form MUST still be available
```

### Scenario FE-S10: API Error on Create

```
Given the API returns 422 with detail "Draft is not backtestable..."
When the user submits the backtest form
Then the error detail MUST be displayed inline below the form
And the submit button MUST return to enabled state
```

### Scenario FE-S11: Multiple Backtests Listed

```
Given 3 backtest jobs exist for the current draft (1 completed, 1 failed, 1 pending)
When the BacktestPanel renders
Then all 3 jobs MUST appear in the list ordered by created_at DESC
And each MUST show the correct status badge color
And polling MUST be active (due to the pending job)
```
