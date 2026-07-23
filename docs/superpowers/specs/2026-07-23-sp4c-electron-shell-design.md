# SP4c — Electron Shell Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Part of:** SP4 Frontend (SP4a API ✓ → SP4b React UI ✓ → **SP4c Electron shell**).
**Wraps:** the SP4b React UI + spawns the SP4a API.

## Vision

Wrap the browser-first React UI in a cross-platform Electron desktop app: it
spawns the Python API as a managed sidecar, embeds YouTube playback for the
selected video, and minimizes to the system tray — completing the desktop app.

## Locked Decisions

| Concern | Choice |
|---|---|
| Integration | `vite-plugin-electron/simple` added to the existing `frontend/` (no restructuring; React stays the renderer) |
| API sidecar | Electron main spawns `uv run yt-ai serve` (from the repo root; command overridable via env); waits for `/status`; kills on quit |
| Embedded YouTube | "Watch" per video: Electron `<webview>` (full watch URL) in the app, `<iframe>` embed fallback in the browser |
| Tray | minimize/close hides to tray; tray menu Show/Quit; real Quit kills the sidecar |
| Security | `contextIsolation: true`, preload via `contextBridge`; `webviewTag: true` for the player |
| Packaging | `electron-builder` config + current-OS package; cross-platform installers + signing deferred |
| Testing | pure main-process helpers (Vitest) + renderer bits (RTL/MSW); the live app is manual smoke (no Playwright E2E) |

## Architecture

```
frontend/
  electron/
    main.ts       app lifecycle: sidecar spawn, window, tray
    preload.ts    contextBridge → window.electron { isElectron, ... }
    lib.ts        PURE helpers: resolveApiCommand(env), waitForApi(url, fetchFn, opts)
    lib.test.ts
  src/
    lib/electron.ts        isElectron() / useIsElectron()
    components/WatchPlayer.tsx   <webview> (Electron) | <iframe> (browser)
    components/WatchPlayer.test.tsx
    components/VideoDetail.tsx    + a Watch toggle rendering <WatchPlayer>
  vite.config.ts            + vite-plugin-electron (main + preload entries)
  package.json              + electron, electron-builder, vite-plugin-electron; scripts; build config
  electron-builder.json     appId + mac/win/linux targets + files
```

### electron/lib.ts (pure, testable)

- `resolveApiCommand(env) -> { command: string; args: string[]; cwd: string }` — default
  `{ command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', '8000'], cwd: <repo root> }`;
  `env.YT_API_CMD` (a shell string) overrides; `env.YT_API_PORT` overrides the port.
- `waitForApi(url, fetchFn, { attempts, delayMs }) -> Promise<boolean>` — polls `url` (default
  `http://127.0.0.1:8000/status`) via the injected `fetchFn`; resolves true on first 2xx, false
  after `attempts` fail. `fetchFn` injectable → offline test.
- Both are pure/injectable so `lib.test.ts` covers them without spawning anything.

### electron/main.ts (thin glue over lib.ts; not unit-tested)

- `app.whenReady()`: spawn the sidecar via `child_process.spawn(resolveApiCommand(process.env))`;
  `await waitForApi(...)`; create the `BrowserWindow` (`preload`, `contextIsolation: true`,
  `webviewTag: true`); load `process.env.VITE_DEV_SERVER_URL` (dev) or the built `index.html` (prod).
  If `waitForApi` fails, show a small error window ("API failed to start — check `uv run yt-ai serve`").
- **Tray:** create a `Tray` with an icon + menu (Show, Quit). `window.on('close')` (unless
  `app.isQuitting`) → `event.preventDefault()` + `window.hide()`; `window.on('minimize')` → hide.
  Tray click / "Show" → `window.show()`. "Quit" → set `isQuitting`, kill the sidecar, `app.quit()`.
- **Sidecar lifecycle:** keep the child ref; on `before-quit` / Quit, `child.kill()` (and on
  Windows, tree-kill if needed). Log sidecar stdout/stderr to the main console.

### electron/preload.ts

```ts
import { contextBridge } from 'electron'
contextBridge.exposeInMainWorld('electron', {
  isElectron: true,
  platform: process.platform,
})
```

### Renderer additions

