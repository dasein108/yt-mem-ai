# SP4c Electron Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the SP4b React UI in an Electron desktop app that spawns the Python API as a managed sidecar, embeds per-video YouTube playback, and minimizes to the system tray.

**Architecture:** `vite-plugin-electron/simple` added to the existing `frontend/`. All spawn/readiness logic lives in a PURE `electron/lib.ts` (Vitest-tested); `electron/main.ts` is thin glue over it (build-checked, manual-smoke). The renderer gains a `WatchPlayer` (Electron `<webview>` / browser `<iframe>` split) tested with RTL. One backend change: permissive CORS on the localhost API so the packaged `file://` renderer can reach it.

**Tech Stack:** Electron, vite-plugin-electron, electron-builder, Vite/React/TS (SP4b), Vitest+RTL, and the Python FastAPI (SP4a) for the CORS change.

## Global Constraints

- **Mixed toolchain.** Task 1 is Python (gates: `uv run pytest -q`, `uv run --with ruff ruff check .`). Tasks 2–5 are Node under `frontend/` (gates: `npm --prefix frontend run typecheck|test|build|lint`). State which gates apply per task.
- Node/TS: `erasableSyntaxOnly` is on (no TS parameter-properties). `node_modules` gitignored + excluded from every `git add`. Electron install is a large download on first `npm install` — expected.
- **Pure/testable seam:** `electron/lib.ts` (`resolveApiCommand`, `waitForApi`) has no Electron/`child_process` imports — unit-tested offline. `electron/main.ts` imports Electron and is NOT unit-tested (verified by build + typecheck + a documented manual smoke).
- Renderer Electron detection is `window.electron?.isElectron` (from the preload's `contextBridge`); browser-first behavior is unchanged when absent.
- `<webview>` is not a default JSX element — declare it in an ambient `.d.ts` (no `any` leaks in components).
- Sidecar default: `uv run yt-ai serve --port <port>` from the repo root; `YT_API_CMD` / `YT_API_PORT` env override. Quit always kills the sidecar.
- Packaged renderer uses `VITE_API_BASE=http://127.0.0.1:8000` (absolute); dev keeps `/api` (Vite proxy). The API gets `CORSMiddleware(allow_origins=["*"])` (safe — 127.0.0.1-bound).
- Each task ends with its gates green and is committed (frontend commits exclude `node_modules`).

---

## File Structure

```
yt_summary/api/app.py           + CORSMiddleware (Task 1)
tests/test_api_reads.py         + CORS header test (Task 1)
frontend/
  electron/ main.ts  preload.ts  lib.ts  lib.test.ts     (Tasks 2–3)
  src/
    electron.d.ts                 (webview JSX + window.electron types)
    lib/electron.ts               isElectron()
    components/WatchPlayer.tsx  WatchPlayer.test.tsx
    components/VideoDetail.tsx     + Watch toggle
  vite.config.ts                  + vite-plugin-electron
  package.json                    + electron deps, main field, scripts, build config
  electron-builder.json           (Task 5)
  tsconfig.node.json              + electron/**/*.ts (typecheck coverage)
```

---

## Task 1: API CORS (Python)

**Files:** `yt_summary/api/app.py`, `tests/test_api_reads.py`. **Gates:** pytest + ruff.

**Interfaces:** `create_app` mounts `CORSMiddleware(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`.

- [ ] **Step 1: Write the failing test (append to `tests/test_api_reads.py`)**

```python
def test_cors_header_present(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        r = client.get("/status", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_reads.py::test_cors_header_present -q`
Expected: FAIL (no `access-control-allow-origin` header)

- [ ] **Step 3: Add CORS in `yt_summary/api/app.py`**

Add the import and, right after `app = FastAPI(lifespan=lifespan)`:
```python
from fastapi.middleware.cors import CORSMiddleware
# ...
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
```

- [ ] **Step 4: Run tests + full sweep**

Run: `uv run pytest -q` → all PASS; `uv run --with ruff ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
git add yt_summary/api/app.py tests/test_api_reads.py
git commit -m "feat(api): permissive CORS for the packaged electron renderer"
```

---

## Task 2: electron/lib.ts — pure sidecar helpers

**Files:** `frontend/electron/lib.ts`, `frontend/electron/lib.test.ts`, `frontend/tsconfig.node.json` (add `electron/**/*.ts`). **Gates:** frontend `typecheck/test/lint/build`.

**Interfaces:**
- `resolveApiCommand(env, repoRoot) -> { command: string; args: string[]; cwd: string }`
- `waitForApi(url, fetchFn, opts?) -> Promise<boolean>`

- [ ] **Step 1: Ensure electron TS is type-checked**

In `frontend/tsconfig.node.json`, add `"electron/**/*.ts"` to `include` (alongside `vite.config.ts`). This makes `tsc -b` cover `electron/`.

- [ ] **Step 2: Write the failing test — `frontend/electron/lib.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { resolveApiCommand, waitForApi } from './lib'

describe('resolveApiCommand', () => {
  it('defaults to uv run yt-ai serve', () => {
    const c = resolveApiCommand({}, '/repo')
    expect(c).toEqual({ command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', '8000'], cwd: '/repo' })
  })
  it('honors YT_API_PORT', () => {
    expect(resolveApiCommand({ YT_API_PORT: '9001' }, '/repo').args).toContain('9001')
  })
  it('honors YT_API_CMD override', () => {
    const c = resolveApiCommand({ YT_API_CMD: 'python -m x' }, '/repo')
    expect(c).toEqual({ command: 'python', args: ['-m', 'x'], cwd: '/repo' })
  })
})

describe('waitForApi', () => {
  it('returns true on first ok response', async () => {
    const ok = (async () => ({ ok: true })) as unknown as typeof fetch
    expect(await waitForApi('u', ok, { attempts: 3, delayMs: 0 })).toBe(true)
  })
  it('returns false after attempts exhaust', async () => {
    let calls = 0
    const fail = (async () => { calls++; throw new Error('down') }) as unknown as typeof fetch
    expect(await waitForApi('u', fail, { attempts: 3, delayMs: 0 })).toBe(false)
    expect(calls).toBe(3)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm --prefix frontend run test -- lib.test`
Expected: FAIL (`Cannot find module './lib'`)

- [ ] **Step 4: Implement `frontend/electron/lib.ts`**

```ts
export interface ApiCommand { command: string; args: string[]; cwd: string }

export function resolveApiCommand(env: Record<string, string | undefined>, repoRoot: string): ApiCommand {
  if (env.YT_API_CMD) {
    const parts = env.YT_API_CMD.trim().split(/\s+/)
    return { command: parts[0], args: parts.slice(1), cwd: repoRoot }
  }
  const port = env.YT_API_PORT || '8000'
  return { command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', port], cwd: repoRoot }
}

export interface WaitOpts { attempts?: number; delayMs?: number }

export async function waitForApi(
  url: string, fetchFn: typeof fetch, opts: WaitOpts = {},
): Promise<boolean> {
  const attempts = opts.attempts ?? 30
  const delayMs = opts.delayMs ?? 500
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetchFn(url)
      if (res.ok) return true
    } catch {
      // API not up yet
    }
    if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs))
  }
  return false
}
```

- [ ] **Step 5: Run gates** (`test/typecheck/lint/build`) → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/electron/lib.ts frontend/electron/lib.test.ts frontend/tsconfig.node.json ':!frontend/node_modules'
git commit -m "feat(electron): pure sidecar helpers (resolveApiCommand, waitForApi)"
```

---

## Task 3: Electron infra — plugin, main, preload, tray, sidecar

**Files:** install deps; `frontend/vite.config.ts`, `frontend/electron/preload.ts`, `frontend/electron/main.ts`, `frontend/package.json`. **Gates:** frontend `typecheck/lint/build` (no unit test — `main.ts` is verified by build + manual smoke).

- [ ] **Step 1: Install Electron deps**

```bash
cd /Users/dasein/dev/yt_summary/frontend
npm install -D electron electron-builder vite-plugin-electron
```

- [ ] **Step 2: Add the plugin to `frontend/vite.config.ts`**

Import and add to `plugins`:
```ts
import electron from 'vite-plugin-electron/simple'
// ...
  plugins: [
    react(),
    electron({
      main: { entry: 'electron/main.ts' },
      preload: { input: 'electron/preload.ts' },
      renderer: {},
    }),
  ],
```

- [ ] **Step 3: `frontend/electron/preload.ts`**

```ts
import { contextBridge } from 'electron'

contextBridge.exposeInMainWorld('electron', {
  isElectron: true,
  platform: process.platform,
})
```

- [ ] **Step 4: `frontend/electron/main.ts`**

```ts
import { app, BrowserWindow, Tray, Menu, nativeImage } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveApiCommand, waitForApi } from './lib'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..') // frontend/dist-electron -> repo root
const port = process.env.YT_API_PORT || '8000'
const apiUrl = `http://127.0.0.1:${port}/status`

