# Assignment 4.1 design pipeline

The instructor prompts, three-row synthetic CSV, and Prompt 01a governance and [AI disclosure](../AI-USE.md) documents exist today. [Instructor Prompt 2](../prompts/02-connect-vue-and-fastapi.md) verified the Vue button, Vite proxy on port 5173, and FastAPI route on port 8000 in installed Chrome. Both routes returned HTTP 200 and `{"status":"healthy"}` before and after the restart. The Vite proxy returned HTTP 500 during the intentional backend outage, and Vue displayed `Backend unavailable.`. See the [verification log](verification.md) for the console and shutdown results.

Prompt 3 adds a separate synthetic practice path. The instructor fixture at `prompts/data/sample-candles.csv` is copied byte for byte to `backend/data/sample-candles.csv`. The standard-library CSV loader validates the exact header and row width, normalizes UTC timestamps to `Z`, checks finite prices, OHLC bounds and nonnegative integer volume, rejects duplicate minutes, and sorts by timestamp. FastAPI returns a generic HTTP 500 if the file is unreadable or invalid. Each row represents one UTC minute for one instrument. Its timestamp is inclusive, and the next minute's start is excluded.

The Prompt 3 HTTP check returned three ordered candles. Each field matched the instructor fixture, and the health route still returned HTTP 200 with its exact body.

Prompt 4 adds a Vue chart for the synthetic practice path. The component fetches `/api/history` through Vite and converts each ISO UTC timestamp to Unix seconds for both Lightweight Charts series. The price candlesticks and volume histogram share a time scale in two stacked panes. The crosshair and keyboard-accessible selector both update the selected candle's UTC date, time, OHLC values, and volume. The panel labels the source as a synthetic one-minute sample and includes the TradingView attribution.