- `src/lib/electron.ts`: `export const isElectron = () => typeof window !== 'undefined' && !!(window as any).electron?.isElectron`.
  (A typed `window.electron` via a `.d.ts` ambient declaration.)
- `WatchPlayer.tsx`: props `{ videoId, url }`. In Electron → `<webview src={url} className=... />`
  (full watch page, plays all videos). In browser → `<iframe src={`https://www.youtube.com/embed/${videoId}`} allow="autoplay; encrypted-media" allowFullScreen />`. A close button.
- `VideoDetail.tsx`: a **Watch** button toggles an inline `<WatchPlayer>` (below the header),
  using the video's `url` + `video_id`. Browser-first behavior unchanged when not watching.

### Data / Process Flow

```
electron:dev / packaged app
  main.ts → spawn `uv run yt-ai serve` (sidecar) → waitForApi(/status)
          → BrowserWindow loads the React UI (Vite dev URL | built files)
  renderer → /api (same-origin in prod via the loaded files hitting 127.0.0.1:8000; dev uses the Vite proxy)
  Watch → <webview> (Electron) plays the YouTube page in-app
  minimize/close → tray;  Quit → kill sidecar + exit
```

Note: in the packaged app the renderer is `file://`, so `VITE_API_BASE` must resolve to the
absolute API (`http://127.0.0.1:8000`) rather than the dev `/api` proxy. The build sets
`VITE_API_BASE=http://127.0.0.1:8000` for the Electron renderer build; browser-first dev keeps `/api`.

**CORS (required for the packaged app):** a `file://` origin calling `http://127.0.0.1:8000` is
cross-origin, so SP4c adds `CORSMiddleware(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`
to the SP4a FastAPI in `create_app`. This is safe because the server binds `127.0.0.1` only (not
reachable off-host). Dev (Vite proxy, same-origin `/api`) doesn't need it, but the middleware is
harmless there. This is the one backend change SP4c makes; add a small API test asserting the CORS
header is present.

### Error Handling

- Sidecar spawn fails / `uv`/`yt-ai` not found → `waitForApi` times out → error window with the
  actionable message; the app doesn't hang on a blank screen.
- Sidecar dies while running → the UI's existing "API not reachable" state shows; (auto-restart deferred).
- `<webview>` fails to load a video → the webview shows YouTube's own error; a "open in browser" link as fallback.
- Quit always kills the sidecar (no orphaned `yt-ai serve`).

### Testing (offline)

- `electron/lib.test.ts` (Vitest, node): `resolveApiCommand` default + `YT_API_CMD`/`YT_API_PORT`
  overrides; `waitForApi` returns true on a 2xx `fetchFn`, false after N failures, respects `attempts`.
- `WatchPlayer.test.tsx` (RTL): with `window.electron` set → renders a `<webview>` (assert the tag/src);
  without it → renders an `<iframe>` with the embed URL; the close button hides it.
- `VideoDetail` Watch toggle: clicking **Watch** mounts `<WatchPlayer>` (extend the existing test).
- Manual smoke (documented, not automated): `npm run electron:dev` spawns the sidecar, the window
  loads, Watch plays a video, minimize→tray→restore works, Quit leaves no `yt-ai serve` running.
- All four existing gates still pass (`typecheck/lint/test/build`); the electron main/preload are
  type-checked and built by the plugin.

## Documentation Updates

- `frontend/README.md`: `npm run electron:dev` (spawns the sidecar automatically), `electron:build`
  (current-OS package), the `YT_API_CMD`/`YT_API_PORT` env overrides, tray behavior, that Watch is
  in-app in Electron. Note cross-platform installers/signing are deferred.
- Root `README.md` + `CLAUDE.md`: SP4c note — Electron shell over the SP4b UI + SP4a sidecar.
- Roadmap memory: mark SP4c (and thus SP4) done.

## Out of Scope

- Bundling Python (PyInstaller) into the app — a distribution follow-up; the sidecar assumes `uv` + the repo.
- Cross-platform installers + code-signing / notarization (needs per-OS CI).
- A full in-app YouTube *browser* (address bar, navigation) — only per-video Watch.
- Auto-update, deep links, native menus beyond the tray, Playwright E2E.
- Recommend/Digest views (still deferred from SP4b).
