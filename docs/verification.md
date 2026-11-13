# Verification log

## Prompt 01 — Project structure and documentation

Checkpoint date: 2026-11-12 (Eastern time). The scope was the existing project root, the supplied instructor materials, and local read-only tool and dependency checks.

### Workspace and starter materials

| Command or check | Expected | Observed |
| --- | --- | --- |
| `Get-Location` and `Get-ChildItem -LiteralPath . -Force` | Selected root and its initial contents | Location matched the agreed root. The directory was empty before extraction. |
| `git --version` | Report the available Git version | Git 2.45.1.windows.1. |
| `git --no-optional-locks status --short --branch --untracked-files=all` and `git rev-parse --show-toplevel` | Identify repository status or confirm absence | Both reported that the root and its parent directories are outside a Git repository. |
| `Get-Item` and .NET `ZipFile.OpenRead` on the supplied archive | Identify the numbered prompt files and sample CSV | The archive contained 20 numbered Markdown prompts and `prompts/data/sample-candles.csv` beneath an archive wrapper, along with macOS metadata. The startup, connection, live-feed, and smoke-test prompts were inspected before documenting their roles. |
| `ZipFileExtensions.ExtractToFile` with overwrite disabled | Copy the numbered prompts and CSV directly into the root's `prompts/` hierarchy | Copied all 21 selected files. The archive wrapper and metadata were excluded. |
| `Get-FileHash -Algorithm SHA256` compared with SHA-256 of each ZIP entry stream | All 21 files match their original bytes | All 21 hashes matched. An inventory and metadata scan found exactly 21 files under `prompts/` and no macOS metadata in the project. |
| `Import-Csv -LiteralPath prompts/data/sample-candles.csv` | Parse the sample as candle data | Three synthetic rows with `timestamp,open,high,low,close,volume` headers and UTC timestamps from 14:30 through 14:32 on 2026-11-09. |
| Recursive PowerShell inventory of manifests, lockfiles, and interpreter markers | Identify project dependency declarations or environment configuration | Zero matches for Python and Node manifests, lockfiles, or markers such as `pyvenv.cfg`, `.python-version`, and `.nvmrc`. |

### Runtime and dependency checks

| Command or check | Expected | Observed |
| --- | --- | --- |
| `[Environment]::OSVersion.VersionString`, `RuntimeInformation.OSDescription`, `RuntimeInformation.OSArchitecture`, and `$PSVersionTable.PSVersion` | Identify the host OS, architecture, and shell | Windows NT 10.0.26300.0, x64, PowerShell 7.6.9. |
| `Get-Command` for `python`, `py`, `node`, `npm`, `npm.cmd`, `npx.cmd`, `pip`, `corepack`, `pnpm`, `yarn`, `bun`, `uv`, `conda`, and `rg` | Identify commands on PATH | Windows app aliases resolved for Python and its launcher. Node.js, npm, npx, pip, and Corepack resolved. pnpm, Yarn, Bun, uv, Conda, and ripgrep were unavailable on PATH. |
| `python --version`, `py -0p`, and `python -m pip --version` | Report the interpreter and pip through the default aliases | All three failed because Windows could not execute the aliases. |
| Probe standard local Python and Conda locations, activation variables, Python registry keys, and the runtime Python variable | Find another interpreter or a configured environment | `VIRTUAL_ENV`, `CONDA_PREFIX`, and `CODEX_PRIMARY_RUNTIME_PYTHON` were unset. Registry enumeration was denied. No project environment was identified. |
| `pip.exe --version` | Report the Python distribution behind the working pip launcher | pip 26.2.1 identified a local Python 3.14 base installation. The first path-discovery script failed when PowerShell did not populate its capture variable. A rerun using an explicit regex match found the executable. |
| `& $projectPython --version` and `& $projectPython -B -m pip --version` after discovery below | Start Python and verify pip against that exact interpreter | Python 3.14.7 and pip 26.2.1. `sys.prefix == sys.base_prefix` confirmed this is a base interpreter. |
| Python `-B` probe below | Import SQLite and check the packages needed by later prompts | SQLite 3.50.4 returned `1` from an in-memory write/read round trip. FastAPI, Uvicorn, yfinance, and `websockets` each raised `ModuleNotFoundError`. |
| `node --version`, `npm.cmd --version`, `npx.cmd --version`, and `corepack.cmd --version` | Report runnable frontend tools | Node.js v24.20.0, npm and npx 11.19.0, Corepack 0.35.0. |
| `node -e "for (const name of ['vue','vite','lightweight-charts']) { try { console.log(name, require.resolve(name)) } catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; console.log(name, 'not locally resolvable') } }"` | Find project-resolvable frontend packages if present | Vue, Vite, and Lightweight Charts were not locally resolvable. |

