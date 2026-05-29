---
name: stock-checker
description: Check the current price and daily change for a given stock ticker on Yahoo Finance.
category: finance
when_to_use:
  - User asks for a stock price or market quote
  - Need to check daily performance of a ticker
pitfalls:
  - Yahoo Finance sometimes shows a "smart-summary" overlay that blocks the price — dismiss it first
  - Tickers with special characters (e.g. BRK.B) need the URL-encoded form (BRK-B)
verification:
  - The response includes a numeric price
  - The daily-change percentage is present
---

## Steps

1. Navigate to `https://finance.yahoo.com/quote/{TICKER}`.
2. Wait for the price element (CSS `[data-testid='qsp-price']`) to appear.
3. Extract:
   - Current price
   - Daily change (absolute and %)
   - Previous close
4. Return a structured summary:

```
Ticker:   AAPL
Price:    $213.25
Change:   +1.42 (+0.67%)
Prev Cl:  $211.83
```

## Variables

- `TICKER` — The stock ticker symbol (e.g. AAPL, MSFT, GOOG)