let win: BrowserWindow | null = null
let tray: Tray | null = null
let sidecar: ChildProcess | null = null
let isQuitting = false

function startSidecar(): void {
  const { command, args, cwd } = resolveApiCommand(process.env, repoRoot)
  sidecar = spawn(command, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' })
  sidecar.on('exit', (code) => console.log(`[sidecar] exited ${code}`))
}

function stopSidecar(): void {
  if (sidecar && !sidecar.killed) sidecar.kill()
  sidecar = null
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1280, height: 820,
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      webviewTag: true,
    },
  })
  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
  win.on('minimize', (e: Electron.Event) => { e.preventDefault(); win?.hide() })
  win.on('close', (e) => { if (!isQuitting) { e.preventDefault(); win?.hide() } })
}

function createTray(): void {
  tray = new Tray(nativeImage.createEmpty())
  tray.setToolTip('yt_summary')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show', click: () => win?.show() },
    { label: 'Quit', click: () => { isQuitting = true; stopSidecar(); app.quit() } },
  ]))
  tray.on('click', () => win?.show())
}

app.whenReady().then(async () => {
  startSidecar()
  const ready = await waitForApi(apiUrl, fetch, { attempts: 60, delayMs: 500 })
  createWindow()
  createTray()
  if (!ready) {
    win?.webContents.once('did-finish-load', () => {
      win?.webContents.executeJavaScript(
        "document.title = 'API failed to start — run: uv run yt-ai serve'")
    })
  }
})

