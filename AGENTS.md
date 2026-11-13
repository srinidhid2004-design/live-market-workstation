# Live Market Workstation instructions

- Work inside this project root, using the directory containing this file. Before editing, inspect relevant files, applicable instructions, and Git status if the folder is in a repository. Preserve existing work. Show the student the intended changes and verification evidence for review before every commit. Obtain separate authorization before initializing Git, creating a GitHub repository, committing, or pushing.
- Save each major prompt under `prompts/` if a copy is missing. Keep the instructor numbering, filenames, and contents intact. Record the prompt's observed results in `docs/verification.md`.
- Keep credentials, cookies, tokens, and other secrets out of source code, prompts, logs, and Git. Keep personal information, private paths, virtual environments, dependency directories, runtime SQLite files and sidecars, caches, logs, and build output out of Git. Use project-relative paths or local runtime discovery in shared documentation. This project uses a credential-free Yahoo Finance subscription.
- Assignment 4.1 covers educational market-data observation, visualization, persistence, and replay. Defer Parts 4.2 and 4.3 to their assigned checkpoints. Never execute real orders, give financial advice, or make profitability claims.
- Keep live, synthetic, recorded, and replay data visibly distinct. Preserve source time, backend receipt time, observation identity, revisions, arrival order, and candle-completion state. Never fabricate live data, volume meaning, market freshness, or candle completion.
- Maintain `AI-USE.md` as the course disclosure. Record tool or model changes with their purpose and reason, and distinguish coding assistance from application AI features.

## Tool and dependency procedure

### CHECK

Inspect the OS, active Python executable and environment, Node.js, package managers, dependency files, and lockfiles. Check which tools and packages already work. Reuse an existing Python environment when it is suitable and configured for this project. If none exists, report the finding and obtain student approval before creating or recreating one.

### TAKE ACTION

For each missing dependency needed for the current task, state its purpose, a compatible version, the exact installation command, the installation target, and every file the change would affect. Wait for explicit student approval before installing software or creating or changing a dependency manifest or lockfile.

### VERIFY

In the intended environment, run the smallest relevant version, import, or build check. Record the command, expected result, observed result, and remaining checks in `docs/verification.md`.

## SmokeTest

SmokeTest is a repeatable check that runs without source edits. Once a feature has a UI, SmokeTest starts the local services, waits for readiness, opens a browser, performs a user operation, and compares the visible result with the expected result. Check stored data when relevant, using an isolated test database for writes. Stop the browser and any services the test started. Document one command to run the test and log both passes and failures in `docs/verification.md`. Add the command when the first runnable UI check exists.

## AutoLoop

Inspect a failed check, make the smallest in-scope correction, and rerun the check. Stop on success, after five correction cycles, or as soon as further permission is needed. Record each result in `docs/verification.md`.