Prompt 05 installed and verified yfinance 1.8.0 and websockets 17.4 for the credential-free Python subscription. The restricted project shell failed to resolve `streamer.finance.yahoo.com` with Windows error 11001. The separate normal-PowerShell probe resolved DNS, opened the WebSocket, and subscribed only to AAPL. It reached its 25-second bound without a qualifying update, so price, source time, receipt time, and volume remain unobserved. Prompt 08 implements the observation-to-chart path and keeps the synthetic CSV as the default source. Final Assignment 4.1 evidence requires a receipt check during active market conditions. See the [bounded check evidence](verification.md#prompt-05---bounded-aapl-check).

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

| Stage | Behavior |
| --- | --- |
| Python receiver | The opt-in Yahoo source subscribes once to AAPL, captures UTC receipt time on frame receipt, and passes the decoded market fields to the existing normalizer. |
| Observation recorder and SQLite | The coordinator commits each accepted observation before recomputing candles. The recorder preserves identity, revisions, source and receipt order, and supplied volume fields. |
| Replay | A later checkpoint will add a cursor over saved observations and reconstruct candles using the same aggregation rules. |
| Candle aggregation | Prompt 07 forms one-minute UTC candles from saved observations. Prompt 07A derives regular-session timeframes from a one-minute snapshot. Prompt 08 shares that path between provider-backed history and WebSocket updates. |
| FastAPI | Serve historical snapshots over HTTP and incremental changes over WebSocket. Include source, data mode, timestamps or age, feed status, and candle-completion status in the contract. |
| Vue | Render candlesticks and volume with TradingView Lightweight Charts. Display live, synthetic sample, recorded, or replay mode and distinguish freshness and feed availability separately. Keep the last observed data clearly timestamped when the feed goes stale or becomes unavailable. |

## Verification evidence

- For a bounded live subscription check, record the symbol, start and end times in UTC, whether the connection opened, and the observed result. For a received update, capture the price, source time, receipt time, and volume availability. Verify that an observation reaches SQLite and that a corresponding update appears in the dashboard.
- If a bounded attempt times out or disconnects, capture the duration, sanitized error or close reason if available, connection state, last-update time or its absence, and the visible feed status. Record receipt as unverified until an actual update arrives. Capture recovery if the feed resumes.
- For replay, confirm the displayed data is marked as replay and compare reconstructed candles with the stored observations. For CSV practice, label the sample as synthetic. Neither replay nor a synthetic run supplies the graded live-stream evidence.
- From a clean local start, verify the frontend reaches FastAPI, that the browser reports feed state, and that a stop and restart leaves stored observations available for replay.

Decisions for later prompts include live provider volume mapping and replay order and pacing. The project is educational and non-advisory.

## Prompt 06 observation identity and revisions

The receiver hands the recorder a normalized observation and selected decoded source fields for audit. It submits observations in arrival order and captures receipt time in UTC at the receiver boundary. The SQLite recorder preserves the original integer Unix source timestamp and its unit (`s`, `ms`, or `us`) and computes a UTC timestamp without floating-point conversion. It preserves provider volume field names and values as supplied, with missing fields left absent. A value alone does not establish the meaning of a volume field. Source evidence is limited to JSON market fields selected by the receiver. It excludes credentials and transport metadata.

The Yahoo adapter handles the decoded `PricingData` field names in the pinned yfinance release. It keeps source fields in an explicit allowlist, stores `day_volume`, `last_size`, `vol_24hr`, and `vol_all_currencies` separately as supplied, and interprets `time` as Unix milliseconds as in the Prompt 05 probe. The adapter was exercised with constructed messages. Live source timestamp and volume semantics remain unverified. The database opens on demand, enables foreign keys on each connection, and serializes initialization and writes with explicit SQLite transactions. Default synthetic history stays independent of the recorder.

- SQLite assigns each stored version an immutable, increasing `observation_id`. The ID also serves as deterministic receipt order for accepted versions. The recorder does not reorder writes by timestamps. Source-time reads sort by normalized UTC and then by ID. The backend receipt clock value is retained separately.
- A SHA-256 fingerprint covers the canonical JSON of source name, ticker, original timestamp and unit, normalized numeric price, source volume fields, selected source fields, and the optional verified source event ID. Canonical JSON sorts object keys, removes insignificant formatting, and preserves array order and source-field value types. Backend receipt time and database-generated fields are excluded. A matching fingerprint returns the original ID without adding a row or changing its receipt time. A return to earlier values can create a distinct version when source evidence identifies a distinct correction, such as a provider revision sequence in the selected source fields.
- Only pass `verified_event_id` when source evidence shows that the same ID identifies the same correctable event. Its scope is source name and ticker. The recorder links new content for that ID to its latest stored version. A ticker and timestamp alone are insufficient, and uncertain provider identifiers can be kept in the selected source fields without setting `verified_event_id`. No Yahoo event ID has been verified in this project.
- Historical reads return every unique stored version, including earlier revisions. Exact repeats have no separate row. Current reads omit a row only when a stored revision points to it, so the latest stored version in each verified chain and every independent observation remain visible. Late independent observations remain available in both receipt order and source-time order.

## Prompt 07 observation-to-candle flow

The aggregator reads `ObservationStore.read(current_only=True, order="source")` once, selects a source and ticker, and groups that snapshot into half-open UTC minutes. SQLite orders equal source times by `observation_id`, the immutable receipt sequence. Open and close use the first and last prices in that order. High and low use all prices in the minute. The recorder excludes exact repeats and keeps ambiguous same-time observations independent. Only verified revision links replace a historical version in this calculation. Historical reads still expose all stored versions.

Each call rebuilds the source and ticker's candles from the current snapshot. A late observation or a correction can change OHLCV for a completed minute. A correction that moves an observation can affect both its old and new minute. A changed cumulative value can also affect a later minute that uses it as a baseline. The caller's explicit UTC evaluation time controls only `is_complete`, which becomes true at the next minute boundary. No candle is emitted for a minute without observations.

The caller identifies a verified cumulative field. The instructor fixture identifies `day_volume` as a cumulative session total for constructed data. Totals accept nonnegative integers and decimal digit strings, and are checked in source-time order starting with the most recent valid pre-minute baseline. Every row in the target minute needs a valid total and the observed sequence must be nondecreasing. Volume is the final total minus the baseline. Missing evidence or a decrease yields `None` (JSON `null`). The latest valid total can serve as the next baseline. The calculation never substitutes a `last_size` value or sums cumulative totals. Unknown live provider semantics leave the cumulative field unset.

## Prompt 07A regular-session calendar

The 40 installed distributions match the approved lock. With `exchange-calendars==4.13.2`, requesting `XNAS` for AAPL resolves to the library's shared `XNYS` U.S. equity schedule. This alias has no separate Nasdaq-specific exception schedule. The installed calendar returned 14:30–21:00 UTC for November 9, 2026, no session on Thanksgiving (November 26), and 14:30–18:00 UTC for the November 27 early close. The 09:30 New York open moved from 14:30 UTC on March 6 to 13:30 UTC on March 9 as the New York offset changed from UTC−05:00 to UTC−04:00.

The aggregation boundary is one current, availability-filtered candle per UTC minute. The synthetic history route uses each CSV row only after its minute ends. The saved-observation path can derive a minute in progress by choosing the latest revision received as of the display time, then excluding observations with later source times. Earlier versions remain auditable in SQLite. The aggregator uses one snapshot for all intervals and ignores minutes outside the regular session.

Intraday windows use whole interval offsets from the session open, with the last window clipped at the session close. Daily windows use that session's open and close. Missing minutes never shift a boundary. Each result uses first open, highest high, lowest low, last close, and the sum of observed minute volumes if all are known. Unknown constituent volume yields `null`. The envelope reports symbol, interval, evaluation time, and timestamp-keyed metadata separately from the six market-data fields. Coverage compares observed minutes with the scheduled count. Completion depends on the window's scheduled end, including early closes.

## Prompt 08 market feed WebSocket

FastAPI's lifespan owns a provider-independent coordinator. The default app loads the synthetic CSV. Provider-backed startup injects the observation iterator, the UTC clock, and a SQLite path. The lifespan starts one upstream task per application process for AAPL, even with multiple browser tabs. Shutdown cancels background work and closes the provider and downstream streams. The Yahoo source uses the pinned yfinance async WebSocket decoder with one subscription, a five-second connection timeout, and no resubscription or reconnect loop. The test-only provider can inject an outage and subsequently resume observations. Yahoo's cumulative-volume mapping is unset, so provider-backed Yahoo candles report unknown volume.

Each accepted observation is committed to SQLite before publication. The coordinator derives one-minute candles from current versions available at the supplied UTC evaluation time, and then uses the regular-session aggregation for the selected interval. Observations outside the calendar's supported range remain in SQLite and produce no candle. A repeat adds no row. A late observation or verified revision causes recalculation, including for a completed candle. Updates replace the chart row at the same timestamp or append a new timestamp. If a revision removes a candle, a fresh snapshot replaces the chart. The backend also updates completion at elapsed interval boundaries. Vue renders backend candles and never aggregates prices or volume.

### Protocol version 1

Connect to `/api/market-feed?symbol=AAPL&interval=1m`. `AAPL` and `1m` are defaults. The supported intervals are `1m`, `5m`, `15m`, `1h`, and `1d`. The server validates the selection before sending data. Connections are read-only and limited to local dashboard origins when the browser supplies an Origin header. The coordinator allows 16 clients per process, four queued batches per client, and at most 500 returned candles for a provider-backed selection. A slow client can receive a replacement snapshot. The route bounds subscription and message sends at five seconds.

Every message has `version`, `type`, `symbol`, `interval`, `source`, `data_mode`, `backend_status`, `feed_status`, and `as_of`. `data_mode` identifies the data source, and `feed_status` conveys freshness and availability. `observation_id`, `source_time`, and `receipt_time` identify the last newly persisted observation in the publication context. A completion-only update or a batch of changed candles can reuse that context. The fields may be `null` before the first row. `latest_source_time` is the latest source timestamp observed so far. `age_seconds` is the nonnegative whole-second difference between that timestamp and backend UTC evaluation time, or `null` when there is no source observation. A late observation can have an earlier `source_time` than `latest_source_time`.

| `type` | Additional fields and behavior |
| --- | --- |
| `snapshot` | `candles` and parallel `metadata` arrays for the selected interval. This uses the same history calculation as `/api/history`, evaluated at the snapshot's `as_of`. A later snapshot replaces the chart. |
| `candle_upsert` | One `candle` and its `metadata`. Insert or replace by candle timestamp. |
| `feed_status` | Current feed context, sent about every two seconds when there is no candle change. |
| `error` | A fixed safe `code` and `message`. Invalid subscriptions, capacity limits, and read-only violations close the socket. History errors are reported without payloads, paths, or exception details. |

Every candle contains exactly `timestamp`, `open`, `high`, `low`, `close`, and `volume`. Candle metadata carries the matching `timestamp`, `coverage`, `observed_minutes`, `expected_minutes`, and `is_complete`. Completion describes the interval boundary. Coverage describes how many scheduled minutes contributed. Synthetic HTTP history retains its existing response shape. Provider-backed HTTP history adds `source` and `data_mode` to the response envelope.

| Status | Meaning |
| --- | --- |
| `connecting` | The upstream is starting and has yet to supply an accepted observation. The first-observation status window is 30 seconds. |
| `live` | The live source supplied an accepted observation and the latest source timestamp is under 120 seconds old. |
| `stale` | The live source has supplied data and the latest source timestamp is at least 120 seconds old. Existing candles remain visible with their timestamps. |
| `unavailable` | Upstream is disabled, reports an outage, ends, or supplies no accepted observation during the startup window. The downstream socket can stay connected. |
| `recorded` | The injected recorded or constructed source supplied an accepted observation. The display explicitly labels the data mode. |
| Browser disconnected | The browser lost its FastAPI socket. The UI shows the upstream status as unknown until a socket supplies a new message. The chart keeps its last data and attempts two reconnects. |

The timeframe selector aborts the previous HTTP request, closes the previous socket, and ignores callbacks belonging to either. A new socket subscribes after the selected HTTP request completes or fails. Each message is checked against the active symbol and interval.

### Integrated live check

After separate approval, start one live-mode backend during an active regular session. Record the UTC attempt window and selected interval. Trace an observation whose source time falls within that session. Capture the normalized AAPL source time and price, the SQLite observation ID and receipt time, the WebSocket candle and metadata, and the matching values displayed in the chart. Match the ID in the socket message to its SQLite row and compare the displayed candle against the backend result for the same timestamp and interval. Check upstream loss with the page still connected and record what the two status fields show. Stop the live backend and verify its connection is closed. If the attempt receives no qualifying update, record the outcome and leave live receipt pending.