Run the interpreter probe from the project root in PowerShell. It discovers the local executable without storing a private path.

```powershell
$pipInfo = (pip.exe --version | Out-String).Trim()
$pipLocation = [regex]::Match($pipInfo, ' from (.+)\\Lib\\site-packages\\pip \(python')
if (-not $pipLocation.Success) { throw 'Could not identify the interpreter from pip' }
$projectPython = Join-Path $pipLocation.Groups[1].Value 'python.exe'
& $projectPython --version
& $projectPython -B -m pip --version
@'
import importlib
import importlib.metadata
import sqlite3
import sys

print("Active virtual environment:", sys.prefix != sys.base_prefix)
with sqlite3.connect(":memory:") as db:
    db.execute("CREATE TABLE probe (id INTEGER)")
    db.execute("INSERT INTO probe VALUES (1)")
    print("SQLite", sqlite3.sqlite_version, "round trip:", db.execute("SELECT id FROM probe").fetchone()[0])

for name in ("fastapi", "uvicorn", "yfinance", "websockets"):
    try:
        module = importlib.import_module(name)
    except ImportError as error:
        print(name, error)
    else:
        print(name, importlib.metadata.version(name))
        if name == "yfinance":
            print("yfinance.WebSocket callable:", callable(getattr(module, "WebSocket", None)))
'@ | & $projectPython -B -
```

### Final structure checks

| Command or check | Expected | Observed |
| --- | --- | --- |
| `tree.com /F /A` and PowerShell inventory | Six new Markdown files, 21 copied files, and empty backend and frontend directories | All 27 files and both empty directories were present. |
| `Get-Item`, `Get-Content -Raw`, and `Test-Path` against the six new documents and their relative Markdown file links | Nonempty documents, working links, and no embedded private Windows paths | All six documents passed. |
| Rerun the documented PowerShell interpreter probe and the archive SHA-256 comparison | Reproduce the runtime checks and confirm the copied files still match | Reproduced the Python, pip, SQLite, and missing-package results. All 21 files still matched the archive. |
| Repeat the Git status and manifest, lockfile, and environment-marker inventory | No Git repository or dependency declarations after setup | Git reported the expected absence of a repository with exit code 128. The first combined check surfaced that exit as a PowerShell error. The dedicated rerun validated the exit code and found zero manifest, lockfile, or environment-marker matches. |

### Remaining checks

- Prompt 2, after student authorization, should establish the local Vue–FastAPI connection. Check direct and proxied `/api/health` responses, verify the proxy fails when the backend stops, then verify recovery. Add tested startup and shutdown commands to the README.
- When the needed packages and features are available, check actual Yahoo Finance message receipt, SQLite persistence and replay, candle boundaries and volume semantics, feed unavailability and recovery, and browser-visible results. The documentation checkpoint required no application dependencies. A browser SmokeTest command is pending runnable UI and service entry points.

## Prompt 01a - Project governance, AI disclosure, and local Git baseline

Checkpoint date: 2026-11-12 (Eastern time). This student-added checkpoint documents the cumulative Assignment 4 sequence and prepares the Part 4.1 foundation for review. See [AI-USE.md](../AI-USE.md) for the disclosure and [Prompt 01a](../prompts/01a-project-governance-and-version-control.md) for the instructions. Its only workstation-specific path was replaced with a project-root reference for the staged record.

