# Dashboard P/L Updates - Implementation Summary

## Changes Made

### 1. **Dashboard HTML Updates** (`app/routes/dashboard.py`)

#### Table Header Updated
- Changed from: `Symbol | Position | Last Price | Realized | Unrealized | Cumulative`
- Changed to: `Symbol | Position (Outstanding) | Last Price | Realized P/L | Unrealized P/L | Cumulative P/L`
- More descriptive column headers with "P/L" notation for clarity

#### JavaScript Formatting Functions Added
- `formatCurrency(v)`: Converts numbers to currency format with $ and 2 decimal places
  - Returns "-" for null/undefined values
  - Example: 115.0 becomes "$115.00"

- `formatCurrencyClass(v)`: Returns CSS class for color coding
  - "positive" class (green) for values >= 0
  - "negative" class (red) for values < 0

#### Daily P/L Display
- Now shows formatted currency with color coding
- Updates when refresh is clicked
- Example: "$40.00" in green for positive P/L

#### Ticker Table Rendering
- Each ticker row now displays:
  - **Symbol**: Ticker symbol (AAPL, MSFT, etc.)
  - **Position**: Number of shares held (outstanding position)
  - **Last Price**: Last trade price formatted as currency
  - **Realized P/L**: Locked-in profit/loss in green/red
  - **Unrealized P/L**: Paper profit/loss based on current price
  - **Cumulative P/L**: Realized + Unrealized total P/L

### 2. **Database Query Fixes** (`app/services/pnl.py`)

Fixed three query issues where status filtering was too strict:

#### Problem
- Trades saved with status: `"Filled | reason: Fill X@Y"`
- Queries were looking for exact match: `Trade.status == 'Filled'`
- Result: No trades matched, P/L calculations returned empty

#### Solution
- Changed to use pattern matching: `Trade.status.like('Filled%')`
- Updated in three functions:
  1. `compute_pnl_by_ticker()` - Main P/L calculation per symbol
  2. `compute_daily_realized_pnl()` - Daily P/L aggregation
  3. `compute_trade_pnls()` - Per-trade P/L details

### 3. **P/L Calculation Logic** (No Changes - Already Implemented)

The system correctly calculates:

#### **Realized P/L**
- Uses FIFO (First In, First Out) matching
- For each SELL, matches against oldest BUY lots
- P/L = (Sell Price - Buy Price) × Quantity
- Only counted after trades are completed

#### **Unrealized P/L**
- Calculated for open positions
- Formula: (Current Price - Average Cost) × Position Size
- Updates as new trades are added
- Reflects current market value changes

#### **Cumulative P/L**
- Total of Realized + Unrealized P/L
- Represents total profit/loss including open positions
- Color coded: Green for gains, Red for losses

## Features Implemented

✅ **Per-Symbol P/L Tracking**
- Each ticker shows its own realized and unrealized P/L
- Independent calculation using FIFO method
- Handles both long and short positions

✅ **Real-Time Updates on Refresh**
- Click "Refresh" button to update all P/L values
- Fetches latest data from database
- Recalculates based on most recent trade prices

✅ **Currency Formatting**
- All P/L values display with $ symbol
- Two decimal place precision
- Easy to read format

✅ **Color Coding**
- **Green**: Positive P/L (profit)
- **Red**: Negative P/L (loss)
- Applied to:
  - Realized P/L column
  - Unrealized P/L column
  - Cumulative P/L column
  - Daily P/L display

✅ **Outstanding Position Tracking**
- Shows current position size for each symbol
- Updates as new trades are added
- Includes both long and short positions

## Example Dashboard Output

```
Daily realized PnL: $40.00 (Green)

Tickers - Position Summary with P/L
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Symbol | Position | Last Price | Realized P/L | Unrealized P/L | Cumulative P/L
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AAPL   | 17       | $155.00    | $40.00 ✓     | $75.00 ✓       | $115.00 ✓
MSFT   | 20       | $300.00    | $0.00        | $0.00          | $0.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ = Green color for positive values
✗ = Red color for negative values
```

## How to Use

1. **View P/L**: Dashboard automatically shows P/L for all positions with outstanding quantities
2. **Refresh Data**: Click "Refresh" button to update P/L calculations based on latest data
3. **Track Positions**: See both realized profits from closed trades and unrealized gains/losses from open positions
4. **Monitor Daily**: Daily realized P/L shown at top of Tickers section

## Technical Details

### API Response Structure (`/dashboard/api/pnl`)

```json
{
  "daily_realized": 40.0,
  "tickers": [
    {
      "symbol": "AAPL",
      "position": 17,
      "realized": 40.0,
      "unrealized": 75.0,
      "cumulative": 115.0,
      "last_price": 155.0
    }
  ],
  "trades": [...]
}
```

### Files Modified

1. **app/routes/dashboard.py**
   - Updated table headers
   - Added `formatCurrency()` function
   - Added `formatCurrencyClass()` function
   - Updated `fetchPnl()` to format and render P/L values

2. **app/services/pnl.py**
   - Fixed 3 query filters: `Trade.status == 'Filled'` → `Trade.status.like('Filled%')`
   - Affects: `compute_pnl_by_ticker()`, `compute_daily_realized_pnl()`, `compute_trade_pnls()`

## Testing

All functionality has been tested and verified:
- ✅ P/L calculations are accurate
- ✅ Currency formatting displays correctly
- ✅ Color coding works for positive/negative values
- ✅ Dashboard updates when refresh is clicked
- ✅ Outstanding positions are tracked correctly
- ✅ Both realized and unrealized P/L calculated using FIFO method
