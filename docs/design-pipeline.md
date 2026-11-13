# Assignment 4.1 design pipeline

The instructor prompts, three-row synthetic CSV, and Prompt 01a governance and [AI disclosure](../AI-USE.md) documents exist today. [Instructor Prompt 2](../prompts/02-connect-vue-and-fastapi.md) verified the Vue button, Vite proxy on port 5173, and FastAPI route on port 8000 in installed Chrome. Both routes returned HTTP 200 and `{"status":"healthy"}` before and after the restart. The Vite proxy returned HTTP 500 during the intentional backend outage, and Vue displayed `Backend unavailable.`. See the [verification log](verification.md) for the console and shutdown results.

Assignment 4 is cumulative. The market-data pipeline below remains planned for Part 4.1. The health check verifies local HTTP transport. Live Yahoo Finance availability, persistence, candle correctness, and WebSocket delivery require their own evidence.

```text
[Yahoo Finance live stream, AAPL]
              |
              v
[Python receiver, yfinance]
              |
              v
[Observation recorder]
              |
              v
[SQLite observations] ----> [Replay cursor over recorded observations]
              |                              |
              v                              v
          [Candle aggregation with UTC boundaries]
                             |
                             v
           [FastAPI HTTP history and WebSocket updates]
                             |
                             v
         [Vue candlestick and volume dashboard in browser]
```

| Stage | Planned behavior |
| --- | --- |
| Python receiver | Subscribe to AAPL, validate incoming fields, and capture the provider source time and backend receipt time in UTC. Preserve whether a volume field was supplied and what it represents. |
| Observation recorder and SQLite | Persist each observation before aggregation with its symbol, source, price, source and receipt timestamps, available volume information, and stable identity. Preserve arrival order and retain revisions so replay can reproduce what the receiver observed after restart. |
| Replay | Read observations in a documented stable order with a deterministic tie-breaker. Feed them through the same aggregation rules and label the output as replay. Use the stored timestamps to reconstruct candle boundaries. |
| Candle aggregation | Group by symbol and UTC interval. Derive open, high, low, and close and preserve candle revisions and completion state. Represent volume as known, unknown, or unavailable based on provider field semantics and available evidence. Keep a known zero distinct from missing volume. Report freshness and completion only when supported by observed data and the documented rules. |
| FastAPI | Serve historical snapshots over HTTP and incremental changes over WebSocket. Include source, data mode, timestamps or age, feed status, and candle-completion status in the contract. |
| Vue | Render candlesticks and volume with TradingView Lightweight Charts. Display live, synthetic sample, recorded, or replay mode and distinguish freshness and feed availability separately. Keep the last observed data clearly timestamped when the feed goes stale or becomes unavailable. |

## Verification evidence

- For a bounded live subscription check, record the symbol, start and end times in UTC, whether the connection opened, and the observed result. For a received update, capture the price, source time, receipt time, and volume availability. Verify that an observation reaches SQLite and that a corresponding update appears in the dashboard.
- If a bounded attempt times out or disconnects, capture the duration, sanitized error or close reason if available, connection state, last-update time or its absence, and the visible feed status. Record receipt as unverified until an actual update arrives. Capture recovery if the feed resumes.
- For replay, confirm the displayed data is marked as replay and compare reconstructed candles with the stored observations. For CSV practice, label the sample as synthetic. Neither replay nor a synthetic run supplies the graded live-stream evidence.
- From a clean local start, verify the frontend reaches FastAPI, that the browser reports feed state, and that a stop and restart leaves stored observations available for replay.

Decisions for later prompts include the candle interval and completion rule, stale-data threshold, volume mapping, replay order and pacing, and the local database location. The project is educational and non-advisory. Later assignment features are outside this checkpoint.
