# PROMPT 01A — PROJECT GOVERNANCE, AI DISCLOSURE, AND LOCAL GIT BASELINE

Student-added supplemental prompt. The workstation-specific absolute path in the original is represented by the project root below.

Work only inside:

`live-market-workstation/` (the selected project root)

This is a supplemental project-safety checkpoint between the instructor’s
Prompt 1 and Prompt 2. Do not begin Prompt 2 and do not implement application
source code.

Read completely:

- AGENTS.md
- README.md
- docs/design-pipeline.md
- docs/verification.md
- handoffs/current.md
- prompts/01-generic-project-startup.md
- the Assignment 4 requirements already recorded in the project

## CHECK

Confirm:

- The selected folder is the exact project root.
- It is not currently inside another Git repository.
- backend/ and frontend/ remain empty.
- All 20 supplied instructor Markdown prompts and
  prompts/data/sample-candles.csv remain present.
- The copied instructor files still match the supplied ZIP byte for byte.
- No __MACOSX, .DS_Store, AppleDouble `._*`, credential, environment file,
  virtual environment, dependency directory, build output, database, cache,
  log, or generated application file exists.
- No dependency has been installed for the project.
- No live Yahoo Finance request has occurred.
- Git identity configuration is inspected without displaying unnecessary
  personal information. Do not invent or change identity settings.

If the root is already part of an unexpected repository, copied instructor
files have changed, or an unsafe/generated file exists, report it and stop.

## TAKE ACTION

1. Create a project-root `.gitignore` before any environment, dependency,
   database, or build output is created.

It must ignore at least:

- `.env` and environment variants containing credentials
- Python virtual environments
- Python bytecode and test/tool caches
- `node_modules`
- frontend build output
- SQLite runtime files, journals, WAL, and SHM files
- logs
- temporary files
- coverage output
- editor metadata
- `.DS_Store`
- `__MACOSX`
- AppleDouble `._*`
- operating-system metadata

It must continue allowing:

- Source code
- Dependency manifests and lockfiles
- Documentation
- Instructor and supplemental prompt records
- Synthetic public-safe fixtures
- Public-safe curated evidence
- `.env.example` templates containing blank values
- Explicit database initialization scripts

2. Create `AI-USE.md`.

Record:

- Codex is being used as the coding agent.
- ChatGPT is being used for planning, prompt review, and assignment guidance.
- The instructor supplied the numbered starter prompts.
- No application AI provider or model has been integrated yet.
- No live market request, trading action, model call, vision call, or audio
  session has occurred.
- Future changes in tools or models must be recorded with their purpose and
  the reason for the change.
- Generated work must be inspected, tested, and explained by the student.
- The final disclosure must distinguish coding assistance from application
  AI features introduced in later parts.

Do not include chat transcripts, credentials, account details, or private
absolute paths.

3. Update AGENTS.md only as needed to preserve these standing boundaries:

- Assignment 4.1 is observation, visualization, persistence, and replay.
- Do not implement Part 4.2 or Part 4.3 early.
- No real order execution.
- No financial advice or profitability claims.
- Keep live, synthetic, recorded, and replay data visibly distinct.
- Preserve source time, backend receipt time, identity, revisions, arrival
  order, and candle-completion state.
- Never fabricate live data, volume meaning, market freshness, or completion.
- Follow CHECK / TAKE ACTION / VERIFY for dependency changes.
- Show intended changes and verification evidence for student review before
  every commit.
- Preserve supplied instructor prompt files unchanged.

4. Save this complete prompt as:

prompts/01a-project-governance-and-version-control.md

Clearly label it as a student-added supplemental prompt, not an instructor
prompt.

5. Update:

- README.md
- docs/design-pipeline.md
- docs/verification.md
- handoffs/current.md

only where required to record:

- The Assignment 4 cumulative structure
- The Part 4.1 scope boundary
- The required AI/tool disclosure
- The current absence of application source and dependencies
- This supplemental checkpoint
- The next task: instructor Prompt 2

Preserve the distinction between implemented and planned behavior.

6. Initialize a local Git repository with `main` as the initial branch:

git init -b main

Do not create a GitHub repository, remote, commit, tag, or feature branch yet.

7. Stage only the intended public-safe foundation files so I can review the
initial commit candidate.

## VERIFY

Confirm:

- Active branch is `main`.
- There is no configured remote.
- All instructor prompt files and the sample CSV remain unchanged by SHA-256.
- `.gitignore` ignores representative test paths for:
  - `.env`
  - `.venv`
  - `node_modules`
  - `dist`
  - SQLite runtime files
  - WAL/SHM files
  - caches
  - logs
  - macOS metadata
- `.gitignore` does not ignore:
  - source files
  - requirements files
  - package manifests and lockfiles
  - documentation
  - prompt records
  - sample-candles.csv
  - `.env.example`
- No credential-like value or private absolute path is staged.
- No generated/runtime file is staged.
- backend/ and frontend/ remain empty.
- No application dependency, environment, source file, database, or network
  service was created.
- `git diff --cached --check` passes.
- The staged file list is complete and expected.

Report:

- Active branch
- Git identity status without exposing unnecessary personal information
- Exact staged files
- `.gitignore` verification
- Instructor-file hash verification
- Credential/private-path scan
- `git diff --cached --check`
- Any unresolved issue

STOP before committing or pushing. Show the staged change summary for my
review. Do not begin instructor Prompt 2.