| Command or check | Expected | Observed |
| --- | --- | --- |
| `Get-Location`, `git --no-optional-locks rev-parse --show-toplevel`, and recursive inventory compared against the baseline | Exact project root, no enclosing repository, and only the existing foundation files | The root matched. Git returned exit 128 before initialization. The inventory matched the 27 expected files, with empty application directories and no runtime or generated artifacts. |
| SHA-256 comparison of local files against the supplied ZIP streams | 20 instructor prompts and one synthetic CSV match byte for byte | All 21 matched at preflight. |
| Repeat the documented Python probe and Node local module resolution | No project environment or application packages | The base interpreter and SQLite probe worked. FastAPI, Uvicorn, yfinance, and websockets did not import. Vue, Vite, and Lightweight Charts did not resolve locally. No project dependency was installed. |
| `git config --get user.name` and `git config --get user.email`, with values suppressed | Report configuration presence without printing identity | Both keys were unset in the effective Git configuration. Identity settings were untouched. |
| `git init -b main`, `git symbolic-ref --short HEAD`, `git remote`, `git rev-parse --verify --quiet HEAD`, and `git for-each-ref` | Local `main` with no commits, remotes, or other refs | Git initialized at the exact root. `main` is the initial branch awaiting its first commit. No remote or refs exist. |
| `git check-ignore --no-index` against sample path names | Ignore local output while allowing public-safe project files | 26 ignore cases and 19 allow cases passed, including SQLite sidecars, metadata, source, manifests and lockfiles, documentation, prompts, the CSV, blank `.env.example` paths, SQL initialization, and curated evidence. No probe files were created. |
| `git hash-object --no-filters` compared with the normal Git hash | Detect whether the current Git configuration would alter starter-file bytes | All 21 starter files produced the same raw and filtered hash. |
| `git add` with the 30 explicitly selected foundation paths | Populate the index for student review | Git could not create `.git/index.lock` under the workspace's read-only Git metadata permissions. The index remained empty. |
| Repeat the ZIP SHA-256 comparison, compare the full working-tree inventory, and scan candidate file contents | Exactly 30 intended files, with all starter bytes preserved and no credential-like values, private paths, or unexpected artifacts | The inventory matched. All 21 archive hashes matched again. The candidate content scan returned zero credential-like or private-path hits and found no trailing whitespace. Both application directories remained empty. |
| `git --no-optional-locks status --short --branch --untracked-files=all`, `git ls-files --stage`, and `git diff --cached --check` | Verify the complete staged candidate and check its whitespace | The status showed 30 untracked files and zero staged files. The cached diff check exited successfully on the empty index. The staged content, hash, and whitespace checks require a populated index. |

The checkpoint used local inspection, documentation edits, and Git commands. It created no application source, environment, dependency, runtime database, or network service and made no live Yahoo Finance request. Staging and verification of the populated index remain pending. Instructor Prompt 2 is the next implementation task after student authorization.

## Prompt 2 - Local Vue–FastAPI connection

Checkpoint date: 2026-11-12 (Eastern time). The student approved the exact package pins and project-local Python environment.

| Check | Expected | Observed |
| --- | --- | --- |
| Git branch, revision, status, and remotes | Clean `feature/assignment-4-part-1` at `474573e`, matching `main`, with zero remotes | Passed before setup. Both refs still point to `474573e` and the index is empty of staged changes. |
| Approved CPython executable with `-m venv --without-scm-ignore-files .\backend\.venv` | Project-local CPython 3.14.7 environment | Created successfully. The environment contains only bundled pip 26.2.1, and Git ignores it. |
| Binary-only dry run below | Resolve the approved packages and write a report inside the ignored environment | Exit 1. PyPI DNS resolution failed with `[Errno 11001] getaddrinfo failed`. pip then reported `No matching distribution found for fastapi==0.162.5` after receiving no package candidates. The report and lockfile were not created. Compatibility and dependency resolution remain unverified. |
| Check ports with `netstat -ano -p TCP` | No listeners on ports 8000 and 5173 following the setup stop | No listeners found on either port. |

```powershell
$venvPython = '.\backend\.venv\Scripts\python.exe'
& $venvPython -m pip install --dry-run --ignore-installed --only-binary=:all: --no-cache-dir --disable-pip-version-check --report .\backend\.venv\resolve.json -r .\backend\requirements.txt
```

Resume at the dry run once PyPI is reachable from the project shell. Then inspect the report and generate the Python lock before installing. Backend imports, `pip check`, the focused health test, npm resolution, lint, build, Playwright, production audit, and all HTTP and browser evidence remain pending. This attempt made no live market-data request.

