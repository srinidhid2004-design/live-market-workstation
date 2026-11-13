# Current handoff

## Checkpoint

Prompt 2 verification is complete and ready for student review. Both dependency sets were installed in approved normal PowerShell sessions and verified against the locks. The backend unittest passed, and the installed-Chrome SmokeTest passed after the Prompt 2C assertion correction. The endpoint, outage, recovery, console, and cleanup results are recorded in [verification](../docs/verification.md). The market-data pipeline in [design notes](../docs/design-pipeline.md) remains planned.

## Files and checks

- Created `README.md`, `AGENTS.md`, `docs/design-pipeline.md`, `docs/verification.md`, `handoffs/create-handoff.md`, and this handoff. Created empty `backend/` and `frontend/` directories.
- Copied the 20 numbered instructor prompts into `prompts/` and the synthetic sample into `prompts/data/sample-candles.csv`. All 21 SHA-256 hashes matched the archive. The numbered files are the originals.
- Confirmed the starting root was empty and outside Git. Verified the Windows tools, discovered a working base Python 3.14.7 despite the failed shell aliases, and verified SQLite with an in-memory round trip. Node.js, npm, npx, pip, and Corepack ran. No project-configured Python environment, dependency manifests, or lockfiles were found. See [verification](../docs/verification.md) for missing packages and exact checks.
- The final tree contained 27 files. The six new documents were nonempty, their file links resolved, and a second hash comparison confirmed the starter materials still matched the archive.
- Prompt 01a added `.gitignore`, [AI-USE.md](../AI-USE.md), and the student-added [governance prompt](../prompts/01a-project-governance-and-version-control.md). Updated the README, project instructions, design notes, verification log, and this handoff. The application directories remain empty and no project dependencies are installed.
- The foundation is committed at `474573e`. The active branch is `feature/assignment-4-part-1` and `main` points to the same commit. There are no staged changes or configured remotes.
- The approved dry run failed to resolve the PyPI hostname. Setup stopped with no Python lockfile, application source, frontend manifest, or running project services. See [verification](../docs/verification.md) for the command and exact error.

## Outstanding decisions and next task

- Review the complete Prompt 2 changes before authorizing a commit. The working tree has four modified documentation files and 14 untracked source, test, configuration, and dependency files. The index has no staged changes.
- Later design decisions include the candle interval and completion rule, stale-data threshold, provider volume mapping, replay order and pacing, and SQLite runtime file location. Keep the course disclosure current as tools or models change.

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
