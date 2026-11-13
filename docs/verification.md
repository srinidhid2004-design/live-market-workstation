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