### Prompt 2A - Bounded PyPI connectivity retry

Verified the expected worktree changes, empty index, feature branch and `main` at `474573e`, and unchanged instructor prompts. The existing environment reported CPython 3.14.7 and only `pip==26.2.1`. The four approved direct pins matched and ports 8000 and 5173 had no listeners.

The single probe attempted to resolve `pypi.org` with Python's `socket.getaddrinfo`, expecting DNS resolution followed by HTTP 200 from the official FastAPI metadata endpoint. DNS returned `gaierror` (Windows error 11001), so the probe skipped HTTPS. The dry run, lock generation, package installation, and application verification remain pending.

### Prompt 2B - Python verification and connection implementation

The explicitly authorized normal PowerShell installation used official PyPI after the project shell's DNS failures. The student reported that DNS succeeded and the official FastAPI 0.162.5 metadata endpoint returned HTTP 200. The project shell verified the resulting files and environment locally.

| Check | Expected | Observed |
| --- | --- | --- |
| Compare `backend/requirements.txt`, `backend/requirements.lock.txt`, the ignored resolution report, and installed metadata | Four approved direct pins, 17 resolved wheels, and no unexpected installed packages | All 17 installed application and test dependencies match the lock. The report lists wheels from the official PyPI file host, including Pydantic Core's CPython 3.14 Windows x64 wheel. Bundled pip remains 26.2.1. |
| Python version, imports, and `pip check` in `backend/.venv` | CPython 3.14.7, approved FastAPI/Uvicorn/Pydantic/HTTPX versions, consistent requirements | Passed. `pip check` reported `No broken requirements found.` |
| `python -B -m unittest discover -s tests -v` from `backend/`, using the local environment | Health test asserts HTTP 200, JSON content type, and exact body | The test started but produced no result before it was interrupted. It must be rerun. |
| `node --check` on the five frontend JavaScript files | Parse the entry point, configs, and browser test | All five passed. Vue compilation and lint are pending. |
| Approved npm install command in README | Resolve exact frontend pins and create `package-lock.json` | One attempt exited 1. DNS returned `getaddrinfo ENOTFOUND registry.npmjs.org` while requesting `@playwright/test`. The manifest and source are present. No lockfile or dependency directory was created. npm wrote its diagnostic log inside the ignored project cache. |
| Git and port checks | Same feature branch and baseline, empty index, no remote, ports 8000 and 5173 unused | Passed. No development server or browser was launched. |

Resume by running the README's npm installation command in normal PowerShell. Then run the backend test, frontend lint, build, production-only audit, and installed-Chrome SmokeTest. Direct and proxied response bodies, outage and recovery, and console results remain pending.

### Prompt 2 AutoLoop - Verification after manual npm installation

The student reported that the official npm registry returned HTTP 200, normal PowerShell installed 131 packages, and the production-only audit reported zero vulnerabilities. This checkpoint checked the resulting lock and local packages without making registry requests.

The seven direct pins matched the manifest, lockfile, and installed package metadata: `vue@3.5.44`, `vite@7.3.8`, `@vitejs/plugin-vue@6.0.4`, `eslint@9.39.5`, `eslint-plugin-vue@10.8.0`, `vue-eslint-parser@10.4.0`, and `@playwright/test@1.64.1`.

