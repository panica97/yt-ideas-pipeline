# Report Drawer Specification

## Purpose

Defines the behavior of the full-screen report drawer component (`BacktestReportDrawer.tsx`) that displays complete backtest results. The drawer presents extended metrics, an equity curve chart, and a scrollable trades table, providing the detailed analytical view users need to evaluate strategy viability.

## Requirements

### Requirement: Drawer Layout and Behavior

The system MUST render a full-screen drawer that slides in from the right side of the viewport. The drawer MUST occupy approximately 80% of the viewport width. The drawer MUST overlay the existing content with a semi-transparent backdrop.

The drawer MUST be closeable by:
- Clicking the X (close) button in the drawer header
- Clicking outside the drawer (on the backdrop)
- Pressing the Escape key

The drawer MUST use a slide-in animation when opening (right to left) and a slide-out animation when closing (left to right).

#### Scenario: Drawer opens on trigger

- GIVEN a completed backtest job with `mode: "complete"`
- WHEN the user clicks "View Report" on the job item
- THEN the drawer slides in from the right
- AND the backdrop appears behind the drawer
- AND the drawer occupies ~80% of the viewport width

#### Scenario: Close via X button

- GIVEN the report drawer is open
- WHEN the user clicks the X button in the drawer header
- THEN the drawer slides out to the right
- AND the backdrop disappears

#### Scenario: Close via backdrop click

- GIVEN the report drawer is open
- WHEN the user clicks on the semi-transparent backdrop (outside the drawer)
- THEN the drawer closes

#### Scenario: Close via Escape key

- GIVEN the report drawer is open
- WHEN the user presses the Escape key
- THEN the drawer closes

### Requirement: Drawer Header

The drawer header MUST display:
- The strategy code or name
- The symbol and timeframe of the backtest
- The date range (start - end)
- A close (X) button aligned to the right

#### Scenario: Header displays backtest context

- GIVEN a complete backtest for strategy 12345, symbol MNQ, timeframe 5m, dates 2024-01-01 to 2024-06-30
- WHEN the drawer opens
- THEN the header shows the strategy identifier, "MNQ", "5m", and "2024-01-01 to 2024-06-30"

### Requirement: Extended Metrics Cards

The drawer MUST display metric cards in a responsive grid layout. The following 10 metrics MUST be displayed:

| # | Metric | Source | Format |
|---|--------|--------|--------|
| 1 | Return / DD | `return_pct / max_drawdown_pct` or `total_pnl / max_drawdown` | Ratio (e.g., `2.15`) |
| 2 | Win Rate | `win_rate` | Percentage (e.g., `54.3%`) |
| 3 | Max DD % | `max_drawdown_pct` or computed from `max_drawdown / initial_equity` | Percentage (e.g., `12.5%`) |
| 4 | Sharpe | `sharpe_ratio` | Decimal (e.g., `1.85`) |
| 5 | Total Trades | `total_trades` or `trade_count` | Integer (e.g., `247`) |
| 6 | Profit Factor | `profit_factor` | Decimal (e.g., `1.42`) |
| 7 | Sortino | `sortino_ratio` | Decimal (e.g., `2.31`) |
| 8 | Avg Win / Loss | Computed from trades: `avg(winning trades PnL) / abs(avg(losing trades PnL))` | Ratio (e.g., `1.28`) |
| 9 | Max Consecutive Losses | Computed from trades: longest streak of trades with `pnl < 0` | Integer (e.g., `7`) |
| 10 | Avg Trade Duration | Computed from trades: mean of `bars_held` field | Decimal with unit (e.g., `12.3 bars`) |

Metrics with positive/favorable values SHOULD use the accent color. Metrics with negative/unfavorable values SHOULD use the danger color. Metrics that cannot be computed (missing data) MUST display "N/A".

#### Scenario: All metrics available

- GIVEN a complete backtest result with full metrics and trades data
- WHEN the drawer renders
- THEN all 10 metric cards are displayed with computed values
- AND color coding reflects favorable vs unfavorable values

#### Scenario: Avg Win/Loss computed from trades

- GIVEN trades where winning trades average +$500 and losing trades average -$300
- WHEN the drawer computes Avg Win / Loss
- THEN it displays `1.67` (500 / 300)

#### Scenario: Max Consecutive Losses computed from trades

- GIVEN trades with PnL sequence: [+100, -50, -30, -20, +80, -10, -5]
- WHEN the drawer computes Max Consecutive Losses
- THEN it displays `3` (the streak of -50, -30, -20)

#### Scenario: Avg Trade Duration computed from trades

- GIVEN trades with `bars_held` values [10, 15, 20, 5]
- WHEN the drawer computes Avg Trade Duration
- THEN it displays `12.5 bars`

#### Scenario: Missing data shows N/A

