# Current handoff

## Checkpoint

Prompt 01 established the project structure. Student-added Prompt 01a covers governance, AI disclosure, and the local Git baseline. Assignment 4 is cumulative. Part 4.1 will receive actual AAPL updates from Yahoo Finance, record observations to SQLite, aggregate UTC candles, expose history and live updates over FastAPI, and show the results in Vue with a replay mode. Parts 4.2 and 4.3 are deferred to their assigned checkpoints.

## Files and checks

- Created `README.md`, `AGENTS.md`, `docs/design-pipeline.md`, `docs/verification.md`, `handoffs/create-handoff.md`, and this handoff. Created empty `backend/` and `frontend/` directories.
- Copied the 20 numbered instructor prompts into `prompts/` and the synthetic sample into `prompts/data/sample-candles.csv`. All 21 SHA-256 hashes matched the archive. The numbered files are the originals.
- Confirmed the starting root was empty and outside Git. Verified the Windows tools, discovered a working base Python 3.14.7 despite the failed shell aliases, and verified SQLite with an in-memory round trip. Node.js, npm, npx, pip, and Corepack ran. No project-configured Python environment, dependency manifests, or lockfiles were found. See [verification](../docs/verification.md) for missing packages and exact checks.
- The final tree contained 27 files. The six new documents were nonempty, their file links resolved, and a second hash comparison confirmed the starter materials still matched the archive.
- Prompt 01a added `.gitignore`, [AI-USE.md](../AI-USE.md), and the student-added [governance prompt](../prompts/01a-project-governance-and-version-control.md). Updated the README, project instructions, design notes, verification log, and this handoff. The application directories remain empty and no project dependencies are installed.
- The local repository is on `main` and awaits its first commit. Staging the 30 foundation files was blocked when Git could not write `.git/index.lock`. The candidate is on disk and the index is empty. No remote is configured. Git identity keys are unset and will need the student's chosen configuration before a commit. See [verification](../docs/verification.md) for the Git and starter-file checks.

## Outstanding decisions and next task

- Stage the reviewed foundation files from a shell with write access to Git metadata and rerun the index checks before any commit.
- Select the backend environment and compatible dependency versions when implementation is authorized. The discovered base interpreter works for the checks above. Obtain student approval before creating an environment, installing anything, or creating or changing dependency files.
- Later design decisions include the candle interval and completion rule, stale-data threshold, provider volume mapping, replay order and pacing, and SQLite runtime file location. Keep the course disclosure current as tools or models change.
- When the student authorizes Prompt 2, follow [the instructor's connection prompt](../prompts/02-connect-vue-and-fastapi.md) to verify a local Vue-to-FastAPI health request and recovery after the backend stops. Live Yahoo receipt, application storage, replay, and browser checks remain pending implementation.