| Check | Expected | Observed |
| --- | --- | --- |
| Compare Python lock and installed metadata, import FastAPI/Uvicorn/Pydantic/HTTPX, and run `pip check` | 17 locked packages plus pip 26.2.1 on CPython 3.14.7, with consistent dependencies | All pins matched, all four imports passed, and pip reported `No broken requirements found.` |
| `node_modules\.bin\esbuild.cmd --version` | Installed esbuild executable runs | Exit 0, version 0.28.2, matching the JavaScript API version. The reported `node install.js` post-install script remains unapproved. |
| `npm.cmd run lint` | ESLint exits 0 with zero warnings | Passed. The npm support-window warning for ESLint 9.39.5 is an installation warning and did not affect lint. |
| `npm.cmd run build` | Vite exits 0 and produces `dist/` | Passed with Vite 7.3.8, 10 modules transformed, and HTML, CSS, and JavaScript produced. The build succeeded with the esbuild post-install script unapproved. |
| Focused backend unittest with a 12-second `faulthandler` deadline | Assert status 200, JSON content type, and exact response bytes | Timed out before reaching the test body. The stack stopped in Windows asyncio's self-pipe setup at `socket._fallback_socketpair` → `accept`. A separate bounded Python loopback probe returned `PermissionError` with Windows error 10013. |
| `npm.cmd run test:connection` | Vite becomes reachable, then installed Chrome verifies direct and proxied health, outage, recovery, and console | Playwright did not reach the browser assertions. The Vite web-server startup check did not become ready and the run was interrupted. A separate bounded Node loopback probe returned `EACCES` during connect. No HTTP response or browser console was observed. |
| `netstat -ano -p TCP`, `git status --short --ignored=matching`, and staged/tracked path checks | Both ports released and generated paths ignored, with nothing staged | No listeners on 8000 or 5173 after the interrupted run. The Python environment, npm cache, dependency directory, and build output were ignored. The index contained no staged changes and no generated files were tracked. |

AutoLoop ran one diagnostic pass and zero correction cycles. The backend hang occurred before application code ran, and independent Python and Node probes confirmed loopback access failures in the project shell. Application and test source were left as written. Run the focused backend test and the Chrome SmokeTest from normal PowerShell with loopback access to complete this checkpoint. The expected HTTP 200 body for both endpoints is `{"status":"healthy"}`.

### Prompt 2C - Windows backend-stop assertion

- Normal PowerShell backend unittest, as reported by the student. One test passed in 0.115 seconds with zero failures, including the exact response-body assertion.
- First Chrome SmokeTest in normal PowerShell, as reported by the student. Uvicorn started. Both `http://127.0.0.1:8000/api/health` and `http://127.0.0.1:5173/api/health` returned HTTP 200 with the exact body `{"status":"healthy"}`. Chrome showed the pending and healthy states.
- Immediately after the intentional backend stop, the direct request failed with `read ECONNRESET`. The assertion expected only `ECONNREFUSED`, so the run ended before the proxy outage, visible unavailable state, restart, recovery, and final console checks.
- AutoLoop cycle 1 changed only the post-shutdown assertion to `/ECONN(?:REFUSED|RESET)/`. On Windows, a fresh connection to the stopped server can be refused, while a connection the client reuses can be reset. The pre-start refusal check and all later outage, recovery, console, and cleanup assertions remain intact.
- `node --check frontend/tests/connection.spec.js` and `npm.cmd run lint` passed, with zero lint warnings. Playwright output paths are ignored. The restricted shell did not rerun the browser test. Full SmokeTest verification remains pending.

From the project root in normal PowerShell, run `npm.cmd --prefix .\frontend run test:connection`.

### Prompt 2D - Completed normal-PowerShell verification

The backend and browser results below are the student's normal-PowerShell evidence. Final local checks used the installed dependencies without registry or loopback requests.