app.on('before-quit', () => { isQuitting = true; stopSidecar() })
app.on('window-all-closed', () => { /* stay in tray; do not quit */ })
```
Note: with the tray + hide-on-close, `window-all-closed` intentionally does nothing (the app lives in the tray until Quit).

- [ ] **Step 5: `frontend/package.json` — main + scripts**

Add `"main": "dist-electron/main.js"`. Add scripts:
```json
    "electron:dev": "vite",
    "electron:build": "vite build && electron-builder"
```
(`vite` with the plugin auto-launches Electron in dev; `vite build` emits `dist/` + `dist-electron/`.)

- [ ] **Step 6: Verify build + typecheck**

```bash
npm --prefix frontend run typecheck   # covers electron/*.ts via tsconfig.node.json
npm --prefix frontend run lint
npm --prefix frontend run build        # emits dist/ + dist-electron/main.js + preload.mjs
npm --prefix frontend run test         # existing tests unaffected
```
All PASS. (Do NOT need to launch Electron here — build success + typecheck is the gate; launching is manual smoke in Task 5.) Report each.

- [ ] **Step 7: Commit**

```bash
git add frontend/vite.config.ts frontend/electron/main.ts frontend/electron/preload.ts frontend/package.json frontend/package-lock.json ':!frontend/node_modules'
git commit -m "feat(electron): main process, preload, tray, sidecar spawn"
```

---

## Task 4: Renderer — WatchPlayer + Watch toggle

**Files:** `frontend/src/electron.d.ts`, `frontend/src/lib/electron.ts`, `frontend/src/components/WatchPlayer.tsx`, `frontend/src/components/WatchPlayer.test.tsx`, `frontend/src/components/VideoDetail.tsx`. **Gates:** frontend `typecheck/test/lint/build`.

- [ ] **Step 1: `frontend/src/electron.d.ts`** (webview JSX + window.electron types)

```ts
import type { DetailedHTMLProps, HTMLAttributes } from 'react'

