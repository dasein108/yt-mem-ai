# Repo Split: Engine (`yt-ai`) + Desktop (`yt-ai-desktop`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single `yt_summary` repo into two GitHub repos — `yt-ai` (Python engine: CLI + skills, published to PyPI with tag-driven CI/CD and a `uvx` install bootstrap) and `yt-ai-desktop` (the React+Electron frontend, history preserved, consuming the engine over HTTP).

**Architecture:** The current repo *becomes* the engine repo (strip `frontend/`, repackage for PyPI). The `frontend/` subtree is extracted into a brand-new repo with its git history intact via `git filter-repo`. The two repos couple only over the local HTTP API (OpenAPI contract); the desktop app launches the engine as a sidecar via `uvx yt-ai serve`. MCP server + cross-agent installer are explicitly **deferred to a phase-2 plan** — this cut ships CLI + skills only.

**Tech Stack:** Python 3.11+, `hatchling` + `hatch-vcs` (version from git tags), `uv`/`uvx`, GitHub Actions + PyPI Trusted Publishing (OIDC), `git-filter-repo`, Vite+React+TS+Electron, `gh` CLI.

## Global Constraints

- Python floor: `requires-python = ">=3.11"` (copied verbatim from current `pyproject.toml`).
- PyPI dist name: `yt-ai` (verified FREE on PyPI 2026-07-25). Import/package dir stays `yt_summary/` — do **not** rename the package dir; dist name ≠ import name is intentional and avoids import churn across ~155 files.
- Console script name stays `yt-ai` (`yt_summary.cli:app`).
- GitHub owner: `dasein108`. Engine repo `dasein108/yt-ai`, desktop repo `dasein108/yt-ai-desktop`.
- License: MIT.
- Engine version source is git tags via `hatch-vcs` — never hand-edit a version string after this plan.
- `git-filter-repo` is already installed at `/opt/homebrew/bin/git-filter-repo`.
- `gh` is authenticated as `dasein108`.
- The working tree is clean at plan start (verified). If it is not, stop and commit/stash first.
- Do NOT push anything until Phase D. All earlier phases are local and reversible.

---

## Phase A — Safety backup

### Task A1: Bundle a full backup of the current repo

**Files:**
- Create: `/Users/dasein/dev/yt_summary-backup-2026-07-25.bundle`

- [ ] **Step 1: Verify clean tree**

Run: `cd /Users/dasein/dev/yt_summary && git status --porcelain`
Expected: empty output (no lines). If non-empty, STOP and resolve before continuing.

- [ ] **Step 2: Create a complete git bundle (all refs) as a restore point**

```bash
cd /Users/dasein/dev/yt_summary
git bundle create /Users/dasein/dev/yt_summary-backup-2026-07-25.bundle --all
```

- [ ] **Step 3: Verify the bundle is valid**

Run: `git bundle verify /Users/dasein/dev/yt_summary-backup-2026-07-25.bundle`
Expected: ends with `The bundle records a complete history.` and lists `refs/heads/main`.

> Recovery, if anything below goes wrong: `git clone /Users/dasein/dev/yt_summary-backup-2026-07-25.bundle /Users/dasein/dev/yt_summary-restored`.

---

## Phase B — Extract `yt-ai-desktop` (frontend, history preserved)

Do this BEFORE stripping `frontend/` from the engine — the extraction reads the full-history clone.

### Task B1: Filter-repo the frontend subtree into a new repo

**Files:**
- Create: `/Users/dasein/dev/yt-ai-desktop/` (new working tree, frontend contents at root)

**Interfaces:**
- Produces: a git repo whose root is the former `frontend/` directory, with history limited to commits that touched `frontend/`. `frontend/.gitignore` is now the root `.gitignore`.

- [ ] **Step 1: Clone the current repo to the desktop path**

```bash
git clone /Users/dasein/dev/yt_summary /Users/dasein/dev/yt-ai-desktop
```
Expected: `Cloning into '/Users/dasein/dev/yt-ai-desktop'... done.`

- [ ] **Step 2: Rewrite history to keep only `frontend/`, moved to root**

