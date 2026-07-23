# yt_summary — Desktop UI (SP4b)

A browser-first React UI for the `yt_summary` local API. It's the MVP web
frontend for `yt-ai serve`, and the foundation for the Electron desktop app
planned in SP4c.

## Stack

Vite + React + TypeScript, TanStack Query for data fetching/caching, Tailwind
+ a few shadcn-style primitives (`src/components/ui`) for layout, and MSW for
offline component/hook tests.

## Setup

```bash
npm install
npm run dev
```

This starts Vite on **http://localhost:5173**. The dev server proxies
`/api/*` to `http://127.0.0.1:8000` (see `vite.config.ts`), stripping the
`/api` prefix before forwarding — so the app always talks to `/api/...` and
never needs to know the backend's real host/port.

For live data, run the backend first, in the repo root:

```bash
yt-ai serve   # localhost-only FastAPI server, defaults to 127.0.0.1:8000
```

Without it running, the UI loads but requests fail (no mock fallback outside
of tests).

If you need to point at a different API origin (e.g. no Vite proxy, or a
non-default port), set `VITE_API_BASE` — it defaults to `/api`.

## Scripts

```bash
npm run dev         # Vite dev server on :5173, proxying /api -> 127.0.0.1:8000
npm run test        # vitest, offline via MSW (no backend needed)
npm run build       # tsc -b && vite build
npm run typecheck   # tsc -b (no emit check)
npm run lint        # eslint . --max-warnings 0
```

## Scope

This is an MVP: **Library** (list + status filter), **Detail** (summary,
highlights, Q&A, like/dislike, trigger Summarize), **Search** (replaces the
library pane), and a **Jobs** strip (fetch/discover/fetch-pending/summarize,
with polling). It talks to the read/write/job endpoints exposed by the SP4a
API (`/videos`, `/status`, `/search`, `/feedback`, `/jobs/*`).

**Deferred** (not in this UI yet):

- Recommend and Daily Digest views

## Electron desktop app (SP4c)

`frontend/electron/` wraps this UI in an Electron shell that manages the
local API as a sidecar process, so there's nothing to start by hand.

```bash
npm run electron:dev     # dev: Vite + Electron, auto-spawns the sidecar
npm run electron:build   # package a current-OS installer into release/
```

- **`electron:dev`** starts the Vite dev server and an Electron window
  pointed at it. On launch, the main process spawns `uv run yt-ai serve`
  (from the repo root) as a child process and polls `GET /status` until the
  API answers (or times out), then loads the UI. You do not need to run
  `yt-ai serve` yourself in this mode.
- **Tray behavior**: minimizing the window hides it to the system tray
  instead of closing it. The tray icon's **Show** menu item restores the
  window; **Quit** tears down the sidecar process (tree-killed on Windows so
  no orphaned Python process is left behind) and exits the app. Closing the
  window (the OS close button) also just hides to tray — only **Quit**
  fully exits.
- **Watch** plays a video's YouTube page in-app (`<webview>` in Electron,
  falls back to an `<iframe>` in the plain browser build) instead of
  opening a new tab.
- **Sidecar overrides**: set `YT_API_CMD` to override the spawned command
  (default resolves `uv run yt-ai serve` against the repo root) and
  `YT_API_PORT` to change the port the app spawns/polls (default `8000`).
- **`electron:build`** runs `vite build` then `electron-builder --config
  electron-builder.json`, producing a **current-OS-only** package (dmg on
  macOS, nsis on Windows, AppImage on Linux) under `frontend/release/`.
  Cross-platform installer generation, code signing/notarization, and
  bundling the Python backend into the package (so end users don't need
  `uv`/Python installed) are all deferred — today the packaged app still
  shells out to `uv run yt-ai serve` on the host machine.

### Manual smoke test

Not automated — after any change to `frontend/electron/*`, a human should
verify:

1. `npm run electron:dev` → the window loads the UI and the sidecar starts
   automatically (no manual `yt-ai serve`).
2. Open a video and click **Watch** → it plays in-app.
3. Minimize the window → it disappears to the tray, not the taskbar/dock.
4. Click **Show** on the tray menu → the window is restored.
5. Click **Quit** on the tray menu → the app exits and no sidecar process
   is left running: `pgrep -f "yt-ai serve"` should print nothing.