| Check | Observed result |
| --- | --- |
| From `backend/`, run `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v` | `test_health_returns_exact_json` passed. One test ran in 0.115 seconds, result `OK`. The status, JSON content type, and exact response bytes matched. |
| From the root, run `npm.cmd --prefix .\frontend run test:connection` | One test passed using installed Chrome, in 11.1 seconds total and 4.8 seconds for the test itself. |
| Healthy path | Uvicorn started on `127.0.0.1:8000`. Both the direct `http://127.0.0.1:8000/api/health` and proxied `http://127.0.0.1:5173/api/health` requests returned HTTP 200 with the exact body `{"status":"healthy"}`. Chrome displayed the pending and healthy states. |
| Intentional outage | The test stopped FastAPI. Vite returned HTTP 500 and logged the expected upstream `ECONNREFUSED` messages. Chrome displayed `Backend unavailable.` and omitted the healthy JSON. |
| Recovery and console | The test restarted FastAPI. Both routes returned HTTP 200 and the exact healthy JSON again, and Chrome showed the healthy state. There were zero unexpected page or application-console errors and one expected failed-resource console error during the outage. |
| Cleanup | The immediate Windows listing showed closed, FIN_WAIT, and briefly retained socket states. The later bounded listening-socket query found no listeners on ports 8000 and 5173. Its process-owner query therefore returned no processes. |
| Local dependency checks | All 17 Python packages matched the lock, FastAPI/Uvicorn/Pydantic/HTTPX imports passed, and `pip check` reported no broken requirements. All seven approved frontend direct pins matched the manifest, lockfile, and installed tree. |
| Local syntax, lint, and build | Three Python files compiled in memory, five JavaScript files passed `node --check`, and the Vue single-file component parsed. `npm.cmd run lint` passed with zero warnings, and `npm.cmd run build` passed with 10 modules transformed. |
| esbuild and npm audit | The direct esbuild CLI returned 0.28.2. The production build passed with the reported `node install.js` post-install script still unapproved. The student's production-only npm audit reported zero vulnerabilities. npm's support-window warning for pinned ESLint 9.39.5 remains non-failing. |
| Final workspace checks | `git diff --check` and the untracked-file whitespace scan passed. All 20 instructor prompts and the sample CSV matched the starter archive by SHA-256. The credential and private-path scans found no matches in 44 tracked or review-candidate files. No SQLite database or sidecar was found, and the local verification made no Yahoo Finance request. The environment, npm cache, dependency tree, build output, Playwright output, and logs were covered by ignore rules. No generated files were staged or tracked. A local port inventory confirmed zero listeners on 8000 and 5173. |
| Final Git state | `feature/assignment-4-part-1` and `main` both point to `474573e`. There are no staged changes or remotes. The working tree has four modified documentation files and 14 untracked Prompt 2 files for review. |

#### Failed approaches and revisions for the curated evidence log

| Failed approach | Revision | Verified result |
| --- | --- | --- |
| Resolve PyPI and the npm registry from the restricted project shell. PyPI returned Windows DNS error 11001 and npm returned `ENOTFOUND`. | Use explicitly approved normal PowerShell sessions with official PyPI and npm. Retain the exact pins, binary-only Python lock, and npm lockfile. | Both installs succeeded. Local package metadata matched the locks and the approved direct pins. |
| Run the loopback-dependent tests in the restricted shell. The Python event loop stalled at socket setup and the Vite readiness check could not connect. | Run the backend unittest and installed-Chrome SmokeTest in normal PowerShell with loopback access. | The backend test passed, and Chrome reached the direct and proxied HTTP endpoints. |
| Expect only `ECONNREFUSED` immediately after deliberately stopping FastAPI. Windows returned `read ECONNRESET`. | Allow exactly the refusal and reset error codes on the post-shutdown direct-request assertion. A new socket can be refused and a reused socket can be reset. Keep the proxy, browser, recovery, console, and cleanup assertions. | The corrected Chrome run passed the complete outage and recovery flow and released both listening ports. |

Prompt 2 verifies local Vue–Vite–FastAPI HTTP connectivity. Yahoo Finance availability, live data, SQLite persistence, candlestick correctness, and WebSocket market streaming remain outside this checkpoint.

## Prompt 3 - Synthetic one-minute CSV history

The starting feature branch was clean at `0954655`. The project had no remote or SQLite file, and Prompt 2's passing health test and Chrome SmokeTest were documented. The instructor archive was verified before editing. This checkpoint made no Yahoo Finance request.

