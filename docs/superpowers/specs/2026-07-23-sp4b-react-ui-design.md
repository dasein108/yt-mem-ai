# SP4b — React UI Design

**Date:** 2026-07-23
**Status:** Approved (brainstorming complete)
**Part of:** SP4 Frontend (SP4a API ✓ → **SP4b React UI** → SP4c Electron shell).
**Consumes:** the SP4a local FastAPI.

## Vision

A browser-first React UI over the SP4a API that drives the core loop: browse the
video library, read summaries/highlights/Q&A, run semantic search, and trigger +
track the pipeline jobs (fetch / discover / fetch-pending / summarize). Built
browser-first (Vite dev server → proxied FastAPI) so the UX is validated before
wrapping it in Electron (SP4c).

## Locked Decisions

| Concern | Choice |
|---|---|
| Location | `frontend/` subdirectory (its own package.json / toolchain) |
| Stack | Vite + React + TypeScript |
| Data layer | TanStack Query (caching + job polling via `refetchInterval`) |
| Routing | React Router (`/`, `/videos/:id`) |
| Styling | Tailwind CSS + shadcn/ui (Radix components) |
| API connection | Vite dev-proxy `/api` → `http://127.0.0.1:8000`; base from `VITE_API_BASE` (default `/api`) |
| Layout | master-detail (list left, detail right) + persistent bottom JobStrip |
| Job progress | **indeterminate** (queued/running/done + spinner) — the API has no %-progress |
| Search UX | top search box **replaces** the left list with semantic hits (no separate route) |
| MVP scope | Library + Detail + Search + Jobs; **Recommend + Digest deferred** |
| Testing | Vitest + React Testing Library + MSW (mock API), `tsc --noEmit`, `npm run build`, ESLint |

## Architecture

```
frontend/
  package.json  vite.config.ts  tsconfig.json  tailwind.config.js  postcss.config.js
  index.html  .env.example (VITE_API_BASE=/api)
  src/
    main.tsx            React root + BrowserRouter + QueryClientProvider
    App.tsx             routes (AppShell wraps them)
    api/
      types.ts          TS types mirroring the API schemas (VideoOut, VideoDetail, SearchHit, Job, ...)
      client.ts         typed fetch wrappers over VITE_API_BASE (get/post helpers + endpoint fns)
      hooks.ts          TanStack Query hooks (queries + mutations)
    components/
      AppShell.tsx       top bar (search, +Add, Discover, Fetch-pending) + panes + JobStrip
      VideoList.tsx      list + StatusFilter; selecting → /videos/:id
      VideoDetail.tsx    metadata + transcript + summary/highlights/Q&A + like/dislike + Summarize
      SearchView.tsx     renders semantic hits into the left pane
      JobStrip.tsx       polls jobs, shows running spinner + recent outcomes
      AddDialog.tsx      URL → POST /jobs/fetch
      DiscoverDialog.tsx after/deep/min-duration → POST /jobs/discover
      ui/                shadcn primitives (button, dialog, input, table, badge, toast, ...)
    lib/utils.ts         cn() + formatting (MM:SS, dates)
  src/test/setup.ts      MSW server + jest-dom
  src/**/*.test.tsx      component tests
```

### API layer (`api/`)

- `types.ts` — hand-written TS mirrors of the pydantic schemas: `VideoOut`, `VideoDetail`
  (`+ transcript, summary`), `SearchHit`, `RecommendItem`, `Job`, `StatusCounts`.
- `client.ts` — `API_BASE = import.meta.env.VITE_API_BASE ?? "/api"`; typed functions:
  `listVideos({status?, since?})`, `getVideo(id)`, `getStatus()`, `search({q, mode?, k?})`,
  `sendFeedback({video_id, signal})`, `startFetch({url, force?})`, `startDiscover(body)`,
  `startFetchPending(body)`, `startSummarize({video_id})`, `getJob(id)`, `listJobs()`.
  Each does `fetch` + status check + typed JSON; throws a typed `ApiError` on non-2xx.
