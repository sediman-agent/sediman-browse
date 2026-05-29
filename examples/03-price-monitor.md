---
name: price-monitor
description: Monitor a product page for price changes and record the result over time.
category: shopping
when_to_use:
  - User wants to track the price of a product
  - Scheduled cron job for periodic price checks
pitfalls:
  - Some e-commerce sites load prices via JavaScript — wait for the element
  - Currency symbols vary by locale; normalise to a plain number for comparison
  - Product pages may redirect to a variant selector — confirm the SKU
verification:
  - Price is a positive number
  - Timestamp is recorded in ISO 8601
---

## Steps

1. Navigate to the product URL provided in `{PRODUCT_URL}`.
2. Wait for the price element to render.
3. Extract the current price and product title.
4. Return a structured result:

```json
{
  "product": "Sony WH-1000XM5",
  "price": 278.00,
  "currency": "USD",
  "url": "https://www.amazon.com/dp/B09XS7JWHH",
  "checked_at": "2025-05-29T08:00:00Z"
}
```

## Variables

- `PRODUCT_URL` — Full URL of the product page to monitor

---

## Cron Setup

Schedule this skill to run on a recurring basis via the API:

```bash
# Every weekday at 9 AM
curl -X POST http://localhost:8000/api/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "cron": "0 9 * * 1-5",
    "task": "Check the price of the product at '"$PRODUCT_URL"' and report back",
    "skill": "price-monitor"
  }'
```

Or via the CLI:

```bash
# First save the skill, then schedule it
sediman schedule add "0 9 * * 1-5" --skill price-monitor --task "Check price for $PRODUCT_URL"
```

### Cron Field Reference

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

| Schedule              | Expression     |
|-----------------------|----------------|
| Every hour            | `0 * * * *`    |
| Every 6 hours         | `0 */6 * * *`  |
| Weekdays 9 AM         | `0 9 * * 1-5`  |
| Twice daily           | `0 8,18 * * *` |
| Monday morning        | `0 8 * * 1`    |