```bash
cd /Users/dasein/dev/yt-ai-desktop
git filter-repo --path frontend/ --path-rename frontend/:
```
Expected: `Parsed N commits ... Completely finished after ...`. `git filter-repo` intentionally removes the `origin` remote.

- [ ] **Step 3: Verify the tree is now the frontend at root**

Run: `cd /Users/dasein/dev/yt-ai-desktop && ls`
Expected: contains `package.json`, `index.html`, `electron/`, `src/`, `vite.config.ts`, `electron-builder.json`, `.gitignore` — and NO `yt_summary/`, `tests/`, `pyproject.toml`.

- [ ] **Step 4: Verify history was preserved (not a single squashed commit)**

Run: `git log --oneline | wc -l`
Expected: a number > 1 (the frontend's real commit count). If it prints `1`, the filter failed — restore from bundle and retry.

- [ ] **Step 5: Commit marker (filter-repo already rewrote; nothing to commit yet)**

No commit here — the working tree matches HEAD after filter-repo. Proceed to B2.

### Task B2: Rebrand desktop package + point the sidecar at the published engine

**Files:**
- Modify: `/Users/dasein/dev/yt-ai-desktop/package.json` (name field)
- Modify: `/Users/dasein/dev/yt-ai-desktop/electron-builder.json` (appId, productName)
- Modify: `/Users/dasein/dev/yt-ai-desktop/electron/lib.ts:12`
- Modify: `/Users/dasein/dev/yt-ai-desktop/electron/lib.test.ts` (default-command assertion)

**Interfaces:**
- Produces: `resolveApiCommand(env, repoRoot)` default returns `{ command: 'uvx', args: ['yt-ai','serve','--port', port], cwd: repoRoot }` when `YT_API_CMD` is unset.

- [ ] **Step 1: Rename the npm package**

In `/Users/dasein/dev/yt-ai-desktop/package.json` change the name line:
```json
  "name": "yt-ai-desktop",
```
(was `"name": "frontend"`).

- [ ] **Step 2: Rebrand the Electron build metadata**

In `/Users/dasein/dev/yt-ai-desktop/electron-builder.json`:
```json
{
  "appId": "app.ytai.desktop",
  "productName": "yt-ai",
  "files": ["dist/**/*", "dist-electron/**/*"],
  "directories": { "output": "release" },
  "mac": { "target": "dmg" },
  "win": { "target": "nsis" },
  "linux": { "target": "AppImage" }
}
```
(was `appId "app.ytsummary.desktop"`, `productName "yt_summary"`).

- [ ] **Step 3: Change the sidecar default from `uv run` (source checkout) to `uvx` (published engine)**

In `/Users/dasein/dev/yt-ai-desktop/electron/lib.ts`, replace line 12:
```ts
  return { command: 'uvx', args: ['yt-ai', 'serve', '--port', port], cwd: repoRoot }
```
(was `{ command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', port], cwd: repoRoot }`). The `YT_API_CMD` override branch above is unchanged — a developer with a source checkout still sets `YT_API_CMD="uv run yt-ai serve"`.

- [ ] **Step 4: Find the test that asserts the old default**

Run: `cd /Users/dasein/dev/yt-ai-desktop && grep -n "uv'\|'run'\|resolveApiCommand" electron/lib.test.ts`
Expected: a line asserting `command` is `'uv'` and/or `args` starting with `'run'`.

- [ ] **Step 5: Update that assertion to the new default**

Edit the matching assertion in `electron/lib.test.ts` so it expects `command: 'uvx'` and `args: ['yt-ai', 'serve', '--port', '8000']` (drop the leading `'run'`). Leave any `YT_API_CMD`-override test case unchanged.

- [ ] **Step 6: Install deps and run the electron unit tests**

```bash
cd /Users/dasein/dev/yt-ai-desktop
npm install
npm run test:electron 2>/dev/null || npx vitest run electron/lib.test.ts
```
Expected: the `resolveApiCommand` tests PASS. If the script name differs, discover it with `grep -n '"test' package.json`.

- [ ] **Step 7: Commit the rebrand**

```bash
cd /Users/dasein/dev/yt-ai-desktop
git add package.json electron-builder.json electron/lib.ts electron/lib.test.ts
git commit -m "chore(desktop): rebrand to yt-ai-desktop; sidecar defaults to uvx yt-ai serve

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task B3: Desktop README + CI

**Files:**
- Modify: `/Users/dasein/dev/yt-ai-desktop/README.md`
- Create: `/Users/dasein/dev/yt-ai-desktop/.github/workflows/ci.yml`

- [ ] **Step 1: Rewrite the README header + prerequisite**

Replace the top of `/Users/dasein/dev/yt-ai-desktop/README.md` (the `# yt_summary — Desktop UI (SP4b)` heading and intro paragraph) with:
```markdown
# yt-ai-desktop

Desktop UI (browser-first React + Electron) for the [`yt-ai`](https://github.com/dasein108/yt-ai)
engine. In dev it proxies to a locally running `yt-ai serve`; the packaged
Electron app launches the engine as a sidecar via `uvx yt-ai serve`.

## Prerequisite

Install the engine so the sidecar can start:

```bash
uvx yt-ai --help        # zero-install run of the published engine
# or from a source checkout, override the sidecar:
#   YT_API_CMD="uv run yt-ai serve" npm run electron:dev
```
```
Keep the rest of the existing README (Stack / Setup / scripts) below this.

- [ ] **Step 2: Add a Node CI workflow**

Create `/Users/dasein/dev/yt-ai-desktop/.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run lint --if-present
      - run: npx vitest run
      - run: npm run build
```

- [ ] **Step 3: Verify the build works locally**

```bash
cd /Users/dasein/dev/yt-ai-desktop
npm run build
```
Expected: `tsc -b` passes and `vite build` writes `dist/`. If TypeScript errors reference paths that assumed a `frontend/` prefix, fix them (there should be none — the subtree was self-contained).

- [ ] **Step 4: Commit**

```bash
cd /Users/dasein/dev/yt-ai-desktop
git add README.md .github/workflows/ci.yml
git commit -m "docs+ci(desktop): README for standalone repo; add Node CI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Convert the current repo into the engine `yt-ai`

Operate in `/Users/dasein/dev/yt_summary` (this repo becomes `yt-ai`).

### Task C1: Remove the frontend subtree from the engine

**Files:**
- Delete: `/Users/dasein/dev/yt_summary/frontend/` (tracked files)

- [ ] **Step 1: Remove tracked frontend files**

```bash
cd /Users/dasein/dev/yt_summary
git rm -r frontend
```
Expected: `rm 'frontend/...'` for ~65 files.

- [ ] **Step 2: Remove any leftover untracked frontend artifacts (node_modules etc.)**

```bash
cd /Users/dasein/dev/yt_summary
rm -rf frontend
```
Expected: no output; directory gone.

- [ ] **Step 3: Verify the engine still imports and tests still pass (frontend removal must not affect Python)**

```bash
cd /Users/dasein/dev/yt_summary
uv run pytest -q
```
Expected: the full offline suite PASSES (same as before the split — frontend was never a Python dependency).

- [ ] **Step 4: Commit the removal**

```bash
cd /Users/dasein/dev/yt_summary
git commit -m "chore: extract frontend into yt-ai-desktop repo

Frontend history preserved in dasein108/yt-ai-desktop via git filter-repo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task C2: Repackage `pyproject.toml` for PyPI + hatch-vcs

**Files:**
- Modify: `/Users/dasein/dev/yt_summary/pyproject.toml`
- Create: `/Users/dasein/dev/yt_summary/LICENSE`

**Interfaces:**
- Produces: a buildable dist named `yt-ai` whose version comes from git tags (`hatch-vcs`). Console script `yt-ai` unchanged.

- [ ] **Step 1: Replace `pyproject.toml` with the packaged form**

Full new content of `/Users/dasein/dev/yt_summary/pyproject.toml`:
```toml
[project]
name = "yt-ai"
dynamic = ["version"]
description = "Local-first YouTube AI CLI: download, transcribe (captions -> whisper), embed in LanceDB, discover subscriptions, and summarize/highlight/Q&A."
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
authors = [{ name = "dasein" }]
keywords = ["youtube", "transcription", "whisper", "lancedb", "summarization", "cli", "ai"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Topic :: Multimedia :: Video",
  "Topic :: Text Processing :: Linguistic",
]
dependencies = [
    "typer>=0.12",
    "yt-dlp>=2024.8",
    "youtube-transcript-api>=1.0",
    "faster-whisper>=1.0",
    "python-dotenv>=1.0",
    "lancedb>=0.15",
    "sentence-transformers>=3.0",
    "openai>=1.40",
    "numpy>=1.26",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "httpx>=0.27"]

[project.urls]
Homepage = "https://github.com/dasein108/yt-ai"
Repository = "https://github.com/dasein108/yt-ai"
Issues = "https://github.com/dasein108/yt-ai/issues"

[project.scripts]
yt-ai = "yt_summary.cli:app"

[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.targets.wheel]
packages = ["yt_summary"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Add the MIT LICENSE**

Create `/Users/dasein/dev/yt_summary/LICENSE`:
```
MIT License

Copyright (c) 2026 dasein

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Sync deps with the new build backend**

```bash
cd /Users/dasein/dev/yt_summary
uv sync --extra dev
```
Expected: resolves and installs; no build-backend error. `hatch-vcs` will derive a dev version from git (e.g. `0.1.dev…`) since no tag exists yet — that is fine.

- [ ] **Step 4: Verify the console script still runs**

```bash
cd /Users/dasein/dev/yt_summary
uv run yt-ai --help
```
Expected: Typer help for `yt-ai` with the usual subcommands (`fetch`, `discover`, `serve`, `show`, …).

- [ ] **Step 5: Verify a wheel actually builds and reports a version**

```bash
cd /Users/dasein/dev/yt_summary
uv build
ls dist/
```
Expected: `dist/` contains `yt_ai-<version>-py3-none-any.whl` and a `.tar.gz`. The `<version>` is git-derived (non-empty). If the build errors with "unable to determine version", ensure the repo has at least one commit (it does) — hatch-vcs falls back to `0.0.0` only when history is truly empty.

- [ ] **Step 6: Commit packaging**

```bash
cd /Users/dasein/dev/yt_summary
git add pyproject.toml LICENSE
git commit -m "build: package as PyPI dist 'yt-ai' with hatch-vcs tag versioning

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task C3: Install bootstrap scripts (`uvx yt-ai`)

**Files:**
- Create: `/Users/dasein/dev/yt_summary/install.sh`
- Create: `/Users/dasein/dev/yt_summary/install.ps1`

- [ ] **Step 1: POSIX bootstrap**

Create `/Users/dasein/dev/yt_summary/install.sh`:
```sh
#!/bin/sh
# yt-ai installer bootstrap (POSIX).
# Usage: curl -LsSf https://raw.githubusercontent.com/dasein108/yt-ai/main/install.sh | sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
  echo "yt-ai: installing uv (provides Python + uvx)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "yt-ai: uvx not found on PATH after installing uv." >&2
  echo "Add uv's bin dir to PATH (usually ~/.local/bin) and re-run." >&2
  exit 1
fi

# uvx caches resolved versions; clear ours so this run picks up the latest release.
echo "yt-ai: fetching the latest published version..."
uv cache clean yt-ai >/dev/null 2>&1 || true

VERSION=$(uvx --refresh-package yt-ai --from yt-ai \
  python -c "import importlib.metadata as m; print(m.version('yt-ai'))" 2>/dev/null || true)
if [ -n "$VERSION" ]; then
  echo "yt-ai: installed version $VERSION"
else
  echo "yt-ai: installed the latest version"
fi

echo "yt-ai: ready. Run it with:"
echo "  uvx yt-ai --help"
echo "  uvx yt-ai serve        # start the local API for yt-ai-desktop"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x /Users/dasein/dev/yt_summary/install.sh
```

- [ ] **Step 3: PowerShell bootstrap**

Create `/Users/dasein/dev/yt_summary/install.ps1`:
```powershell
# yt-ai installer bootstrap (Windows PowerShell).
# Usage: irm https://raw.githubusercontent.com/dasein108/yt-ai/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "yt-ai: installing uv (provides Python + uvx)..."
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "yt-ai: fetching the latest published version..."
uv cache clean yt-ai *> $null

Write-Host "yt-ai: ready. Run it with:"
Write-Host "  uvx yt-ai --help"
Write-Host "  uvx yt-ai serve        # start the local API for yt-ai-desktop"
```

- [ ] **Step 4: Smoke-test the POSIX script locally (uv already installed here)**

```bash
sh /Users/dasein/dev/yt_summary/install.sh
```
Expected: prints "ready. Run it with:" and the two example commands. (It resolves `yt-ai` from PyPI; before the first release this may print "installed the latest version" without a number — acceptable.)

- [ ] **Step 5: Commit**

```bash
cd /Users/dasein/dev/yt_summary
git add install.sh install.ps1
git commit -m "feat: add install.sh / install.ps1 uvx bootstrap

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task C4: GitHub Actions — CI + tag-driven PyPI publish

**Files:**
- Create: `/Users/dasein/dev/yt_summary/.github/workflows/ci.yml`
- Create: `/Users/dasein/dev/yt_summary/.github/workflows/publish-pypi.yml`

- [ ] **Step 1: CI workflow (uv + ruff + pytest)**

Create `/Users/dasein/dev/yt_summary/.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --extra dev
      - name: Lint
        run: uv run ruff check .
      - name: Test (offline suite)
        run: uv run pytest -q
```

- [ ] **Step 2: Publish workflow (tag `v*` -> build -> Trusted Publishing)**

Create `/Users/dasein/dev/yt_summary/.github/workflows/publish-pypi.yml`:
```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
        with:
          # hatch-vcs needs full tag history to resolve the version.
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --extra dev
      - name: Run tests
        run: uv run pytest -q
      - name: Build distributions
        run: uv build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 3: Lint the workflow YAML locally (syntax sanity)**

```bash
cd /Users/dasein/dev/yt_summary
uv run python -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')];print('workflows OK')"
```
Expected: `workflows OK`. (If PyYAML is missing, install transiently: `uv run --with pyyaml python -c ...`.)

- [ ] **Step 4: Commit**

```bash
cd /Users/dasein/dev/yt_summary
git add .github/workflows/ci.yml .github/workflows/publish-pypi.yml
git commit -m "ci: add CI + tag-driven PyPI trusted-publishing workflows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task C5: Docs — README + CLAUDE.md + AGENTS.md parity contract

**Files:**
- Modify: `/Users/dasein/dev/yt_summary/README.md`
- Modify: `/Users/dasein/dev/yt_summary/CLAUDE.md`
- Create: `/Users/dasein/dev/yt_summary/AGENTS.md`

- [ ] **Step 1: Add an Install section to the top of README**

Insert immediately after the first heading in `/Users/dasein/dev/yt_summary/README.md`:
```markdown
## Install

```bash
# zero-install run (recommended)
uvx yt-ai --help

# or bootstrap uv + warm the cache
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-ai/main/install.sh | sh
```

The desktop UI lives in a separate repo: **[yt-ai-desktop](https://github.com/dasein108/yt-ai-desktop)**.
It talks to this engine over the local API (`yt-ai serve`).
```

- [ ] **Step 2: Point CLAUDE.md's frontend section at the new repo**

In `/Users/dasein/dev/yt_summary/CLAUDE.md`, replace the `- \`frontend/\` — SP4b desktop UI ...` module-map bullet (and its `frontend/electron/` continuation) with:
```markdown
- `frontend/` — **moved out** to the standalone repo
  [`yt-ai-desktop`](https://github.com/dasein108/yt-ai-desktop) (React+Vite+TS
  desktop UI + Electron wrapper). It consumes this engine only over the local
  HTTP API (`yt-ai serve`); the packaged app launches the engine as a sidecar
  via `uvx yt-ai serve`. This repo is the engine: CLI + API + skills, published
  to PyPI as `yt-ai`.
```

- [ ] **Step 3: Add the parity contract AGENTS.md**

Create `/Users/dasein/dev/yt_summary/AGENTS.md`:
```markdown
# Repository Instructions — yt-ai (engine)

This repo is the Python engine published to PyPI as `yt-ai`. The desktop UI is
a separate repo (`yt-ai-desktop`) that consumes this engine over the local HTTP
API only — never import Python across the boundary.

## Surface parity

When adding, changing, or removing a user-facing operation, keep every surface
in sync in the same change:

- Core logic in `yt_summary/` (single source of truth).
- CLI in `yt_summary/cli.py` (thin `run_*` cores over the same core).
- API routes in `yt_summary/api/` when the desktop UI needs it.
- Canonical skills in `skills/<name>/SKILL.md` (the `.claude/skills/<name>`
  symlinks are thin pointers — never duplicate the body).
- Tests in `tests/` (offline via the injectable seams; no network, no model
  downloads).

The CLI and API are thin adapters over the same core — do not fork logic into
either surface.

## Packaging

- Version comes from git tags via `hatch-vcs`. Do not hand-edit a version.
- Release = push a `v*` tag; `.github/workflows/publish-pypi.yml` builds and
  publishes via PyPI Trusted Publishing (OIDC, no stored token).

## Deferred (phase 2, not in this repo yet)

- `yt_summary/server.py` MCP server + `yt_summary/installer/` cross-agent
  config writer. When added, they become additional surfaces under "Surface
  parity" above and get their own `yt-ai-mcp` / `yt-ai-install` console scripts.
```

- [ ] **Step 4: Verify no other doc still describes frontend as in-repo**

Run: `cd /Users/dasein/dev/yt_summary && grep -rn "frontend/" README.md CLAUDE.md | grep -v "yt-ai-desktop"`
Expected: no output (every remaining `frontend/` mention is the pointer to the new repo). Fix any stragglers.

- [ ] **Step 5: Commit docs**

```bash
cd /Users/dasein/dev/yt_summary
git add README.md CLAUDE.md AGENTS.md
git commit -m "docs: engine README install section, point frontend to yt-ai-desktop, add AGENTS.md parity contract

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase D — Publish to GitHub + configure PyPI Trusted Publishing + first release

> This phase pushes to the network and publishes a package. Each push is outward-facing — do not skip the verification steps.

### Task D1: Create and push the desktop repo

**Files:** none (remote operations)

- [ ] **Step 1: Create the GitHub repo and push**

```bash
cd /Users/dasein/dev/yt-ai-desktop
gh repo create dasein108/yt-ai-desktop --public --source . --remote origin --push
```
Expected: repo created; `main` pushed. `gh repo view dasein108/yt-ai-desktop --web` opens it.

- [ ] **Step 2: Verify CI ran**

Run: `gh run list --repo dasein108/yt-ai-desktop --limit 3`
Expected: a `CI` run appears (queued/in-progress/completed). If it fails on lint, fix and push; the build must go green before relying on the sidecar contract.

### Task D2: Create and push the engine repo

**Files:** none (remote operations)

- [ ] **Step 1: Create the GitHub repo and push**

```bash
cd /Users/dasein/dev/yt_summary
gh repo create dasein108/yt-ai --public --source . --remote origin --push
```
Expected: repo created; `main` pushed with full history.

- [ ] **Step 2: Verify CI passed**

Run: `gh run list --repo dasein108/yt-ai --limit 3`
Expected: the `CI` workflow completes green (uv sync + ruff + pytest). If red, fix before releasing.

### Task D3: Configure PyPI Trusted Publishing (manual, one-time)

**Files:** none (done on pypi.org)

- [ ] **Step 1: Register the pending publisher on PyPI**

This is a manual browser step the user performs (credentials required — the agent must not attempt it):
1. Log in at https://pypi.org → *Your account* → *Publishing* → *Add a pending publisher*.
2. PyPI Project Name: `yt-ai`
3. Owner: `dasein108` · Repository: `yt-ai` · Workflow name: `publish-pypi.yml` · Environment: `pypi`
4. Save.

- [ ] **Step 2: Confirm the environment name matches the workflow**

Run: `grep -n "environment:" /Users/dasein/dev/yt_summary/.github/workflows/publish-pypi.yml`
Expected: `environment: pypi` — must exactly match the PyPI publisher's Environment field from Step 1.

> PAUSE: Do not proceed to D4 until the user confirms the pending publisher is saved on PyPI. Ask them explicitly.

### Task D4: Cut the first release (`v0.1.0`)

**Files:** none (tag + release)

- [ ] **Step 1: Tag and push**

```bash
cd /Users/dasein/dev/yt_summary
git tag v0.1.0
git push origin v0.1.0
```

- [ ] **Step 2: Watch the publish workflow**

Run: `gh run watch --repo dasein108/yt-ai $(gh run list --repo dasein108/yt-ai --workflow publish-pypi.yml --limit 1 --json databaseId -q '.[0].databaseId')`
Expected: the `Publish to PyPI` job completes green, ending on the publish step. If it fails at publish with a trusted-publishing error, re-check D3 (owner/repo/workflow/environment must match exactly).

- [ ] **Step 3: Confirm the release is live on PyPI**

Run: `curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/yt-ai/0.1.0/json`
Expected: `200`.

---

## Phase E — End-to-end verification

### Task E1: Fresh-machine simulation of the engine

**Files:** none

- [ ] **Step 1: Run the published engine with zero project context**

```bash
cd /tmp && uvx yt-ai --help
```
Expected: Typer help renders — proves the published wheel is self-contained and the console script resolves.

- [ ] **Step 2: Start the API the way the desktop app will**

```bash
cd /tmp && uvx yt-ai serve --port 8011 &
sleep 8
curl -s http://127.0.0.1:8011/status
kill %1
```
Expected: `/status` returns JSON. This is exactly the sidecar contract `yt-ai-desktop` relies on.

### Task E2: Desktop consumes the engine sidecar

**Files:** none

- [ ] **Step 1: Build the desktop app against the published engine**

```bash
cd /Users/dasein/dev/yt-ai-desktop
npm ci
npm run build
```
Expected: green build. (Full Electron packaging via `npm run electron:build` is a manual smoke test, not required here.)

- [ ] **Step 2: Final backup note**

The pre-split bundle `/Users/dasein/dev/yt_summary-backup-2026-07-25.bundle` remains the restore point for the engine's pre-split state. Keep it until both repos are confirmed healthy, then it may be deleted.

---

## Self-Review notes

- **Coverage:** engine repackaging (C2), install bootstrap (C3), CI/CD both repos (B3/C4/D), skills stay in-repo as canonical `skills/` + symlink pointers (no change needed — already correct), desktop extraction with history (B1), sidecar re-point (B2), PyPI trusted publishing (D3/D4), verification (E). MCP + cross-agent installer explicitly deferred and recorded in AGENTS.md.
- **Package dir vs dist name:** import package stays `yt_summary`; dist/CLI/repo are `yt-ai`. Consistent across C2 (`packages = ["yt_summary"]`, script `yt_summary.cli:app`) and all docs.
- **Version:** single source = git tags via hatch-vcs; no static version remains after C2.
- **No pushes before Phase D:** enforced by the constraint and phase ordering; every destructive/irreversible step is preceded by the Phase A bundle.

---

## REWORK ADDENDUM (revised boundary, 2026-07-25)

User revised the split boundary AFTER the initial engine/desktop cut (nothing pushed yet): the engine `yt-ai` becomes a **pure reusable library + data/pipeline CLI**; the **REST API (`api/`), the `serve` command, and the `yt-debugger` skill move to the desktop app**, which now depends on `yt-ai` via pip and reuses it.

**Engine `yt-ai` after rework:** `yt_summary/` MINUS `api/`; CLI MINUS `serve`; skills = yt, summarize-video, daily-digest, yt-manager (NOT yt-debugger); deps drop `fastapi`/`uvicorn`; no `dev.sh`. API tests removed.

**Desktop `yt-ai-desktop` after rework:** gains a Python backend package `backend/` (the moved `api/`, imports rewritten `..x` → `yt_summary.x`) + `yt-ai-desktop-serve` entrypoint, its own `pyproject.toml` (deps `yt-ai` + fastapi + uvicorn), the moved api pytest tests + `tests/support.py`, the `yt-debugger` skill, `dev.sh` (backend+vite), and the Electron sidecar re-pointed to `uv run yt-ai-desktop-serve`.

Executed as two rework tasks R1 (engine) and R2 (desktop); briefs in `.superpowers/sdd/brief-rework-*.md`.
