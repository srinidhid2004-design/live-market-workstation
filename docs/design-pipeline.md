# Assignment 4.1 design pipeline

The instructor prompts, three-row synthetic CSV, and Prompt 01a governance and [AI disclosure](../AI-USE.md) documents exist today. [Instructor Prompt 2](../prompts/02-connect-vue-and-fastapi.md) verified the Vue button, Vite proxy on port 5173, and FastAPI route on port 8000 in installed Chrome. Both routes returned HTTP 200 and `{"status":"healthy"}` before and after the restart. The Vite proxy returned HTTP 500 during the intentional backend outage, and Vue displayed `Backend unavailable.`. See the [verification log](verification.md) for the console and shutdown results.

Prompt 3 adds a separate synthetic practice path. The instructor fixture at `prompts/data/sample-candles.csv` is copied byte for byte to `backend/data/sample-candles.csv`. The standard-library CSV loader validates the exact header and row width, normalizes UTC timestamps to `Z`, checks finite prices, OHLC bounds and nonnegative integer volume, rejects duplicate minutes, and sorts by timestamp. FastAPI serves only the six candle fields at `GET /api/history` and returns a generic HTTP 500 if the file is unreadable or invalid. Each row represents one UTC minute for one instrument. Its timestamp is inclusive, and the next minute's start is excluded.

The Prompt 3 HTTP check returned three ordered candles. Each field matched the instructor fixture, and the health route still returned HTTP 200 with its exact body.

Prompt 4 adds a Vue chart for the synthetic practice path. The component fetches `/api/history` through Vite and converts each ISO UTC timestamp to Unix seconds for both Lightweight Charts series. The price candlesticks and volume histogram share a time scale in two stacked panes. The crosshair and keyboard-accessible selector both update the selected candle's UTC date, time, OHLC values, and volume. The panel labels the source as a synthetic one-minute sample and includes the TradingView attribution.

