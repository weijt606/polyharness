# Example: API Calling (Tool Selection)

A harness that routes natural-language queries to the correct API endpoint with proper parameters.

## Task

Given a query like "What's the weather in Tokyo?", select the right API endpoint from a catalog of 8 APIs and extract the correct parameters.

**20 test cases** covering: weather, product search, user profiles, email, calendar events, translation, stock prices, reminders.

## Scoring

- Correct endpoint: 0.5 points
- Correct parameters: 0.5 points (divided equally among expected params)

## Base Harness

The naive `harness.py` matches a few keywords (`weather`, `product`, `email`, `stock`) to endpoints but doesn't extract parameters properly. Falls back to `get_weather` for unrecognized queries.

**Base score: ~0.30** (gets some endpoints right but parameters are mostly wrong)

## Run

```bash
cd examples/api-calling
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5
ph log --workspace .ws
```