declare global {
  interface Window {
    electron?: { isElectron: boolean; platform: string }
  }
  namespace JSX {
    interface IntrinsicElements {
      webview: DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & { src?: string; allowpopups?: string }
    }
  }
}
export {}
```

- [ ] **Step 2: `frontend/src/lib/electron.ts`**

```ts
export function isElectron(): boolean {
  return typeof window !== 'undefined' && !!window.electron?.isElectron
}
```

- [ ] **Step 3: Write the failing test — `frontend/src/components/WatchPlayer.test.tsx`**

```tsx
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WatchPlayer } from './WatchPlayer'

afterEach(() => { delete (window as { electron?: unknown }).electron })

describe('WatchPlayer', () => {
  it('renders an iframe embed in the browser', () => {
    const { container } = render(<WatchPlayer videoId="abc" url="https://y/watch?v=abc" onClose={() => {}} />)
    const iframe = container.querySelector('iframe')
    expect(iframe).toBeTruthy()
    expect(iframe?.getAttribute('src')).toContain('/embed/abc')
  })
  it('renders a webview in electron', () => {
    ;(window as { electron?: unknown }).electron = { isElectron: true, platform: 'darwin' }
    const { container } = render(<WatchPlayer videoId="abc" url="https://y/watch?v=abc" onClose={() => {}} />)
    expect(container.querySelector('webview')).toBeTruthy()
    expect(container.querySelector('iframe')).toBeNull()
  })
  it('close button calls onClose', async () => {
    let closed = false
    render(<WatchPlayer videoId="abc" url="u" onClose={() => { closed = true }} />)
    screen.getByLabelText('close player').click()
    expect(closed).toBe(true)
  })
})
```

- [ ] **Step 4: `frontend/src/components/WatchPlayer.tsx`**

```tsx
import { isElectron } from '@/lib/electron'
import { Button } from './ui/button'

export function WatchPlayer({ videoId, url, onClose }: { videoId: string; url: string | null; onClose: () => void }) {
  const watchUrl = url ?? `https://www.youtube.com/watch?v=${videoId}`
  return (
    <div className="relative mb-4 aspect-video w-full overflow-hidden rounded-md border bg-black">
      <Button size="icon" variant="ghost" aria-label="close player"
        className="absolute right-1 top-1 z-10 bg-white/80" onClick={onClose}>✕</Button>
      {isElectron() ? (
        <webview src={watchUrl} className="h-full w-full" />
      ) : (
        <iframe className="h-full w-full" src={`https://www.youtube.com/embed/${videoId}`}
          title="player" allow="autoplay; encrypted-media" allowFullScreen />
      )}
    </div>
  )
}
```

- [ ] **Step 5: Add the Watch toggle to `frontend/src/components/VideoDetail.tsx`**

Import `useState`, `WatchPlayer`. Add `const [watching, setWatching] = useState(false)`. In the action row, add a Watch button:
```tsx
        <Button size="sm" variant="outline" onClick={() => setWatching((w) => !w)}>▶ Watch</Button>
```
And render the player above the summary section (inside the article, after the header/actions):
```tsx
      {watching && <WatchPlayer videoId={v.video_id} url={v.url} onClose={() => setWatching(false)} />}