| Check | Observed result |
| --- | --- |
| SHA-256 of `prompts/data/sample-candles.csv` and `backend/data/sample-candles.csv` | Both files have SHA-256 `331afdd6729190444595cb8df1a02d3c213e16fc7521400797a110503df2dfa8`. The runtime fixture is a byte-for-byte copy. |
| From `backend/`, run `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_history.py -v -k HistoryLoaderTest` | Nine loader tests passed. They covered the sample, ordering, UTC normalization, duplicates, invalid timestamps, nonnumeric and nonfinite prices, invalid volume, impossible OHLC values, headers, and row width. |
| Compile Python sources in memory and import FastAPI, Uvicorn, Pydantic, HTTPX, and the app | Five Python files compiled, the imports passed, and FastAPI generated the history response schema. Direct handler checks confirmed the sample and the generic HTTP 500 detail for an unreadable file. |
| `.\.venv\Scripts\python.exe -B -m pip --disable-pip-version-check check` from `backend/` | No broken requirements found. |
| `npm.cmd run lint` and `npm.cmd run build` from `frontend/` | ESLint passed with zero warnings. Vite built successfully with 10 modules transformed. |
| Full backend unittest discovery with a 12-second diagnostic deadline | The restricted shell timed out in Windows asyncio's internal socket setup before the unchanged health test reached its assertions. The later normal-PowerShell run is recorded below. |
| Local TCP loopback probe | The restricted shell returned `PermissionError` with Windows error 10013. The later running HTTP check was performed in normal PowerShell. |
| Git, ignore, credential, private-path, and fixture checks | `git diff --check` and the untracked-file whitespace scan passed. Credential and private-path scans found no matches in 47 tracked or review-candidate files. All 20 instructor prompts and the source CSV still matched the starter archive by SHA-256. The backend fixture is eligible for tracking, and runtime output remains ignored. No SQLite files or port 8000 listener were found. The feature branch remains at `0954655` and `main` at `474573e`, with no staged changes or remote. |

The second row matched all six fixture values in the loader and the direct handler. Its inclusive UTC interval is `[14:31:00Z, 14:32:00Z)`.

