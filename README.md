# Live Market Workstation

Live Market Workstation is a local educational market-data dashboard for a student or reviewer. Its first milestone is to observe live Yahoo Finance updates for AAPL, inspect candlesticks and volume with source and freshness information, and replay previously recorded observations from SQLite.

Assignment 4 is cumulative. Part 4.1 establishes market-data observation, visualization, persistence, and replay. Parts 4.2 and 4.3 build on that foundation at their assigned checkpoints. This educational project prohibits real order execution, financial advice, and profitability claims.

Prompt 01 established the project structure. Student-added Prompt 01a covers governance, AI disclosure, and the local Git baseline. Both application directories are empty and no application dependencies are installed for the project. The next implementation task is [instructor Prompt 2](prompts/02-connect-vue-and-fastapi.md). See [AI-USE.md](AI-USE.md) for the distinction between development assistance and future application AI features.

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
| API transport | FastAPI HTTP and WebSocket routes, served by Uvicorn | FastAPI, Uvicorn, and `websockets` did not import in the checked interpreter. |
| Storage | Python standard-library `sqlite3` | SQLite 3.50.4 passed an in-memory write/read check. |
| Market feed | Yahoo Finance via yfinance | yfinance did not import. The planned subscription uses no Yahoo credentials. |
| Frontend | Vue 3 single-file components with the Composition API, Vite for local development, and TradingView Lightweight Charts | Node.js 24.20.0 and npm/npx 11.19.0 run. Vue, Vite, and Lightweight Charts were unavailable through local module resolution. |
| Package tools | pip for Python and npm for the frontend | pip 26.2.1 and Corepack 0.35.0 are available. No project dependency manifests or lockfiles exist yet. |

The working Python is a base installation. A project-specific environment has yet to be configured. See [verification](docs/verification.md) for the interpreter discovery command. Get student approval before creating an environment, installing software, or creating or changing manifests and lockfiles.

## Run locally

This checkpoint has empty `backend/` and `frontend/` directories. App start and stop commands will be added here after both services can be launched and checked. A clean startup should bring up FastAPI and Vue on loopback addresses using the chosen interpreter and project dependencies. Once the dashboard exists, it should open in a browser, display the selected data mode and feed status, and show an unavailable-feed state when appropriate. Record the tested shutdown commands as well.

## Project map

| Path | Contents |
| --- | --- |
| `README.md` | Project overview, prerequisites, and run instructions |
| `AGENTS.md` | Standing project instructions |
| `.gitignore` | Local environment, dependency, build, and runtime exclusions |
| `AI-USE.md` | Course disclosure of development tools and application AI status |
| `backend/` | Empty directory for Python and FastAPI |
| `frontend/` | Empty directory for Vue |
| `docs/design-pipeline.md` | Planned data flow and evidence requirements |
| `docs/verification.md` | Commands, expected results, and observed results |
| `prompts/` | 20 original instructor prompts and the student-added governance checkpoint `01a-project-governance-and-version-control.md` |
| `prompts/data/sample-candles.csv` | Instructor practice sample with three synthetic candles |
| `handoffs/create-handoff.md` | Handoff instructions |
| `handoffs/current.md` | Latest checkpoint and next task |