```

- [ ] **Step 6: Run gates** (`test/typecheck/lint/build`) → PASS. Report the test count.

- [ ] **Step 7: Commit**

```bash
git add frontend/src ':!frontend/node_modules'
git commit -m "feat(ui): WatchPlayer (webview|iframe) + Watch toggle in detail"
```

---

## Task 5: electron-builder config + docs + final sweep

**Files:** `frontend/electron-builder.json`, `frontend/package.json` (build ref if needed), `frontend/README.md`, root `README.md`, `CLAUDE.md`.

- [ ] **Step 1: `frontend/electron-builder.json`**

```json
{
  "appId": "app.ytsummary.desktop",
  "productName": "yt_summary",
  "files": ["dist/**/*", "dist-electron/**/*"],
  "directories": { "output": "release" },
  "mac": { "target": "dmg" },
  "win": { "target": "nsis" },
  "linux": { "target": "AppImage" }
}
```
Ensure `electron:build` uses it (`electron-builder --config electron-builder.json`, or `"build"` key referencing it). Add `release/` to `frontend/.gitignore`.

- [ ] **Step 2: Verify the build (not full packaging)**

Run: `npm --prefix frontend run build` → emits `dist/` + `dist-electron/main.js` + `preload.mjs`. Report.
(Producing an installer via `electron-builder` downloads platform binaries and is slow/manual — do NOT run it in this task; document it as a manual step. `electron:dev` launching the real app is the manual smoke below.)

- [ ] **Step 3: Docs**

- `frontend/README.md`: add an "Electron desktop app" section — `npm run electron:dev` (auto-spawns `uv run yt-ai serve` and opens the window), tray behavior (minimize→tray, Quit exits + stops the sidecar), Watch plays in-app, `YT_API_CMD`/`YT_API_PORT` overrides, `npm run electron:build` (current-OS package, needs the electron-builder toolchain), and that cross-platform installers + signing are deferred.
- Root `README.md` + `CLAUDE.md`: SP4c note — Electron shell wraps the SP4b UI and manages the SP4a sidecar; the API now allows CORS for the packaged renderer.

- [ ] **Step 4: Manual smoke checklist (document in the report; NOT automated)**

State that a human should verify: `npm run electron:dev` → window loads the UI (sidecar auto-started), a video's **Watch** plays in-app, minimize hides to tray, tray→Show restores, Quit exits with no leftover `yt-ai serve` process (`pgrep -f "yt-ai serve"` empty).

- [ ] **Step 5: Final sweep**

Run: `npm --prefix frontend run typecheck && lint && test && build` → all PASS (report test count).
Run: `uv run pytest -q` → still green (Task 1's CORS test included). Report count.
Confirm `git status` shows no `node_modules`/`dist`/`release` staged.

- [ ] **Step 6: Commit**

```bash
git add frontend/electron-builder.json frontend/.gitignore frontend/README.md README.md CLAUDE.md
git commit -m "feat(electron): builder config + docs; finish SP4c"
```

- [ ] **Step 7: Report roadmap-memory update to the controller**

Report that the roadmap memory should mark SP4c (and SP4 overall) done: Electron shell over the SP4b UI + SP4a sidecar (auto-spawn `uv run yt-ai serve`, wait for `/status`, kill on quit), per-video Watch (`<webview>`/`<iframe>`), minimize-to-tray, CORS on the API, electron-builder config (current-OS package; cross-platform installers + PyInstaller bundling deferred).

---

## Self-Review Notes

- **Spec coverage:** CORS for the packaged renderer (T1), pure sidecar helpers tested (T2), Electron main/preload/tray/sidecar-spawn + vite-plugin-electron (T3), per-video Watch `<webview>`/`<iframe>` + toggle (T4), electron-builder config + docs + manual-smoke checklist + final sweep (T5). Bundling Python, cross-platform installers/signing, full YouTube browser, Playwright E2E all deferred per spec.
- **Placeholder scan:** none — every code step is complete. `main.ts` is intentionally not unit-tested (Electron runtime); its logic core (`resolveApiCommand`/`waitForApi`) IS tested in T2, and it's build+typecheck-gated + manual-smoke.
- **Toolchain correctness:** T1 uses pytest/ruff; T2–T5 use `npm --prefix frontend run *`; `electron/*.ts` is type-checked via `tsconfig.node.json` include; `<webview>` typed via `electron.d.ts` (no `any`). `node_modules`/`dist`/`release` gitignored + excluded from commits.
- **Type/name consistency:** `resolveApiCommand(env, repoRoot)` / `waitForApi(url, fetchFn, opts)` signatures match T2 tests and the T3 `main.ts` calls; `window.electron.isElectron` set by `preload.ts` and read by `isElectron()`; `WatchPlayer` props match its test and the `VideoDetail` call site.
- **Version correctness:** vite-plugin-electron/simple config + `VITE_DEV_SERVER_URL` dev/prod split + `dist-electron/main.js` main field grounded against current docs; preload emitted as `preload.mjs`.