Prompt 05 installed and verified yfinance 1.8.0 and websockets 17.4 for the credential-free Python subscription. The restricted project shell failed to resolve `streamer.finance.yahoo.com` with Windows error 11001. The separate normal-PowerShell probe resolved DNS, opened the WebSocket, and subscribed only to AAPL. It reached its 25-second bound without a qualifying update, so price, source time, receipt time, and volume remain unobserved. The chart continues to use the synthetic CSV. The live Part 4.1 pipeline below remains planned, and final Assignment 4.1 evidence requires another receipt check during active market conditions. See the [bounded check evidence](verification.md#prompt-05---bounded-aapl-check).

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
| Observation recorder and SQLite | Prompt 06 implements a recorder and decoded Yahoo message adapter. Constructed observations verified persistence and ordering across a process restart. The live receiver can pass each decoded message and its UTC receipt time to `record_yahoo_message`. |
| Replay | Read observations in a documented stable order with a deterministic tie-breaker. Feed them through the same aggregation rules and label the output as replay. Use the stored timestamps to reconstruct candle boundaries. |
| Candle aggregation | Prompt 07 forms one-minute UTC candles from current saved observations for one source and ticker. Completion is evaluated separately. The HTTP and WebSocket delivery of recorded candles remains planned. |
| FastAPI | Serve historical snapshots over HTTP and incremental changes over WebSocket. Include source, data mode, timestamps or age, feed status, and candle-completion status in the contract. |
| Vue | Render candlesticks and volume with TradingView Lightweight Charts. Display live, synthetic sample, recorded, or replay mode and distinguish freshness and feed availability separately. Keep the last observed data clearly timestamped when the feed goes stale or becomes unavailable. |

## Verification evidence

- For a bounded live subscription check, record the symbol, start and end times in UTC, whether the connection opened, and the observed result. For a received update, capture the price, source time, receipt time, and volume availability. Verify that an observation reaches SQLite and that a corresponding update appears in the dashboard.
- If a bounded attempt times out or disconnects, capture the duration, sanitized error or close reason if available, connection state, last-update time or its absence, and the visible feed status. Record receipt as unverified until an actual update arrives. Capture recovery if the feed resumes.
- For replay, confirm the displayed data is marked as replay and compare reconstructed candles with the stored observations. For CSV practice, label the sample as synthetic. Neither replay nor a synthetic run supplies the graded live-stream evidence.
- From a clean local start, verify the frontend reaches FastAPI, that the browser reports feed state, and that a stop and restart leaves stored observations available for replay.

Decisions for later prompts include the stale-data threshold, live provider volume mapping, and replay order and pacing. The project is educational and non-advisory. Later assignment features are outside this checkpoint.

## Prompt 06 observation identity and revisions

The receiver hands the recorder a normalized observation and selected decoded source fields for audit. It submits observations in arrival order and captures receipt time in UTC at the receiver boundary. The SQLite recorder preserves the original integer Unix source timestamp and its unit (`s`, `ms`, or `us`) and computes a UTC timestamp without floating-point conversion. It preserves provider volume field names and values as supplied, with missing fields left absent. A value alone does not establish the meaning of a volume field. Source evidence is limited to JSON market fields selected by the receiver. It excludes credentials and transport metadata.

The Yahoo adapter handles the decoded `PricingData` field names in the pinned yfinance release. It keeps source fields in an explicit allowlist, stores `day_volume`, `last_size`, `vol_24hr`, and `vol_all_currencies` separately as supplied, and interprets `time` as Unix milliseconds as in the Prompt 05 probe. The adapter was exercised with constructed messages. Live source timestamp and volume semantics remain unverified. The database opens on demand, enables foreign keys on each connection, and serializes initialization and writes with explicit SQLite transactions. The existing CSV route stays independent of the recorder.

- SQLite assigns each stored version an immutable, increasing `observation_id`. The ID also serves as deterministic receipt order for accepted versions. The recorder does not reorder writes by timestamps. Source-time reads sort by normalized UTC and then by ID. The backend receipt clock value is retained separately.
- A SHA-256 fingerprint covers the canonical JSON of source name, ticker, original timestamp and unit, normalized numeric price, source volume fields, selected source fields, and the optional verified source event ID. Canonical JSON sorts object keys, removes insignificant formatting, and preserves array order and source-field value types. Backend receipt time and database-generated fields are excluded. A matching fingerprint returns the original ID without adding a row or changing its receipt time. A return to earlier values can create a distinct version when source evidence identifies a distinct correction, such as a provider revision sequence in the selected source fields.
- Only pass `verified_event_id` when source evidence shows that the same ID identifies the same correctable event. Its scope is source name and ticker. The recorder links new content for that ID to its latest stored version. A ticker and timestamp alone are insufficient, and uncertain provider identifiers can be kept in the selected source fields without setting `verified_event_id`. No Yahoo event ID has been verified in this project.
- Historical reads return every unique stored version, including earlier revisions. Exact repeats have no separate row. Current reads omit a row only when a stored revision points to it, so the latest stored version in each verified chain and every independent observation remain visible. Late independent observations remain available in both receipt order and source-time order.

## Prompt 07 observation-to-candle flow

The aggregator reads `ObservationStore.read(current_only=True, order="source")` once, selects a source and ticker, and groups that snapshot into half-open UTC minutes. SQLite orders equal source times by `observation_id`, the immutable receipt sequence. Open and close use the first and last prices in that order. High and low use all prices in the minute. The recorder excludes exact repeats and keeps ambiguous same-time observations independent. Only verified revision links replace a historical version in this calculation. Historical reads still expose all stored versions.

Each call rebuilds the source and ticker's candles from the current snapshot. A late observation or a correction can change OHLCV for a completed minute. A correction that moves an observation can affect both its old and new minute. A changed cumulative value can also affect a later minute that uses it as a baseline. The caller's explicit UTC evaluation time controls only `is_complete`, which becomes true at the next minute boundary. No candle is emitted for a minute without observations.

The caller identifies a verified cumulative field. The instructor fixture identifies `day_volume` as a cumulative session total for constructed data. Totals accept nonnegative integers and decimal digit strings, and are checked in source-time order starting with the most recent valid pre-minute baseline. Every row in the target minute needs a valid total and the observed sequence must be nondecreasing. Volume is the final total minus the baseline. Missing evidence or a decrease yields `None` (JSON `null`). The latest valid total can serve as the next baseline. The calculation never substitutes a `last_size` value or sums cumulative totals. Unknown live provider semantics leave the cumulative field unset.
