# Live Market Workstation

Live Market Workstation is a local educational market-data dashboard for a student or reviewer. Its first milestone is to observe live Yahoo Finance updates for AAPL, inspect candlesticks and volume with source and freshness information, and replay previously recorded observations from SQLite.

Assignment 4 is cumulative. Part 4.1 establishes market-data observation, visualization, persistence, and replay. Parts 4.2 and 4.3 build on that foundation at their assigned checkpoints. This educational project prohibits real order execution, financial advice, and profitability claims.

Prompt 01 established the project structure. Student-added Prompt 01a covers governance, AI disclosure, and the local Git baseline. [Instructor Prompt 2](prompts/02-connect-vue-and-fastapi.md) is verified. The Vue connection check reaches FastAPI through Vite, shows an unavailable state when the backend stops, and recovers when it restarts. See [AI-USE.md](AI-USE.md) for the distinction between development assistance and future application AI features.

Assignment 4.1 verified live Yahoo Finance receipt for AAPL and offline replay of the same recorded observation. The final report, public repository publication, video, and Canvas submission remain pending. See the [evidence record](docs/verification.md#supplemental-prompt-08a---bounded-live-evidence).

## Assignment 4.1 goals

- Receive actual AAPL updates from Yahoo Finance through the yfinance WebSocket client. Use UTC internally for source timestamps, receipt timestamps, and candle boundaries.
- Record observations in SQLite before deriving candles. Read stored observations back in a stable order so that a reviewer can replay them after a restart.
- Use FastAPI for history and WebSocket updates. Display candlesticks, volume, source, data age, feed status, and candle-completion status in Vue.
- Label live data, synthetic sample data, recorded data, and replay data. Separately indicate delayed or stale data, unavailable feeds, complete and incomplete candles, and known, unknown, or unavailable volume.
- Capture evidence of feed unavailability and recovery when observable. CSV practice uses the instructor's synthetic sample. The graded live-data evidence requires receipt of an actual Yahoo Finance streaming update.

## Stack and prerequisites

| Layer | Planned technology | Checked on this computer |
| --- | --- | --- |
| Local shell | Windows and PowerShell | Windows x64, build 26300, PowerShell 7.6.9 |
| Backend | Python with type hints | Python 3.14.7 runs directly. The Windows `python` and `py` aliases failed in the project shell. |
| API transport | FastAPI HTTP and WebSocket routes, served by Uvicorn | HTTP routes include `/api/health`, `/api/history`, and `/api/replay/coverage`. Chart updates use `/api/market-feed` or `/api/replay/stream`. |
| Storage | Python standard-library `sqlite3` | SQLite 3.50.4 passed the Prompt 06 recorder and restart checks with constructed observations. |
| Market feed | Yahoo Finance via yfinance | `yfinance==1.8.0` and `websockets==17.4` import in `backend/.venv`. The integrated normal-PowerShell check captured 226 unique AAPL observations in one subscription. |
| Exchange sessions | `exchange-calendars==4.13.2` | AAPL requests `XNAS`, which uses the shared `XNYS` U.S. equity schedule. The alias has no separate Nasdaq-specific exception schedule. |
| Frontend | Vue 3 single-file components with the Composition API, Vite for local development, and TradingView Lightweight Charts | Node.js 24.20.0 and npm 11.19.0 run. The Vue, Vite, and Lightweight Charts 5.3.0 pins are in `frontend/package.json`. |
| Package tools | pip for Python and npm for the frontend | pip 26.2.1 runs in the existing environment. The student completed the npm install from the official registry in normal PowerShell. The 40-pin Python lock was checked against the installed distributions. |

The approved Python environment is `backend/.venv`, created from CPython 3.14.7. The student completed the locked wheel installation through official PyPI in normal PowerShell. All 40 application pins match the installed distributions, and `pip check` passes. HTTPX is used only by the backend `unittest` tests. See [verification](docs/verification.md) for the setup evidence.

## Run locally

For a clean checkout, install the locked frontend dependencies from the project root in normal PowerShell. The current checkout already has these dependencies. The original verified installation generated the lockfile with `npm install`. The `npm ci` command below is the clean-checkout procedure and was not rerun during final verification.

```powershell
$npmCache = Join-Path (Get-Location).Path 'frontend\.cache\npm'
npm.cmd --prefix .\frontend ci --cache $npmCache --no-audit --no-fund
```

For a clean checkout on Windows, create the Python environment with the local CPython 3.14.7 executable and install from the exact lock. The current checkout already has this environment.

```powershell
$projectPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $projectPython -m venv --without-scm-ignore-files .\backend\.venv
& .\backend\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check install --only-binary=:all: --no-cache-dir --index-url https://pypi.org/simple --timeout 5 --retries 0 -r .\backend\requirements.lock.txt
& .\backend\.venv\Scripts\python.exe -m pip check
```

For an existing environment, keep `backend/.venv` and run only the pip commands above in normal PowerShell if installation is needed.

### Start the dashboard

Start the backend and frontend in separate PowerShell windows with the commands in the table below. Open `http://127.0.0.1:5173/`. The default backend serves synthetic CSV history and its matching WebSocket snapshot. A clean checkout can use this mode as soon as dependencies are installed. It starts without a runtime database or Yahoo connection.

The recorded demonstration runs inside the browser SmokeTest. It starts a test-only backend with a disposable SQLite database, injects constructed AAPL observations, and checks the chart through the Vite proxy. It removes the database after stopping the test backend.

### Connection verification

Run the backend test and browser SmokeTest in normal PowerShell with loopback access. The restricted project shell can run imports, syntax checks, lint, and the production build. See [verification](docs/verification.md) for the failed DNS and loopback attempts and the successful normal-PowerShell results.

| Task | Working directory | Command |
| --- | --- | --- |
| Complete backend tests | `backend/` | `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v` |
| Backend development server | `backend/` | `.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Frontend development server | `frontend/` | `npm.cmd run dev` |
| Stop a manually started service | Its server terminal | Press Ctrl+C |
| Lint | `frontend/` | `npm.cmd run lint` |
| Production build | `frontend/` | `npm.cmd run build` |
| Browser SmokeTest | `frontend/` | `npm.cmd run test:connection` |
| Production-only audit | `frontend/` | `npm.cmd audit --omit=dev --cache .\.cache\npm` |

For the browser SmokeTest, leave ports 8000 and 5173 free. Playwright uses the installed Chrome channel and manages both services. The test checks `http://127.0.0.1:8000/api/health` directly and `http://127.0.0.1:5173/api/health` through Vite. It expects HTTP 200 and `{"status":"healthy"}` before and after restarting the backend, with a visible outage state while the backend is stopped.

After shutdown, check for listeners with `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue`.

The student's official-registry production-only audit reported zero vulnerabilities. The pinned ESLint release has an npm support-window warning, and lint passed with zero warnings. The esbuild CLI reported 0.28.2 and Vite built successfully with the esbuild post-install script still unapproved.

### Synthetic CSV history

`GET /api/history` defaults to three one-minute synthetic practice candles for AAPL from `backend/data/sample-candles.csv`, a byte-for-byte copy of `prompts/data/sample-candles.csv`. The UTC timestamp is the inclusive start of the interval. The 14:30 minute ends just before `14:31:00Z`.

The endpoint supports `interval=1m`, `5m`, `15m`, `1h`, or `1d`, and `symbol=AAPL`. Optional `as_of` accepts a supported ISO 8601 UTC timestamp at or before the current time, with `Z` or `+00:00`. The default cutoff is the request's current UTC time. The CSV contains finished minute summaries, so a row becomes available at its minute's end. Unsupported parameters, duplicate keys, and invalid evaluation times return a bounded HTTP 422. An unreadable or invalid CSV returns a generic HTTP 500.

The response contains `symbol`, `interval`, `as_of`, `candles`, and `metadata`. Each timestamp-ordered candle has exactly `timestamp`, `open`, `high`, `low`, `close`, and `volume`. Each metadata row gives the matching `timestamp`, `coverage` (`full` or `partial`), `observed_minutes`, `expected_minutes`, and `is_complete`. Intraday windows start at the session open, and a daily candle spans one regular session. A window completes at its scheduled end even with partial coverage. Gaps preserve window alignment, and empty windows are omitted. Volume sums observed constituent minutes and is `null` if any contributing volume is unknown.

For example, `/api/history?symbol=AAPL&interval=5m&as_of=2026-11-09T14:35:00Z` returns a 14:30 UTC candle with O/H/L/C/V `100/105/99/104/3550` and partial coverage of three of five minutes. The data remains synthetic. See the [Prompt 07A checks](docs/verification.md#prompt-07a---regular-session-timeframes) and the [PowerShell history check](docs/verification.md#bounded-normal-powershell-check).

### Inspect the chart

The chart defaults to `1m`. Choose `5m`, `15m`, `1h`, or `1d` to load matching HTTP history and open a new WebSocket for that interval. Hover over a candle or use **Inspect candle (UTC)** to see its time, OHLC, volume, coverage, and forming or complete status. In the synthetic `1m` fixture, the close at 14:31 UTC on November 9, 2026 is **101**, with volume of **850 shares**. Unknown volume is displayed as **Unavailable**.

The chart displays source and data mode, source and receipt times, server-calculated age, browser WebSocket state, and upstream feed status. A connected browser can show an unavailable upstream. After a disconnect the browser tries twice, after 1 and 2 seconds. **Reconnect feed** starts a new attempt when the socket is disconnected.

See the [WebSocket contract](docs/design-pipeline.md#prompt-08-market-feed-websocket) and [Prompt 08 results](docs/verification.md#prompt-08---market-feed-websocket).

### Replay recorded observations

Stop the live-mode backend and start the default `app.main:app` backend from the run table. Open the dashboard and choose **Open replay**. Select a recorded symbol and source, then enter the UTC start and end in ISO 8601 format, such as `2026-11-09T14:30:00Z`. The start is inclusive and the end is exclusive. The range selects original backend receipt times and can cover up to 24 hours and 1,000 observations. The replay chart uses one-minute candles. Its timeframe control is disabled while replay is open.

Choose `1×`, `2×`, or `4×` and start the replay. Pause freezes playback. Resume continues from the same observation, and reset clears the chart so the same selection can run again. The backend uses stored observation IDs for arrival order. A late observation or verified revision changes the chart when its turn arrives. The chart shows **Replay**, the original source and receipt times, observation ID, and whether the candle is forming or complete.

Replay reads the saved rollback-journal SQLite database without writing to it. Stop any external writer before replaying. A clean checkout or an empty range displays a no-observations message. The browser SmokeTest creates a separate constructed database and removes it afterward. The offline replay of Yahoo observation 193 matched the original timestamps and close of `358.1301`, with volume `Unavailable` and zero Yahoo requests or subscriptions. The runtime database hash and all 226 rows were unchanged. See the [replay contract](docs/design-pipeline.md#prompt-09-recorded-session-replay), [constructed fixture evidence](docs/verification.md#prompt-09---read-only-sqlite-replay), and [offline Yahoo replay screenshot](docs/evidence/08a-offline-yahoo-replay.png).

### Integrated live check

During the separately authorized AAPL check, the opt-in startup command from `backend/` is:

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn app.main:create_live_app --factory --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
```

Run a single backend process for this mode. It opens one AAPL subscription and uses the ignored SQLite database for history and new observations. On November 13, 2026, the integrated check traced observation 193 from SQLite to the live dashboard. The browser WebSocket was connected, the feed was live, and the forming one-minute candle closed at `358.1301` with volume `Unavailable`. The separately constructed feed check showed upstream unavailability and recovery while the browser socket stayed connected. See the [live screenshot](docs/evidence/08a-live-aapl-receipt.png) and [trace record](docs/verification.md#live-yahoo-aapl-capture).

### Initialize the local observation database

From `backend/`, run:

```powershell
.\.venv\Scripts\python.exe -B -m app.observations
```

The command initializes the ignored `backend/data/observations.sqlite3` file with `PRAGMA user_version = 1`. A clean checkout contains no database. After the Python environment is set up, the command creates an empty schema on first use. Running it again preserves the data. An unsupported schema version raises an error. Pass `--db <path>` to use another database in an existing directory. The HTTP backend can still start on a clean checkout and serve health and synthetic history without this initialization.

The `observations` table stores an immutable ID that doubles as receipt order, source and ticker, original integer source time and unit, normalized source and receipt UTC times, price, volume fields, decoded source evidence, a unique content fingerprint, and optional verified event and revision IDs. `ObservationStore.read()` returns all unique versions. `read(current_only=True)` keeps independent observations and the latest stored version in each verified chain. Both support `order="source"` for source-time order. The Yahoo adapter accepts already-decoded messages. Prompt 06 used constructed inputs and disposable databases. See the [identity policy](docs/design-pipeline.md#prompt-06-observation-identity-and-revisions) and [restart evidence](docs/verification.md#prompt-06---sqlite-observation-recorder).

### Form one-minute candles from observations

`app.candles.form_candles()` reads current versions for one source and ticker. It groups observations by UTC source minute, including the minute start and excluding the next boundary. Prices are ordered by source time and then by immutable observation ID, which is the recorder's receipt order. Empty minutes produce no candle. Recalculating after a late observation or a verified correction uses the updated snapshot. Earlier observation versions remain in the recorder for audit.

Each candle has exactly six market-data fields in `data` (`timestamp`, `open`, `high`, `low`, `close`, `volume`) and a separate `is_complete`. The caller supplies a UTC evaluation time. Completion begins at the next minute boundary and does not prevent a later recalculation from changing OHLCV. An optional `as_of` cutoff selects the latest saved revision received by that time and excludes later source times. The same minute calculation feeds the regular-session timeframe aggregator for live and replay data.

For a field explicitly identified as a cumulative session total, volume is the last valid total in the minute minus the most recent valid total strictly before the minute. A missing or invalid in-minute value, missing baseline, or observed decrease yields `None` (JSON `null`). A known zero is `0`. The constructed fixture uses `day_volume` for this calculation. Yahoo's live volume semantics remain unverified. See the [Prompt 07 checks](docs/verification.md#prompt-07---one-minute-candles).

## Project map

| Path | Contents |
| --- | --- |
| `README.md` | Project overview, prerequisites, and run instructions |
| `AGENTS.md` | Standing project instructions |
| `.gitignore` | Local environment, dependency, build, and runtime exclusions |
| `AI-USE.md` | Course disclosure of development tools and application AI status |
| `backend/` | FastAPI health and synthetic history routes, SQLite recorder, Yahoo message adapter, one-minute candle calculation, backend tests, dependency lock, and ignored local runtime files |
| `frontend/` | Vue connection interface and synthetic candlestick chart, Vite proxy, pinned manifest, and Chrome SmokeTest |
| `docs/design-pipeline.md` | Planned data flow and evidence requirements |
| `docs/verification.md` | Commands, expected results, and observed results |
| `docs/evidence/` | Public screenshots of the live AAPL capture and offline Yahoo replay |
| `prompts/` | 20 original instructor prompts and the student-added governance and live evidence checkpoints |
| `prompts/data/sample-candles.csv` | Instructor practice sample with three synthetic candles |
| `handoffs/create-handoff.md` | Handoff instructions |
| `handoffs/current.md` | Latest checkpoint and next task |
