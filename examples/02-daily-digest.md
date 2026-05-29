---
name: daily-digest
description: Compile a morning digest with weather, top news headlines, and calendar events for the day.
category: productivity
when_to_use:
  - User asks for a morning summary or daily briefing
  - First task of the day to get oriented
pitfalls:
  - News sites may geo-block or show paywalls — fall back to a different source
  - Weather APIs change response format; prefer scraping a reliable site
verification:
  - At least 3 news headlines are present
  - Temperature is a number with a unit
---

## Steps

1. **Weather** — Navigate to `https://weather.com/weather/today/l/{ZIP_CODE}` and extract current temperature, conditions, and today's high/low.

2. **News** — Navigate to `https://news.ycombinator.com` and extract the top 5 headlines with their point counts.

3. **Calendar** — Open Google Calendar (`https://calendar.google.com`) and list today's events (requires the user to be logged in).

4. **Compose** — Combine everything into a single markdown digest:

```markdown
# Morning Digest — {DATE}

## Weather ({CITY})
- Temp: 72 °F (High 78 / Low 65)
- Conditions: Partly Cloudy

## Top News
1. [Title](url) — 342 points
2. ...

## Today's Events
- 09:00 Standup
- 11:00 Design review
```

## Variables

- `ZIP_CODE` — ZIP code for weather lookup (default: user's location)
- `CITY` — City name for display (default: user's city)