- GIVEN a backtest result where `profit_factor` is null or missing
- WHEN the drawer renders the Profit Factor card
- THEN it displays "N/A" in muted text color

### Requirement: Equity Curve Chart

The drawer MUST display an equity curve chart using recharts (LineChart). The chart plots cumulative PnL over time, derived from the trades data.

The chart MUST:
- Sort trades by `exit_date` ascending
- Compute cumulative PnL as a running sum of each trade's `pnl`
- Use exit_date as the X axis
- Use cumulative PnL as the Y axis
- Format Y axis values as currency
- Include a tooltip showing date and cumulative PnL on hover
- Use the accent color for the line when final cumulative PnL is positive, danger color when negative

The chart SHOULD have a reasonable minimum height (e.g., 300px) for readability in the full-screen drawer.

#### Scenario: Equity curve renders from trades

- GIVEN 100 trades with varying PnL values
- WHEN the drawer renders the equity curve
- THEN a line chart shows 100 data points
- AND the X axis shows trade exit dates
- AND the Y axis shows cumulative PnL in currency format

#### Scenario: Empty trades shows no chart

- GIVEN a complete backtest result with 0 trades
- WHEN the drawer renders
- THEN the equity curve section displays a message like "No trades to display"
- AND no chart is rendered

#### Scenario: Tooltip on hover

- GIVEN the equity curve is rendered
- WHEN the user hovers over a data point
- THEN a tooltip shows the exit date and cumulative PnL value

### Requirement: Trades Table

The drawer MUST display a scrollable, sortable table of all individual trades. The table MUST show the following columns:

| Column | Source Field | Format |
|--------|-------------|--------|
| # | Row index | Integer (1-based) |
| Entry Date | `entry_date` | Date/time string |
| Exit Date | `exit_date` | Date/time string |
| Direction | `direction` | "Long" / "Short" with color coding |
| Entry Price | `entry_price` | Currency |
| Exit Price | `exit_price` | Currency |
| PnL | `pnl` | Currency with +/- sign and color |
| Cumulative PnL | `cumulative_pnl` | Currency with +/- sign and color |
| Exit Reason | `exit_reason` | Text (e.g., "sl", "tp", "signal") |
| Bars Held | `bars_held` | Integer |

The table MUST:
- Be scrollable vertically with a sticky header
- Support sorting by clicking column headers (ascending/descending toggle)
- Default sort by Entry Date ascending
- Color-code the Direction column (accent for Long, danger for Short)
- Color-code PnL and Cumulative PnL columns (accent for positive, danger for negative)

The table SHOULD have a maximum height that allows scrolling within the drawer content area without the drawer itself scrolling.

#### Scenario: Trades table renders all trades

- GIVEN a complete backtest with 250 trades
- WHEN the drawer renders
- THEN the trades table shows 250 rows
- AND the header row is sticky while scrolling

#### Scenario: Sort by PnL descending

- GIVEN the trades table is displayed sorted by Entry Date
- WHEN the user clicks the "PnL" column header
- THEN trades are sorted by PnL descending (best trades first)
- WHEN the user clicks "PnL" again
- THEN trades are sorted by PnL ascending (worst trades first)

#### Scenario: Empty trades shows message

- GIVEN a complete backtest with 0 trades
- WHEN the drawer renders
- THEN the trades table section displays "No trades recorded"

### Requirement: Drawer Scroll Behavior

The drawer content (metrics, chart, table) MUST be scrollable as a single column when the content exceeds the viewport height. The drawer header MUST remain fixed at the top.

Body scroll MUST be locked when the drawer is open to prevent background content from scrolling.

#### Scenario: Content overflow scrolls within drawer

- GIVEN the drawer displays metrics, a chart, and 500 trades
- WHEN the total content exceeds the viewport height
- THEN the drawer content area scrolls vertically
- AND the drawer header stays fixed

#### Scenario: Body scroll locked

- GIVEN the drawer is open
- WHEN the user attempts to scroll the page background
- THEN the background does not scroll

### Requirement: Integration with BacktestPanel

The `BacktestPanel` component MUST show a "View Report" link/button for completed jobs that were run in `mode: "complete"`. Clicking "View Report" MUST open the `BacktestReportDrawer`.

For jobs run in `mode: "simple"`, the existing inline results view MUST remain unchanged (no "View Report" link).

#### Scenario: Complete mode job shows View Report

- GIVEN a completed backtest job with `mode: "complete"` in the job history
- WHEN the user sees the job item
- THEN a "View Report" link is visible
- AND clicking it opens the BacktestReportDrawer with that job's results

#### Scenario: Simple mode job shows inline results

- GIVEN a completed backtest job with `mode: "simple"` in the job history
- WHEN the user expands the job item
- THEN the existing inline MetricsGrid and equity curve are shown
- AND no "View Report" link is present
