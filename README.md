# Live Market Workstation

Live Market Workstation is a local educational market-data dashboard for a student or reviewer. Its first milestone is to observe live Yahoo Finance updates for AAPL, inspect candlesticks and volume with source and freshness information, and replay previously recorded observations from SQLite.

Assignment 4 is cumulative. Part 4.1 establishes market-data observation, visualization, persistence, and replay. Parts 4.2 and 4.3 build on that foundation at their assigned checkpoints. This educational project prohibits real order execution, financial advice, and profitability claims.

Prompt 01 established the project structure. Student-added Prompt 01a covers governance, AI disclosure, and the local Git baseline. [Instructor Prompt 2](prompts/02-connect-vue-and-fastapi.md) is verified. The Vue connection check reaches FastAPI through Vite, shows an unavailable state when the backend stops, and recovers when it restarts. See [AI-USE.md](AI-USE.md) for the distinction between development assistance and future application AI features.

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
| API transport | FastAPI HTTP and WebSocket routes, served by Uvicorn | FastAPI 0.162.5 and Uvicorn 0.54.0 import in the local environment. The implemented HTTP routes are `/api/health` and `/api/history`. |
| Storage | Python standard-library `sqlite3` | SQLite 3.50.4 passed an in-memory write/read check. |
| Market feed | Yahoo Finance via yfinance | `yfinance==1.8.0` and `websockets==17.4` import in `backend/.venv`. The normal-PowerShell AAPL probe resolved DNS and opened the WebSocket. It timed out after 25 seconds without a qualifying update. |
| Frontend | Vue 3 single-file components with the Composition API, Vite for local development, and TradingView Lightweight Charts | Node.js 24.20.0 and npm 11.19.0 run. The Vue, Vite, and Lightweight Charts 5.3.0 pins are in `frontend/package.json`. |
| Package tools | pip for Python and npm for the frontend | pip 26.2.1 runs in the existing environment. The student completed the npm install from the official registry in normal PowerShell. The 36-pin Python lock was checked against the approved resolution. |

The approved Python environment is `backend/.venv`, created from CPython 3.14.7. The student completed the locked wheel installation through official PyPI in normal PowerShell. All 36 application pins match the installed distributions, and `pip check` passes. HTTPX is used only by the backend `unittest` tests. See [verification](docs/verification.md) for the setup evidence.

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

Prompt 05 confirmed Yahoo Finance WebSocket connectivity in normal PowerShell. An earlier attempt in the restricted project shell failed at DNS resolution. Live AAPL receipt remains unverified. Final Assignment 4.1 evidence requires a separate live-receipt check during active market conditions. See the [Prompt 05 verification record](docs/verification.md#prompt-05---bounded-aapl-check).

### Connection verification

Run the backend test and browser SmokeTest in normal PowerShell with loopback access. The restricted project shell can run imports, syntax checks, lint, and the production build. See [verification](docs/verification.md) for the failed DNS and loopback attempts and the successful normal-PowerShell results.

| Task | Working directory | Command |
| --- | --- | --- |
| Backend focused test | `backend/` | `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v` |
| Backend development server | `backend/` | `.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Frontend development server | `frontend/` | `npm.cmd run dev` |
| Stop a manually started service | Its server terminal | Press Ctrl+C |
| Lint | `frontend/` | `npm.cmd run lint` |
| Production build | `frontend/` | `npm.cmd run build` |
| Browser SmokeTest | `frontend/` | `npm.cmd run test:connection` |
| Production-only audit | `frontend/` | `npm.cmd audit --omit=dev --cache .\.cache\npm` |

For the browser SmokeTest, leave ports 8000 and 5173 free. Playwright uses the installed Chrome channel and manages both services. The verified direct backend URL is `http://127.0.0.1:8000/api/health`, and the verified frontend proxy URL is `http://127.0.0.1:5173/api/health`. Both returned HTTP 200 with the exact body `{"status":"healthy"}` before and after the restart. With the backend stopped, the proxy returned HTTP 500 and Chrome displayed `Backend unavailable.`.

After shutdown, check for listeners with `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue`. The completed SmokeTest released both ports.

This checkpoint verifies local HTTP connectivity. Yahoo Finance availability, live data, SQLite persistence, candlestick correctness, and WebSocket market streaming are outside its evidence.

The student's official-registry production-only audit reported zero vulnerabilities. The pinned ESLint release has an npm support-window warning, and lint passed with zero warnings. The esbuild CLI reported 0.28.2 and Vite built successfully with the esbuild post-install script still unapproved.

### Synthetic CSV history

`GET /api/history` returns three synthetic practice candles from `backend/data/sample-candles.csv`, a byte-for-byte copy of the instructor file at `prompts/data/sample-candles.csv`. Each row represents one instrument over one UTC minute. The timestamp marks the inclusive start, and the next minute's start is excluded. The 14:30 candle covers `14:30:00Z` through the instant immediately before `14:31:00Z`.

The endpoint returns an array ordered by timestamp with exactly `timestamp`, `open`, `high`, `low`, `close`, and `volume`. The loader checks the header and row width, parses UTC minute starts and normalizes them to `Z`, rejects duplicate times and nonfinite prices, checks OHLC bounds, and requires nonnegative integer volume. An unreadable or invalid file returns a generic HTTP 500. These practice candles are synthetic. The route provides no evidence of live market data or Yahoo Finance connectivity.

Prompt 3 verification passed in normal PowerShell. All 12 backend tests passed, `/api/history` returned HTTP 200 with three ordered candles matching the instructor CSV, and `/api/health` returned HTTP 200 with `{"status":"healthy"}`. To repeat the check, use the [Windows PowerShell procedure](docs/verification.md#bounded-normal-powershell-check).

### Inspect the synthetic chart

Start the backend and frontend with the commands above and open `http://127.0.0.1:5173/`. The chart loads `/api/history` and draws a candle and aligned volume bar for each UTC minute. Hover over a candle or use **Inspect candle (UTC)** to see its date, time, OHLC prices, and volume. The expected close at 14:31 UTC on November 9, 2026 is **101**, with volume of **850 shares**.

From the project root in normal PowerShell, run `npm.cmd --prefix .\frontend run test:connection` with ports 8000 and 5173 free. The test starts both services and checks the chart and connection behavior in installed Chrome. The chart passed an offline Chrome check with the synthetic fixture. The running-app SmokeTest still needs a shell with loopback access. Live Yahoo Finance ingestion, SQLite persistence, market-data WebSockets, and replay remain future work.

## Project map

| Path | Contents |
| --- | --- |
| `README.md` | Project overview, prerequisites, and run instructions |
| `AGENTS.md` | Standing project instructions |
| `.gitignore` | Local environment, dependency, build, and runtime exclusions |
| `AI-USE.md` | Course disclosure of development tools and application AI status |
| `backend/` | FastAPI health and synthetic history routes, loader and tests, dependency lock, and ignored Python environment |
| `frontend/` | Vue connection interface and synthetic candlestick chart, Vite proxy, pinned manifest, and Chrome SmokeTest |
| `docs/design-pipeline.md` | Planned data flow and evidence requirements |
| `docs/verification.md` | Commands, expected results, and observed results |
| `prompts/` | 20 original instructor prompts and the student-added governance checkpoint `01a-project-governance-and-version-control.md` |
| `prompts/data/sample-candles.csv` | Instructor practice sample with three synthetic candles |
| `handoffs/create-handoff.md` | Handoff instructions |
| `handoffs/current.md` | Latest checkpoint and next task |
