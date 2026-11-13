# Current handoff

## Checkpoint

Prompt 08 connects the existing AAPL chart to `/api/market-feed` for all five timeframes. Default startup uses the synthetic CSV. The recorded SmokeTest injects constructed observations and uses a disposable database. The opt-in Yahoo provider uses one lifecycle-owned AAPL subscription per backend process. The coordinator commits observations before publishing backend-calculated candles. The chart displays downstream connection and upstream feed status separately, and exposes timestamps, observation ID, coverage, and completion. See the [protocol](../docs/design-pipeline.md#prompt-08-market-feed-websocket) and [Prompt 08 verification](../docs/verification.md#prompt-08---market-feed-websocket).

All 67 backend tests and three routed Chrome checks passed. The post-fix normal-PowerShell SmokeTest then passed all three Playwright tests in 24.0 seconds. It verified health and backend outage recovery, `Unavailable` for unknown volume, `0 shares` at 14:31 UTC, and the recorded update from close 100 to 103 for SQLite observation ID 2. The browser stayed connected through the upstream outage, recovery added the next candle, and the timeframe test rejected delayed HTTP responses and retired WebSocket updates.

The initial normal-PowerShell run passed two of three tests. AutoLoop reproduced a layout-only crosshair callback moving the inspector from the 14:31 candle to the 14:32 candle. The inspector now accepts mouse or touch selection, and the test uses timestamp-derived option values with its HTTP fixture isolated from WebSocket snapshots. The final run had no unexpected Chrome application-console errors. The intentional outage logged one failed request, and Vite's teardown `ECONNRESET` was non-failing. Port 5173 briefly appeared in the immediate listener check. A later bounded check found no listeners on either service port, and no process required manual termination. See the [AutoLoop evidence](../docs/verification.md#browser-smoketest-autoloop) and [final SmokeTest](../docs/verification.md#final-normal-powershell-smoketest).

Prompt 07A adds `1m`, `5m`, `15m`, `1h`, and `1d` AAPL history with a metadata envelope. The default chart still uses the three synthetic minutes. The five-minute fixture gives `100/105/99/104/3550` with 3/5 coverage, and daily coverage is 3/390. Saved-observation snapshots can apply an `as_of` cutoff before revision selection. The approved 40-pin lock is installed, and `XNAS` resolves to the shared `XNYS` regular-session calendar. See the [Prompt 07A verification](../docs/verification.md#prompt-07a---regular-session-timeframes).

Prompt 07 adds provider-independent one-minute UTC candle calculation over the SQLite recorder's current versions. The constructed AAPL fixture returned O/H/L/C/V `100/103/100/101/11` before and at completion, and again after the late observation. All 41 backend tests passed with the process-local asyncio runner. `pip check`, frontend ESLint, and the production build passed. See the [Prompt 07 results](../docs/verification.md#prompt-07---one-minute-candles).

Prompt 06 adds the SQLite observation recorder and an adapter for decoded Yahoo messages. The ignored runtime path is `backend/data/observations.sqlite3`. Use `.\.venv\Scripts\python.exe -B -m app.observations` from `backend/` to initialize it. Constructed inputs verified repeat suppression, revision retention, and persistence after reopening in a fresh Python backend process. All 24 backend tests passed, as did `pip check`, frontend lint, and the production build. See [Prompt 06 verification](../docs/verification.md#prompt-06---sqlite-observation-recorder).

Prompt 05's normal-PowerShell installation is complete. All 36 pins match `backend/.venv`, including yfinance 1.8.0 and websockets 17.4. The WebSocket import and `pip check` passed. The restricted project shell failed Yahoo hostname resolution with Windows error 11001. The separately authorized normal-PowerShell probe resolved DNS, opened the Yahoo Finance WebSocket, and subscribed only to AAPL. It timed out within the 25-second bound without a qualifying update or a retry. Price, source and receipt times, and volume were unobserved. Live receipt remains unverified. See the [bounded check evidence](../docs/verification.md#prompt-05---bounded-aapl-check).

Final verification passed all 12 backend tests with the process-local asyncio runner, frontend ESLint with zero warnings, and the production build. Ports 8000 and 5173 were free and the Yahoo probe had exited. The virtual environment and generated artifacts remain ignored and untracked.

Prompt 07 started at `54da86d` on `feature/assignment-4-part-1`, with `main` at `474573e`, a clean worktree, an empty index, and no remote. Prompts 2 and 3 were verified and committed at `0954655` and `c683818`. Prompt 4's committed chart uses the synthetic CSV. Its isolated Chrome favicon check, lint, and build passed. See the [Prompt 4 verification](../docs/verification.md#prompt-4-autoloop---favicon-console-error).

## Foundation files and checks

- Created `README.md`, `AGENTS.md`, `docs/design-pipeline.md`, `docs/verification.md`, `handoffs/create-handoff.md`, and this handoff. Created empty `backend/` and `frontend/` directories.
- Copied the 20 numbered instructor prompts into `prompts/` and the synthetic sample into `prompts/data/sample-candles.csv`. All 21 SHA-256 hashes matched the archive. The numbered files are the originals.
- Confirmed the starting root was empty and outside Git. Verified the Windows tools, discovered a working base Python 3.14.7 despite the failed shell aliases, and verified SQLite with an in-memory round trip. Node.js, npm, npx, pip, and Corepack ran. No project-configured Python environment, dependency manifests, or lockfiles were found. See [verification](../docs/verification.md) for missing packages and exact checks.
- The final tree contained 27 files. The six new documents were nonempty, their file links resolved, and a second hash comparison confirmed the starter materials still matched the archive.
- Prompt 01a added `.gitignore`, [AI-USE.md](../AI-USE.md), and the student-added [governance prompt](../prompts/01a-project-governance-and-version-control.md). Updated the README, project instructions, design notes, verification log, and this handoff. The application directories remain empty and no project dependencies are installed.
- The foundation is committed at `474573e`.
- The approved dry run failed to resolve the PyPI hostname. Setup stopped with no Python lockfile, application source, frontend manifest, or running project services. See [verification](../docs/verification.md) for the command and exact error.

## Outstanding decisions and next task

- Actual live AAPL receipt remains pending for the separately authorized market-hours check. The final SmokeTest made no Yahoo request. Trace a qualifying Yahoo message through normalization, the persisted observation ID, the backend candle, the FastAPI WebSocket, and the visible chart. The Prompt 05 probe established connectivity and reached its bound before receiving a qualifying update.
- Replay controls, replay order and pacing, and verified Yahoo volume semantics remain future work. Keep the course disclosure current as tools or models change.

## Prompt 2A connectivity retry

The single official PyPI probe failed at DNS resolution for `pypi.org` with Windows error 11001. The HTTPS request was skipped. See [verification](../docs/verification.md) for the preflight and result.

## Prompt 2B resumption

- The explicitly authorized normal PowerShell session resolved and installed the approved Python wheels from official PyPI. The project shell verified all 17 pins and the matching wheel report, imports, and `pip check`.
- Added backend source under `backend/app/` and a focused test under `backend/tests/`. Added the exact frontend manifest, Vue entry and component, Vite and lint configs, and Playwright config and test. The focused backend test was interrupted without a result. All five JavaScript syntax checks passed.
- The project shell's single npm install attempt returned `ENOTFOUND registry.npmjs.org`. The student later completed installation in normal PowerShell using the official registry.

## Prompt 2 AutoLoop verification

- The student reported HTTP 200 from the official npm registry, 131 packages installed, and zero production audit vulnerabilities. The project shell verified all seven exact direct pins against the manifest, lockfile, and installed package metadata. Python imports and `pip check` passed.
- esbuild 0.28.2 ran directly. Lint passed with zero warnings despite npm's ESLint support-window warning. The production build passed with esbuild's post-install script still unapproved.
- The bounded backend test timed out while Windows asyncio initialized its loopback socket pair. Python and Node probes returned Windows error 10013 and `EACCES`, respectively. The Playwright web-server check did not become ready and was interrupted before browser assertions. AutoLoop made zero source corrections.
- Ports 8000 and 5173 had no listeners afterward. The environment, npm cache, dependencies, and build output are ignored. Prompt 2 still needs the backend test and browser evidence. See [verification](../docs/verification.md) for the observations.

## Prompt 2C - Windows backend-stop assertion

- The student reported that normal PowerShell passed the backend unittest in 0.115 seconds, including the exact JSON assertion. The first Chrome run reached both HTTP 200 responses with `{"status":"healthy"}` and displayed the pending and healthy states.
- The immediate request after shutdown returned `read ECONNRESET`. AutoLoop cycle 1 allowed reset or refusal on that assertion alone. Windows can refuse a new connection or reset a reused connection when the server stops.
- Syntax and lint passed. Full browser verification was pending at the end of Prompt 2C.

## Prompt 2D final verification

- The student reported one backend test passed in 0.115 seconds, including exact status, content type, and body assertions. The corrected Chrome SmokeTest passed in 11.1 seconds total, with 4.8 seconds in the test.
- Direct and proxied requests both returned HTTP 200 with `{"status":"healthy"}`. Stopping FastAPI produced proxy HTTP 500 and a visible unavailable state without healthy JSON. Restart restored both HTTP 200 responses and the healthy UI. Chrome logged one expected failed-resource error during the outage and no unexpected page or application-console errors.
- A final listening-socket query confirmed both ports were released. The earlier closed and FIN_WAIT rows were transitional. The final process-owner query had no listening processes to report.
- Local Python imports, `pip check`, syntax checks, ESLint, and the production build passed. The production-only audit previously returned zero vulnerabilities. The pinned ESLint support-window warning remains non-failing and the esbuild post-install script remains unapproved.