| timestamp | open | high | low | close | volume |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2026-11-09T14:31:00Z` | 102 | 104 | 100 | 101 | 850 |

### Prompt 3A - Completed normal-PowerShell verification

The student ran the complete suite and verified both endpoints in normal Windows PowerShell 5.1. The results below are from that session.

| Check | Observed result |
| --- | --- |
| Complete backend unittest discovery | 12 tests passed in 0.667 seconds. This includes the unchanged health test, nine loader tests, the exact history field and type test, and the safe error test for missing and malformed files. An asyncio diagnostic reported that one task took 0.208 seconds. The task passed. |
| `GET /api/history` | HTTP 200 with exactly three candles in ascending timestamp order. Every field in every row matched the instructor CSV. |
| Second HTTP candle | `{"timestamp":"2026-11-09T14:31:00Z","open":102.0,"high":104.0,"low":100.0,"close":101.0,"volume":850}` |
| `GET /api/health` | HTTP 200 with exact body `{"status":"healthy"}`. |
| Cleanup | The test server stopped and a final query found no listener on port 8000. |
| Final local regression checks | Python syntax and imports passed for the five backend source and test files. `pip check` found no broken requirements. Nine focused loader tests passed in 0.145 seconds. Frontend ESLint passed with zero warnings and Vite built 10 modules successfully. |
| Repeatable command check | Windows PowerShell 5.1 parsed the full block below. Its comparison code accepted three matching fixture rows and rejected an incorrect second-row volume in an offline check. The successful running HTTP evidence is from the student session. |
| Final workspace checks | `git diff --check` passed. Credential and private-path scans found no matches in 47 files. All 20 instructor prompts and the source CSV still matched the starter archive, and both fixture copies still shared one SHA-256. No SQLite file or listener on port 8000 was found. The local checks made no Yahoo Finance request. Generated output remained ignored and untracked. |

#### Verification-command revisions

| First approach | Revised approach and result |
| --- | --- |
| An inline `python -c` wrapper contained nested quotes around the unittest arguments. Windows PowerShell 5.1 stripped the inner quotes when building the native command line. Python treated `unittest`, `discover`, and the other argument values as names and raised `NameError`. | Run `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v` directly from `backend/`. All 12 tests passed. |
| The HTTP comparison wrapped `$historyResponse.Content \| ConvertFrom-Json` in `@()`. Windows PowerShell 5.1 produced one nested array object, so the script counted one item. The HTTP response contained three candles. | Assign the decoded JSON directly to `$history` and compare the rows individually. The three rows and all six values of the second candle matched, and the listening port was released. |

Both issues were in the verification commands. The application and tests stayed as implemented in Prompt 3. The endpoint serves synthetic practice data. Live Yahoo Finance connectivity, SQLite persistence, candlestick charting, market-data WebSockets, and replay remain pending.

### Bounded normal-PowerShell check

Run this block from the project root in normal Windows PowerShell with loopback access. It runs the full backend suite and verifies both HTTP endpoints. It requires port 8000 to be free and stops only the Uvicorn process tree it starts.

```powershell
& {
    $ErrorActionPreference = 'Stop'

    function Get-HistoryListener {
        $connections = netstat.exe -ano -p TCP
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect local TCP listeners.' }
        $connections | Select-String -Pattern '^\s*TCP\s+\S+:8000\s+\S+\s+LISTENING\s+\d+\s*$'
    }

    if (Get-HistoryListener) { throw 'Port 8000 already has a listener.' }
    $fixture = @(Import-Csv -LiteralPath .\prompts\data\sample-candles.csv)
    if ($fixture.Count -ne 3) { throw 'Expected three instructor fixture rows.' }

    Push-Location .\backend
    $server = $null
    try {
        .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Backend unittest discovery failed.' }
        if (Get-HistoryListener) { throw 'Port 8000 already has a listener.' }

        $server = Start-Process -FilePath (Resolve-Path .\.venv\Scripts\python.exe).Path `
            -ArgumentList '-B', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
            -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru

        $healthUrl = 'http://127.0.0.1:8000/api/health'
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $healthResponse = $null
        do {
            if ($server.HasExited) { throw 'Uvicorn exited before becoming ready.' }
            try {
                $healthResponse = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            } catch {
                Start-Sleep -Milliseconds 200
            }
        } until ($healthResponse -or $clock.Elapsed.TotalSeconds -ge 10)

        if (-not $healthResponse) { throw 'Uvicorn did not become ready.' }
        if ($healthResponse.StatusCode -ne 200 -or $healthResponse.Content -cne '{"status":"healthy"}') {
            throw 'Health response did not match HTTP 200 and the exact JSON body.'
        }

        $historyResponse = Invoke-WebRequest -UseBasicParsing `
            -Uri 'http://127.0.0.1:8000/api/history' -TimeoutSec 2
        if ($historyResponse.StatusCode -ne 200 -or -not $historyResponse.Content.TrimStart().StartsWith('[')) {
            throw 'Expected HTTP 200 with a JSON array.'
        }
        $history = $historyResponse.Content | ConvertFrom-Json
        if ($history.Count -ne 3) { throw 'Expected three history candles.' }

        $culture = [Globalization.CultureInfo]::InvariantCulture
        $fields = 'close,high,low,open,timestamp,volume'
        for ($i = 0; $i -lt $fixture.Count; $i++) {
            $row = $history[$i]
            $expected = $fixture[$i]
            if ((($row.PSObject.Properties.Name | Sort-Object) -join ',') -cne $fields) {
                throw "Unexpected fields in row $($i + 1)."
            }
            if ($row.timestamp -cne $expected.timestamp -or
                ($i -gt 0 -and [string]::CompareOrdinal($history[$i - 1].timestamp, $row.timestamp) -ge 0)) {
                throw "Timestamp or order mismatch in row $($i + 1)."
            }
            foreach ($field in 'open', 'high', 'low', 'close') {
                if (($row.$field -isnot [ValueType]) -or $row.$field -is [bool] -or
                    $row.$field -ne [double]::Parse($expected.$field, $culture)) {
                    throw "Price mismatch for $field in row $($i + 1)."
                }
            }
            if (($row.volume -isnot [int] -and $row.volume -isnot [long]) -or
                $row.volume -ne [long]::Parse($expected.volume, $culture)) {
                throw "Volume mismatch in row $($i + 1)."
            }
        }
        if ($history[1].timestamp -cne '2026-11-09T14:31:00Z') {
            throw 'The second candle did not match the expected minute.'
        }

        "GET /api/history HTTP 200, three ordered rows match the fixture."
        $history[1] | ConvertTo-Json -Compress
        'GET /api/health HTTP 200 {"status":"healthy"}'
    } finally {
        try {
            if ($server -and -not $server.HasExited) {
                taskkill.exe /PID $server.Id /T /F | Out-Null
                if (-not $server.WaitForExit(5000)) { throw 'Uvicorn shutdown timed out.' }
            }
        } finally {
            Pop-Location
            if (Get-HistoryListener) { throw 'Port 8000 still has a listener.' }
            'Port 8000 released.'
        }
    }
}
```
