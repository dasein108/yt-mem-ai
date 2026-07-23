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
- The Electron desktop wrapper (SP4c) — this app is currently browser-only