- `hooks.ts` — TanStack Query:
  - Queries: `useVideos(filters)`, `useVideo(id)`, `useStatus()`, `useSearch(q, mode)`
    (enabled when `q` non-empty), `useJobs()` with `refetchInterval` = 1000ms **while any job
    is queued/running**, else `false`.
  - Mutations: `useFeedback()`, `useStartFetch()`, `useStartDiscover()`, `useStartFetchPending()`,
    `useSummarize()` — on success, enqueue the job and invalidate `["jobs"]`.
  - A small effect/observer: when a job transitions to `done`, invalidate `["videos"]` and
    `["status"]` (and `["video", id]` for summarize) so the UI refreshes.

### Components

- **AppShell** — top bar with the search input (debounced; non-empty switches the left pane to
  `SearchView`), `+Add` / `Discover` / `Fetch-pending` buttons (open dialogs / fire mutations),
  the master-detail body (`VideoList` | `Outlet` for `VideoDetail`), and `JobStrip` pinned bottom.
- **VideoList** — `useVideos({status})`; a `StatusFilter` dropdown (all/discovered/downloaded/
  transcribed/summarized); rows show published date · title · status badge; row click →
  `navigate("/videos/:id")`; the selected row is highlighted.
- **VideoDetail** — `useVideo(id)`; shows title/url, the summary (markdown), highlights as
  `MM:SS — label`, Q&A; 👍/👎 buttons (`useFeedback`); a **Summarize** button (`useSummarize`)
  shown when `summary` is null; a transcript disclosure.
- **SearchView** — `useSearch(q)`; renders hits (`MM:SS · video · snippet`); click → the hit's video detail.
- **JobStrip** — `useJobs()`; shows each running job as `kind + spinner`, recent done/error jobs
  with a short result/error; a subtle badge with the running count.
- **AddDialog / DiscoverDialog** — shadcn `Dialog` + `Input`s; submit → the matching mutation; close on success.

### Data Flow

```
React ──/api──▶ Vite proxy ──▶ FastAPI (127.0.0.1:8000)
  useVideos/useVideo/useStatus/useSearch  → GET reads
  useFeedback                             → POST /feedback
  useStartFetch/Discover/FetchPending/Summarize → POST /jobs/* → JobStrip polls GET /jobs
  job done → invalidate videos/status/video queries → UI refreshes
```

### Error Handling

- `client.ts` throws `ApiError` (status + detail); hooks surface errors; components show an
  inline error state (toast for mutations, error text for queries). 404 on `/videos/:id` → a
  "not found" detail state.
- Job `error` status → the JobStrip shows the error message (red badge) and stops polling once
  no job is running.
- API unreachable (server not started) → a clear "API not reachable — run `yt-ai serve`" banner.

### Testing (offline via MSW)

- MSW handlers mock every endpoint with canned fixtures; `src/test/setup.ts` starts the server.
- `VideoList`: renders rows from mocked `/videos`; the StatusFilter changes the request/params.
- `VideoDetail`: renders summary/highlights/Q&A; 👍 fires `POST /feedback`; **Summarize** shown
  only when summary is null and fires `POST /jobs/summarize`.
- `SearchView`: typing a query renders mocked hits.
- `JobStrip`: with a mocked running job, shows the spinner; when it flips to `done`, the videos
  query is invalidated (assert a refetch / UI update).
- `AddDialog`: submitting a URL calls `POST /jobs/fetch`.
- `client.ts`: builds URLs from `VITE_API_BASE`; throws `ApiError` on non-2xx.
- Gates per task: `npx tsc --noEmit` (types), `npx vitest run` (tests), `npm run build` (bundles),
  `npm run lint` (ESLint). The Python suite/ruff are a separate toolchain and untouched.

## Documentation Updates

- `frontend/README.md`: setup (`npm install`, `npm run dev`), the `VITE_API_BASE` proxy, that it
  needs `yt-ai serve` running.
- Root `README.md`: a "Desktop UI (SP4b)" note pointing at `frontend/`.
- `CLAUDE.md`: add the `frontend/` structure + that it's browser-first React over the SP4a API,
  Electron wrapping deferred to SP4c.
- Roadmap memory: mark SP4b done.

## Out of Scope

- Recommend + Digest views (follow-up within SP4).
- Electron shell, system tray, embedded YouTube browser (SP4c).
- Determinate %-progress (needs progress plumbed into the run_* cores).
- Auth, multi-user, SSR, i18n, offline caching beyond TanStack Query defaults.
- Editing transcripts/summaries in-UI (read + trigger only).
