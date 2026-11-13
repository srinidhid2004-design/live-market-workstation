Perform one bounded Assignment 4.1 live AAPL evidence checkpoint during regular U.S. market hours.

Read `AGENTS.md`, `README.md`, `docs/design-pipeline.md`, `docs/verification.md`, and `handoffs/current.md` completely.

## Preflight

Confirm:

- Branch: `feature/assignment-4-part-1`
- HEAD: `0dd1591` with subject `Add verified read-only market replay`
- `main`: `474573e81efca7b4921cd602f4dee7803f804f36`
- Worktree and index clean
- No remote configured
- Ports 8000 and 5173 free
- Runtime SQLite database and sidecars ignored and untracked
- Dependencies match both locks
- Current time falls within a regular AAPL trading session according to the installed exchange calendar

If the market is closed, stop without starting Yahoo or changing files. Report the next regular session.

## Authorization

Authorize exactly one bounded live application attempt:

- Symbol: AAPL only
- One backend process
- One Yahoo subscription
- No retry
- No second provider session
- No alternate symbol or provider
- Maximum observation wait: 90 seconds
- Stop after the first qualifying accepted observation has been traced and public-safe evidence captured
- Do not print or retain the raw Yahoo payload

This checkpoint may write accepted observations only to the ignored runtime SQLite database through the existing recorder.

Do not change source code, dependencies, locks, or instructor prompts. If the integrated trace exposes a source defect, stop and diagnose it without editing.

## Live trace

Start the existing live factory:

`python.exe -B -m uvicorn app.main:create_live_app --factory --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5`

Start the existing Vue frontend and open it in installed Chrome.

For the first qualifying AAPL update, verify the complete path:

1. Yahoo observation accepted by the existing adapter.
2. Observation persisted before publication.
3. Immutable SQLite observation ID assigned.
4. Source and receipt timestamps stored in UTC.
5. Price and available volume evidence stored.
6. Existing candle calculation produces the corresponding candle.
7. FastAPI WebSocket publishes the update.
8. Vue chart displays the updated candle.
9. Visible UI shows:
   - AAPL
   - Yahoo Finance source
   - Live data mode
   - Browser WebSocket status
   - Upstream feed status
   - Observation ID
   - Source time
   - Receipt time
   - Data age
   - Candle completion
   - Known, zero, or unavailable volume accurately

Compare the normalized browser/WebSocket values with the exact SQLite row. Do not expose raw provider content or machine-private paths.

Capture public-safe screenshots showing the live chart and trace fields. Ensure no local absolute path appears.

If no qualifying update arrives within 90 seconds:

- Stop the attempt.
- Make no retry.
- Record DNS resolution, WebSocket state, feed status, elapsed bound, database before/after counts, and that live receipt remains unverified.
- Do not claim success.

## Offline replay of the live capture

Only after a successful live receipt:

1. Stop the live backend and confirm the Yahoo subscription is closed.
2. Record the runtime database count and SHA-256.
3. Restart the ordinary backend with the live provider off, using the same ignored database.
4. Confirm Replay coverage lists the recorded Yahoo/AAPL interval.
5. Replay the captured range through the existing Replay interface.
6. Verify that the replayed observation ID, source time, receipt time, candle close, and volume agree with the live capture and SQLite.
7. Confirm the UI says `Replay` and `Recorded session — live feed off`.
8. Confirm no Yahoo request occurs during replay.
9. Confirm the database count and SHA-256 remain unchanged after replay.
10. Capture one public-safe replay screenshot.

## Unavailable-feed evidence

Using existing deterministic behavior, capture or verify the UI’s unavailable-feed state while keeping it clearly distinguished from live Yahoo evidence. Do not manufacture or label constructed data as live.

## Verification and documentation

Run the relevant backend checks, `pip check`, frontend tests, ESLint, production build, `git diff --check`, and safety scans.

Update:

- `README.md` only if live status wording changes
- `docs/design-pipeline.md`
- `docs/verification.md`
- `handoffs/current.md`
- Add a public-safe evidence index if needed
- Save this supplemental checkpoint as `prompts/08a-part-4-1-live-evidence.md` without modifying instructor prompts

Record exact request/subscription counts, observed values, database evidence, screenshots, warnings, limitations, and whether replay of the captured session succeeded.

Stop all services created by this checkpoint and verify ports 8000 and 5173 are closed.

Stop before staging or committing. Report the exact changed files and final Git status.

## Checkpoint result

The restricted-shell preflight stopped at loopback access. The subsequent normal-PowerShell run used the single authorized Yahoo/AAPL subscription and saved 226 unique observations. The public live trace shows observation 193. Offline replay with the provider off matched its timestamps and close `358.1301`, with volume `Unavailable`. Replay made zero Yahoo requests or subscriptions, and the SQLite count and SHA-256 matched before and after. The constructed unavailable-feed check and the synthetic CSV practice data are separate evidence. See the [checkpoint results](../docs/verification.md#supplemental-prompt-08a---bounded-live-evidence), [live screenshot](../docs/evidence/08a-live-aapl-receipt.png), and [offline replay screenshot](../docs/evidence/08a-offline-yahoo-replay.png).
