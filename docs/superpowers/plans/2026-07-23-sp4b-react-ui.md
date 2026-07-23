# SP4b React UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser-first React UI in `frontend/` over the SP4a API — Library + Detail + Search + Jobs — with fully offline (MSW) component tests.

**Architecture:** Vite + React + TS. TanStack Query v5 for data + job polling. React Router for `/` and `/videos/:id`. Tailwind + hand-added shadcn-style primitives (Radix). A typed `api/client.ts` over `VITE_API_BASE` (default `/api`, Vite-proxied to `127.0.0.1:8000`). Every network call is mocked with MSW so tests run without a server. Master-detail layout with a persistent JobStrip.

**Tech Stack:** Node 22, Vite, React 18, TypeScript, @tanstack/react-query v5, react-router-dom v6, Tailwind, Radix Dialog, Vitest + Testing Library + MSW v2, ESLint.

## Global Constraints

- **Separate toolchain from Python.** All work is under `frontend/`. Gates are `npm run` scripts, NOT pytest/ruff. Run them with `npm --prefix frontend run <script>` (or `cd frontend && ...`).
- Per-task gates (all must pass): `npm --prefix frontend run typecheck` (`tsc --noEmit`), `npm --prefix frontend run test` (`vitest run`), `npm --prefix frontend run build` (`vite build`), `npm --prefix frontend run lint` (ESLint). Early tasks that have no tests yet still must pass typecheck + build + lint.
- **TanStack Query v5 object syntax:** `useQuery({ queryKey, queryFn, enabled, refetchInterval })`, `useMutation({ mutationFn, onSuccess })`, `queryClient.invalidateQueries({ queryKey })`. No positional args (v4 style).
- **MSW v2:** `import { http, HttpResponse } from 'msw'`; `setupServer(...)` from `msw/node`; handlers `http.get('/path', ({ params, request }) => HttpResponse.json(...))`; test lifecycle `server.listen()/resetHandlers()/close()`.
- API base: `const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'`. All client calls are relative to it. MSW handlers match `/api/*` (the base). Vite dev-proxy rewrites `/api` → `''` onto `127.0.0.1:8000`.
- The API's `get_summary`/`/videos/{id}.summary.highlights` and `.qa` are JSON **strings** — `VideoDetail` must `JSON.parse` them (guarded).
- Jobs are status-only (`queued|running|done|error`) — the JobStrip shows a spinner + status, never a %.
- `frontend/` gets its own `.gitignore` (`node_modules`, `dist`). Do NOT commit `node_modules`.
- Each task ends with all four gates green and is committed.

---

## File Structure

```
frontend/
  package.json  vite.config.ts  tsconfig.json  tsconfig.node.json
  tailwind.config.js  postcss.config.js  .eslintrc.cjs  .gitignore  index.html
  .env.example (VITE_API_BASE=/api)
  src/
    main.tsx  App.tsx  index.css  vite-env.d.ts
    api/ types.ts  client.ts  hooks.ts
    lib/ utils.ts
    components/
      AppShell.tsx  VideoList.tsx  VideoDetail.tsx  SearchView.tsx  JobStrip.tsx
      AddDialog.tsx  DiscoverDialog.tsx
      ui/ button.tsx  dialog.tsx  input.tsx  badge.tsx
    mocks/ handlers.ts  node.ts
    test/ setup.ts  utils.tsx (renderWithProviders)
    **/*.test.tsx
```

---

## Task 1: Scaffold + toolchain

**Files:** create the whole `frontend/` skeleton (configs + empty `src` entry).

- [ ] **Step 1: Create the Vite React-TS project**

From the repo root:
```bash
cd /Users/dasein/dev/yt_summary
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query react-router-dom @radix-ui/react-dialog class-variance-authority clsx tailwind-merge lucide-react
npm install -D tailwindcss postcss autoprefixer vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event msw @vitejs/plugin-react eslint
npx tailwindcss init -p
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
})
```

- [ ] **Step 3: Configure Tailwind**

`frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```
Replace `frontend/src/index.css` with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: `frontend/src/lib/utils.ts`, tsconfig path alias, `.env.example`, `.gitignore`**

`src/lib/utils.ts`:
```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtTs(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(seconds ?? 0))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
```
In `tsconfig.json` `compilerOptions`, add:
```json
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
```
`frontend/.env.example`: `VITE_API_BASE=/api`
Ensure `frontend/.gitignore` (Vite creates one) ignores `node_modules` and `dist`.

- [ ] **Step 5: Add package.json scripts**

Ensure `frontend/package.json` `scripts` has:
```json
    "dev": "vite",
    "build": "tsc -b && vite build",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "lint": "eslint . --max-warnings 0",
    "preview": "vite preview"
```

- [ ] **Step 6: Minimal placeholder App so build passes**

`src/App.tsx`:
```tsx
export default function App() {
  return <div className="p-4 text-lg">yt_summary</div>
}
```
`src/main.tsx` (keep Vite's default, importing `./index.css` and rendering `<App />`).

- [ ] **Step 7: Verify gates**

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```
All must succeed. (`test` has no tests yet — `vitest run` with no tests exits 0.)

- [ ] **Step 8: Commit**

```bash
git add frontend/ ':!frontend/node_modules'
git commit -m "feat(ui): scaffold vite+react+ts+tailwind frontend"
```

---

## Task 2: API types + client + MSW harness

**Files:** `src/api/types.ts`, `src/api/client.ts`, `src/mocks/handlers.ts`, `src/mocks/node.ts`, `src/test/setup.ts`, `src/test/utils.tsx`, `src/api/client.test.ts`.

- [ ] **Step 1: `src/api/types.ts`**

```ts
export interface VideoOut {
  video_id: string
  title: string | null
  url: string | null
  status: string | null
  published_at: string | null
  duration_s: number | null
}
export interface Summary {
  video_id: string
  summary_md: string
  highlights: string | null // JSON string
  qa: string | null // JSON string
  model: string | null
  created_at: string | null
}
export interface VideoDetail extends VideoOut {
  transcript: string | null
  summary: Summary | null
}
export interface SearchHit {
  video_id: string
  start_s: number | null
  end_s: number | null
  text: string | null
}
export interface Job {
  id: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: number | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
}
export interface StatusCounts { counts: Record<string, number> }
export interface Highlight { start_s: number; label: string }
export interface QA { q: string; a: string }
```

- [ ] **Step 2: `src/api/client.ts`**

```ts
import type { VideoOut, VideoDetail, SearchHit, Job, StatusCounts } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = (body as { detail?: string }).detail ?? detail
    } catch { /* non-json */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const qs = (params: Record<string, string | number | undefined>) => {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ''
}

export const api = {
  listVideos: (f: { status?: string; since?: string } = {}) =>
    req<VideoOut[]>(`/videos${qs(f)}`),
  getVideo: (id: string) => req<VideoDetail>(`/videos/${id}`),
  getStatus: () => req<StatusCounts>('/status'),
  search: (q: string, mode = 'hybrid', k = 10) =>
    req<SearchHit[]>(`/search${qs({ q, mode, k })}`),
  sendFeedback: (video_id: string, signal: number) =>
    req<void>('/feedback', { method: 'POST', body: JSON.stringify({ video_id, signal }) }),
  startFetch: (url: string, force = false) =>
    req<Job>('/jobs/fetch', { method: 'POST', body: JSON.stringify({ url, force }) }),
  startDiscover: (body: { after?: string; deep?: boolean; min_duration?: number }) =>
    req<Job>('/jobs/discover', { method: 'POST', body: JSON.stringify(body) }),
  startFetchPending: (body: { since?: string; limit?: number }) =>
    req<Job>('/jobs/fetch-pending', { method: 'POST', body: JSON.stringify(body) }),
  startSummarize: (video_id: string) =>
    req<Job>('/jobs/summarize', { method: 'POST', body: JSON.stringify({ video_id }) }),
  listJobs: () => req<Job[]>('/jobs'),
  getJob: (id: string) => req<Job>(`/jobs/${id}`),
}
```

- [ ] **Step 3: MSW harness — `src/mocks/handlers.ts` + `src/mocks/node.ts`**

`handlers.ts`:
```ts
import { http, HttpResponse } from 'msw'

export const videosFixture = [
  { video_id: 'v1', title: 'First Video', url: 'https://y/v1', status: 'summarized',
    published_at: '2026-07-22', duration_s: 600 },
  { video_id: 'v2', title: 'Second', url: 'https://y/v2', status: 'transcribed',
    published_at: '2026-07-21', duration_s: 300 },
]

export const handlers = [
  http.get('/api/videos', () => HttpResponse.json(videosFixture)),
  http.get('/api/videos/:id', ({ params }) => {
    const v = videosFixture.find((x) => x.video_id === params.id)
    if (!v) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json({
      ...v, transcript: 'hello world',
      summary: { video_id: v.video_id, summary_md: 'A summary.',
        highlights: JSON.stringify([{ start_s: 10, label: 'key point' }]),
        qa: JSON.stringify([{ q: 'what?', a: 'this.' }]), model: 'test', created_at: 't0' },
    })
  }),
  http.get('/api/status', () => HttpResponse.json({ counts: { transcribed: 1, summarized: 1 } })),
  http.get('/api/search', () => HttpResponse.json([
    { video_id: 'v1', start_s: 10, end_s: 20, text: 'matched snippet' }])),
  http.post('/api/feedback', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/jobs', () => HttpResponse.json([])),
  http.post('/api/jobs/:kind', ({ params }) => HttpResponse.json({
    id: 'job1', kind: String(params.kind), status: 'queued', progress: null,
    result: null, error: null, created_at: 't0' })),
  http.get('/api/jobs/:id', ({ params }) => HttpResponse.json({
    id: String(params.id), kind: 'fetch', status: 'done', progress: null,
    result: { video_id: 'vX' }, error: null, created_at: 't0' })),
]
```
`node.ts`:
```ts
import { setupServer } from 'msw/node'
import { handlers } from './handlers'
export const server = setupServer(...handlers)
```

- [ ] **Step 4: `src/test/setup.ts` + `src/test/utils.tsx`**

`setup.ts`:
```ts
import '@testing-library/jest-dom/vitest'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { server } from '../mocks/node'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```
`utils.tsx`:
```tsx
import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
  return render(ui, { wrapper: Wrapper })
}
```

- [ ] **Step 5: `src/api/client.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { server } from '../mocks/node'
import { http, HttpResponse } from 'msw'
import { api, ApiError } from './client'

describe('api client', () => {
  it('lists videos', async () => {
    const vids = await api.listVideos()
    expect(vids.map((v) => v.video_id)).toEqual(['v1', 'v2'])
  })
  it('throws ApiError with detail on non-2xx', async () => {
    server.use(http.get('/api/status', () =>
      HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    await expect(api.getStatus()).rejects.toMatchObject({ status: 500, message: 'boom' })
    await expect(api.getStatus()).rejects.toBeInstanceOf(ApiError)
  })
  it('204 feedback resolves to undefined', async () => {
    await expect(api.sendFeedback('v1', 1)).resolves.toBeUndefined()
  })
})
```

- [ ] **Step 6: Run gates**

Run: `npm --prefix frontend run test` → PASS; `typecheck`, `lint`, `build` → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src ':!frontend/node_modules'
git commit -m "feat(ui): typed api client + msw test harness"
```

---

## Task 3: TanStack Query hooks

**Files:** `src/api/hooks.ts`, `src/api/hooks.test.tsx`.

- [ ] **Step 1: `src/api/hooks.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Job } from './types'

export function useVideos(filters: { status?: string; since?: string } = {}) {
  return useQuery({ queryKey: ['videos', filters], queryFn: () => api.listVideos(filters) })
}
export function useVideo(id: string | undefined) {
  return useQuery({ queryKey: ['video', id], queryFn: () => api.getVideo(id!), enabled: !!id })
}
export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: api.getStatus })
}
export function useSearch(q: string, mode = 'hybrid') {
  return useQuery({
    queryKey: ['search', q, mode],
    queryFn: () => api.search(q, mode),
    enabled: q.trim().length > 0,
  })
}
const active = (j: Job) => j.status === 'queued' || j.status === 'running'
export function useJobs() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    refetchInterval: (query) => (query.state.data?.some(active) ? 1000 : false),
  })
}

function useJobMutation<V>(fn: (v: V) => Promise<Job>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
export const useStartFetch = () => useJobMutation((url: string) => api.startFetch(url))
export const useStartDiscover = () =>
  useJobMutation((b: { after?: string; deep?: boolean; min_duration?: number }) => api.startDiscover(b))
export const useStartFetchPending = () =>
  useJobMutation((b: { since?: string; limit?: number }) => api.startFetchPending(b))
export const useSummarize = () => useJobMutation((id: string) => api.startSummarize(id))

export function useFeedback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ video_id, signal }: { video_id: string; signal: number }) =>
      api.sendFeedback(video_id, signal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })
}
```

- [ ] **Step 2: `src/api/hooks.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useVideos, useSearch } from './hooks'

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('hooks', () => {
  it('useVideos returns fixture data', async () => {
    const { result } = renderHook(() => useVideos(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(2)
  })
  it('useSearch is disabled for empty query', () => {
    const { result } = renderHook(() => useSearch(''), { wrapper: wrap() })
    expect(result.current.fetchStatus).toBe('idle')
  })
})
```

- [ ] **Step 3: Run gates** (`test`/`typecheck`/`lint`/`build`) → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api ':!frontend/node_modules'
git commit -m "feat(ui): tanstack-query hooks (queries + job mutations)"
```

---

## Task 4: UI primitives + providers + AppShell + routing

**Files:** `src/components/ui/{button,dialog,input,badge}.tsx`, `src/components/AppShell.tsx` (skeleton with a `JobStrip` placeholder), `src/App.tsx`, `src/main.tsx`, `src/components/AppShell.test.tsx`.

- [ ] **Step 1: shadcn-style primitives**

`src/components/ui/button.tsx`:
```tsx
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        default: 'bg-slate-900 text-white hover:bg-slate-700',
        outline: 'border border-slate-300 hover:bg-slate-100',
        ghost: 'hover:bg-slate-100',
      },
      size: { default: 'h-9 px-4', sm: 'h-8 px-3', icon: 'h-9 w-9' },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)
export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
)
Button.displayName = 'Button'
```
`src/components/ui/input.tsx`:
```tsx
import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn('h-9 w-full rounded-md border border-slate-300 px-3 text-sm', className)} {...props} />
  ),
)
Input.displayName = 'Input'
```
`src/components/ui/badge.tsx`:
```tsx
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'
export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium', className)} {...props} />
}
```
`src/components/ui/dialog.tsx`:
```tsx
import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Dialog({ open, onOpenChange, children }: {
  open: boolean; onOpenChange: (o: boolean) => void; children: ReactNode
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 bg-black/40" />
        <DialogPrimitive.Content className={cn(
          'fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-lg')}>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
export const DialogTitle = DialogPrimitive.Title
```

- [ ] **Step 2: `src/App.tsx` + `src/main.tsx`**

`src/App.tsx`:
```tsx
import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { VideoDetail } from './components/VideoDetail'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route path="videos/:id" element={<VideoDetail />} />
      </Route>
    </Routes>
  )
}
```
`src/main.tsx`:
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const qc = new QueryClient()
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
```
Note: `VideoDetail` is created in Task 6; for Task 4, create a minimal stub `src/components/VideoDetail.tsx` returning `<div>select a video</div>` and replace it in Task 6.

- [ ] **Step 3: `src/components/AppShell.tsx`** (skeleton; JobStrip + VideoList wired as they land)

```tsx
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { VideoList } from './VideoList'
import { SearchView } from './SearchView'
import { JobStrip } from './JobStrip'
import { AddDialog } from './AddDialog'
import { DiscoverDialog } from './DiscoverDialog'

export function AppShell() {
  const [query, setQuery] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b px-4 py-2">
        <span className="font-semibold">yt_summary</span>
        <Input placeholder="Search…" value={query}
          onChange={(e) => setQuery(e.target.value)} className="max-w-md" />
        <Button variant="outline" onClick={() => setAddOpen(true)}>+ Add</Button>
        <Button variant="outline" onClick={() => setDiscoverOpen(true)}>Discover</Button>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-80 overflow-y-auto border-r">
          {query.trim() ? <SearchView query={query} /> : <VideoList />}
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto p-4"><Outlet /></main>
      </div>
      <JobStrip />
      <AddDialog open={addOpen} onOpenChange={setAddOpen} />
      <DiscoverDialog open={discoverOpen} onOpenChange={setDiscoverOpen} />
    </div>
  )
}
```
Note: `VideoList`, `SearchView`, `JobStrip`, `AddDialog`, `DiscoverDialog` are built in Tasks 5–7. For Task 4, create minimal stubs for each (e.g. `export function JobStrip() { return null }`) so the app compiles; later tasks replace them.

- [ ] **Step 4: `src/components/AppShell.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders the title and search box', () => {
    renderWithProviders(<AppShell />)
    expect(screen.getByText('yt_summary')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Search…')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Run gates** → PASS (with stubs in place).

- [ ] **Step 6: Commit**

```bash
git add frontend/src ':!frontend/node_modules'
git commit -m "feat(ui): primitives + providers + AppShell skeleton + routing"
```

---

## Task 5: VideoList + StatusFilter

**Files:** replace stub `src/components/VideoList.tsx`; `src/components/VideoList.test.tsx`.

- [ ] **Step 1: `src/components/VideoList.tsx`**

```tsx
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useVideos } from '@/api/hooks'
import { Badge } from './ui/badge'
import { cn } from '@/lib/utils'

const STATUSES = ['', 'discovered', 'downloaded', 'transcribed', 'summarized']

export function VideoList() {
  const [status, setStatus] = useState('')
  const { data, isLoading, error } = useVideos(status ? { status } : {})
  const navigate = useNavigate()
  const { id } = useParams()

  return (
    <div>
      <div className="border-b p-2">
        <select className="w-full rounded border px-2 py-1 text-sm"
          value={status} onChange={(e) => setStatus(e.target.value)} aria-label="status filter">
          {STATUSES.map((s) => <option key={s} value={s}>{s || 'all statuses'}</option>)}
        </select>
      </div>
      {isLoading && <p className="p-3 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-3 text-sm text-red-600">API not reachable — run `yt-ai serve`</p>}
      <ul>
        {data?.map((v) => (
          <li key={v.video_id}>
            <button
              onClick={() => navigate(`/videos/${v.video_id}`)}
              className={cn('flex w-full flex-col items-start gap-1 border-b px-3 py-2 text-left hover:bg-slate-50',
                id === v.video_id && 'bg-slate-100')}
            >
              <span className="text-sm font-medium">{v.title ?? v.video_id}</span>
              <span className="flex items-center gap-2 text-xs text-slate-500">
                {v.published_at ?? '—'} <Badge>{v.status ?? '?'}</Badge>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 2: `src/components/VideoList.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/utils'
import { VideoList } from './VideoList'

describe('VideoList', () => {
  it('renders rows from the API', async () => {
    renderWithProviders(<VideoList />)
    expect(await screen.findByText('First Video')).toBeInTheDocument()
    expect(screen.getByText('Second')).toBeInTheDocument()
  })
  it('has a status filter', async () => {
    renderWithProviders(<VideoList />)
    await screen.findByText('First Video')
    const select = screen.getByLabelText('status filter')
    await userEvent.selectOptions(select, 'transcribed')
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe('transcribed'))
  })
})
```

- [ ] **Step 3: Run gates** → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components ':!frontend/node_modules'
git commit -m "feat(ui): video list + status filter"
```

---

## Task 6: VideoDetail

**Files:** replace stub `src/components/VideoDetail.tsx`; `src/components/VideoDetail.test.tsx`.

**Interfaces:** parses `summary.highlights`/`summary.qa` (JSON strings) defensively; 👍/👎 via `useFeedback`; **Summarize** button (via `useSummarize`) shown only when `summary` is null.

- [ ] **Step 1: `src/components/VideoDetail.tsx`**

```tsx
import { useParams } from 'react-router-dom'
import { useVideo, useFeedback, useSummarize } from '@/api/hooks'
import { Button } from './ui/button'
import { fmtTs } from '@/lib/utils'
import type { Highlight, QA } from '@/api/types'

function parse<T>(s: string | null | undefined): T[] {
  if (!s) return []
  try { const v = JSON.parse(s); return Array.isArray(v) ? (v as T[]) : [] } catch { return [] }
}

export function VideoDetail() {
  const { id } = useParams()
  const { data: v, isLoading, error } = useVideo(id)
  const feedback = useFeedback()
  const summarize = useSummarize()

  if (!id) return <p className="text-slate-500">Select a video.</p>
  if (isLoading) return <p className="text-slate-500">loading…</p>
  if (error || !v) return <p className="text-red-600">not found</p>

  const highlights = parse<Highlight>(v.summary?.highlights)
  const qa = parse<QA>(v.summary?.qa)

  return (
    <article className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">{v.title ?? v.video_id}</h1>
        <a href={v.url ?? '#'} className="text-sm text-blue-600" target="_blank" rel="noreferrer">{v.url}</a>
      </header>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => feedback.mutate({ video_id: v.video_id, signal: 1 })}>👍 Like</Button>
        <Button size="sm" variant="outline" onClick={() => feedback.mutate({ video_id: v.video_id, signal: -1 })}>👎 Dislike</Button>
        {!v.summary && (
          <Button size="sm" disabled={summarize.isPending} onClick={() => summarize.mutate(v.video_id)}>
            {summarize.isPending ? 'Summarizing…' : 'Summarize'}
          </Button>
        )}
      </div>
      {v.summary && (
        <section className="space-y-3">
          <div>
            <h2 className="font-medium">Summary</h2>
            <p className="whitespace-pre-wrap text-sm">{v.summary.summary_md}</p>
          </div>
          {highlights.length > 0 && (
            <div>
              <h2 className="font-medium">Highlights</h2>
              <ul className="text-sm">
                {highlights.map((h, i) => (
                  <li key={i}><span className="font-mono text-slate-500">{fmtTs(h.start_s)}</span> — {h.label}</li>
                ))}
              </ul>
            </div>
          )}
          {qa.length > 0 && (
            <div>
              <h2 className="font-medium">Q&amp;A</h2>
              <dl className="space-y-1 text-sm">
                {qa.map((x, i) => (<div key={i}><dt className="font-medium">{x.q}</dt><dd className="text-slate-600">{x.a}</dd></div>))}
              </dl>
            </div>
          )}
        </section>
      )}
      {v.transcript && (
        <details><summary className="cursor-pointer text-sm text-slate-500">Transcript</summary>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{v.transcript}</p></details>
      )}
    </article>
  )
}
```

- [ ] **Step 2: `src/components/VideoDetail.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { Routes, Route } from 'react-router-dom'
import { VideoDetail } from './VideoDetail'

const renderAt = (id: string) =>
  renderWithProviders(<Routes><Route path="/videos/:id" element={<VideoDetail />} /></Routes>, { route: `/videos/${id}` })

describe('VideoDetail', () => {
  it('shows summary, highlights, Q&A', async () => {
    renderAt('v1')
    expect(await screen.findByText('A summary.')).toBeInTheDocument()
    expect(screen.getByText(/key point/)).toBeInTheDocument()
    expect(screen.getByText('00:10')).toBeInTheDocument()
  })
  it('like sends feedback', async () => {
    let posted = false
    server.use(http.post('/api/feedback', async ({ request }) => {
      const b = await request.json() as { signal: number }
      posted = b.signal === 1
      return new HttpResponse(null, { status: 204 })
    }))
    renderAt('v1')
    await userEvent.click(await screen.findByText('👍 Like'))
    await new Promise((r) => setTimeout(r, 20))
    expect(posted).toBe(true)
  })
  it('shows Summarize only when no summary', async () => {
    server.use(http.get('/api/videos/:id', ({ params }) => HttpResponse.json({
      video_id: params.id, title: 'No Sum', url: 'u', status: 'transcribed',
      published_at: '2026-07-20', duration_s: 100, transcript: 't', summary: null })))
    renderAt('v9')
    expect(await screen.findByText('Summarize')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run gates** → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components ':!frontend/node_modules'
git commit -m "feat(ui): video detail (summary/highlights/qa + feedback + summarize)"
```

---

## Task 7: SearchView + JobStrip + dialogs

**Files:** replace stubs `SearchView.tsx`, `JobStrip.tsx`, `AddDialog.tsx`, `DiscoverDialog.tsx`; tests for JobStrip + AddDialog + SearchView.

- [ ] **Step 1: `src/components/SearchView.tsx`**

```tsx
import { useNavigate } from 'react-router-dom'
import { useSearch } from '@/api/hooks'
import { fmtTs } from '@/lib/utils'

export function SearchView({ query }: { query: string }) {
  const { data, isLoading } = useSearch(query)
  const navigate = useNavigate()
  return (
    <div>
      <p className="border-b p-2 text-xs text-slate-500">Search: “{query}”</p>
      {isLoading && <p className="p-3 text-sm text-slate-500">searching…</p>}
      <ul>
        {data?.map((h, i) => (
          <li key={i}>
            <button onClick={() => navigate(`/videos/${h.video_id}`)}
              className="flex w-full flex-col items-start border-b px-3 py-2 text-left hover:bg-slate-50">
              <span className="font-mono text-xs text-slate-500">{fmtTs(h.start_s ?? 0)} · {h.video_id}</span>
              <span className="text-sm">{h.text}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 2: `src/components/JobStrip.tsx`**

```tsx
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useJobs } from '@/api/hooks'
import { Badge } from './ui/badge'

export function JobStrip() {
  const { data: jobs } = useJobs()
  const qc = useQueryClient()
  const prevDone = useRef(0)

  const doneCount = jobs?.filter((j) => j.status === 'done').length ?? 0
  useEffect(() => {
    if (doneCount > prevDone.current) {
      qc.invalidateQueries({ queryKey: ['videos'] })
      qc.invalidateQueries({ queryKey: ['status'] })
    }
    prevDone.current = doneCount
  }, [doneCount, qc])

  if (!jobs || jobs.length === 0) return <footer className="border-t px-4 py-1 text-xs text-slate-400">No jobs</footer>
  return (
    <footer className="flex items-center gap-3 border-t px-4 py-1 text-xs">
      <span className="font-medium">Jobs:</span>
      {jobs.slice(-5).map((j) => (
        <span key={j.id} className="flex items-center gap-1">
          {j.kind}
          {j.status === 'running' && <span className="animate-pulse">⏳</span>}
          {j.status === 'queued' && <Badge>queued</Badge>}
          {j.status === 'done' && <span className="text-green-600">✓</span>}
          {j.status === 'error' && <span className="text-red-600" title={j.error ?? ''}>✕</span>}
        </span>
      ))}
    </footer>
  )
}
```

- [ ] **Step 3: `src/components/AddDialog.tsx` + `src/components/DiscoverDialog.tsx`**

`AddDialog.tsx`:
```tsx
import { useState } from 'react'
import { Dialog, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { useStartFetch } from '@/api/hooks'

export function AddDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [url, setUrl] = useState('')
  const start = useStartFetch()
  const submit = () => {
    if (!url.trim()) return
    start.mutate(url.trim(), { onSuccess: () => { setUrl(''); onOpenChange(false) } })
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="mb-3 text-lg font-semibold">Add a video</DialogTitle>
      <Input placeholder="https://youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button disabled={start.isPending} onClick={submit}>Fetch</Button>
      </div>
    </Dialog>
  )
}
```
`DiscoverDialog.tsx`:
```tsx
import { useState } from 'react'
import { Dialog, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { useStartDiscover } from '@/api/hooks'

export function DiscoverDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [after, setAfter] = useState('')
  const [minDuration, setMinDuration] = useState('120')
  const [deep, setDeep] = useState(false)
  const start = useStartDiscover()
  const submit = () => start.mutate(
    { after: after || undefined, deep, min_duration: Number(minDuration) || 120 },
    { onSuccess: () => onOpenChange(false) },
  )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="mb-3 text-lg font-semibold">Discover subscriptions</DialogTitle>
      <label className="block text-sm">After (YYYY-MM-DD)
        <Input value={after} onChange={(e) => setAfter(e.target.value)} placeholder="optional" /></label>
      <label className="mt-2 block text-sm">Min duration (s)
        <Input value={minDuration} onChange={(e) => setMinDuration(e.target.value)} /></label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> Deep (enumerate channels)</label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button disabled={start.isPending} onClick={submit}>Discover</Button>
      </div>
    </Dialog>
  )
}
```

- [ ] **Step 4: Tests — `JobStrip.test.tsx`, `AddDialog.test.tsx`, `SearchView.test.tsx`**

```tsx
// src/components/JobStrip.test.tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { JobStrip } from './JobStrip'

describe('JobStrip', () => {
  it('shows a running job', async () => {
    server.use(http.get('/api/jobs', () => HttpResponse.json([
      { id: 'j1', kind: 'fetch', status: 'running', progress: null, result: null, error: null, created_at: 't0' }])))
    renderWithProviders(<JobStrip />)
    expect(await screen.findByText('fetch')).toBeInTheDocument()
  })
})
```
```tsx
// src/components/AddDialog.test.tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/node'
import { renderWithProviders } from '../test/utils'
import { AddDialog } from './AddDialog'

describe('AddDialog', () => {
  it('submitting a URL posts a fetch job', async () => {
    let gotUrl = ''
    server.use(http.post('/api/jobs/fetch', async ({ request }) => {
      gotUrl = (await request.json() as { url: string }).url
      return HttpResponse.json({ id: 'j1', kind: 'fetch', status: 'queued', progress: null, result: null, error: null, created_at: 't0' })
    }))
    renderWithProviders(<AddDialog open onOpenChange={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/youtube.com/), 'https://y/abc')
    await userEvent.click(screen.getByText('Fetch'))
    await new Promise((r) => setTimeout(r, 20))
    expect(gotUrl).toBe('https://y/abc')
  })
})
```
```tsx
// src/components/SearchView.test.tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import { SearchView } from './SearchView'

describe('SearchView', () => {
  it('renders hits for a query', async () => {
    renderWithProviders(<SearchView query="matched" />)
    expect(await screen.findByText('matched snippet')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Run gates** → PASS (full `vitest run`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components ':!frontend/node_modules'
git commit -m "feat(ui): search view + job strip + add/discover dialogs"
```

---

## Task 8: Docs + final sweep

**Files:** `frontend/README.md`, root `README.md`, `CLAUDE.md`.

- [ ] **Step 1: `frontend/README.md`**

Cover: `npm install`, `npm run dev` (Vite on :5173), the `/api` proxy to `127.0.0.1:8000`, that it needs `yt-ai serve` running for live data, and `npm run test|build|typecheck|lint`. Note the MVP scope (Library/Detail/Search/Jobs) and that Recommend/Digest + Electron are deferred.

- [ ] **Step 2: Root `README.md` + `CLAUDE.md`**

- README: a "Desktop UI (SP4b)" section → `cd frontend && npm install && npm run dev` (with `yt-ai serve` running); browser-first React over the local API.
- CLAUDE.md: add `frontend/` to the layout (Vite+React+TS, TanStack Query, MSW tests), note it's browser-first over the SP4a API, Electron wrapping is SP4c.

- [ ] **Step 3: Final sweep**

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
```
All must pass. Also confirm the Python suite is untouched: `uv run pytest -q` still green.

- [ ] **Step 4: Commit**

```bash
git add frontend/README.md README.md CLAUDE.md
git commit -m "docs(ui): frontend README + root docs for the desktop UI"
```

- [ ] **Step 5: Report roadmap-memory update to the controller**

Report that the roadmap memory should mark SP4b done: browser-first React UI in `frontend/` (Vite+React+TS, TanStack Query, Tailwind/shadcn, MSW tests) over the SP4a API — Library/Detail/Search/Jobs; Recommend/Digest deferred; SP4c (Electron) next.

---

## Self-Review Notes

- **Spec coverage:** master-detail AppShell + JobStrip (T4, T7), Library + StatusFilter (T5), Detail with summary/highlights(JSON-parsed)/Q&A + like/dislike + Summarize (T6), Search replacing the left pane (T4 wiring + T7), typed client + hooks over `VITE_API_BASE` with Vite proxy (T1–T3), offline MSW tests (T2 harness + every component test), docs (T8). Recommend/Digest/Electron/determinate-progress deferred per spec.
- **Placeholder scan:** none — every step has complete code. The stub→replace sequence (VideoDetail in T4→T6; VideoList/SearchView/JobStrip/dialogs stubbed in T4, replaced in T5–T7) is deliberate and each intermediate task is green.
- **Version correctness:** TanStack Query v5 object syntax + `invalidateQueries({queryKey})` + function `refetchInterval`; MSW v2 `http`/`HttpResponse`/`setupServer`; Vite proxy `rewrite`; grounded against current docs.
- **Type/name consistency:** `api.*` client methods match the hook callers and MSW handler paths (all under `/api`); `Job.status` union matches `active()` + JobStrip; `VideoDetail` parses `summary.highlights`/`qa` strings per the API contract; the Vite `test` block + `setupFiles` matches `src/test/setup.ts`.
- **Toolchain isolation:** all gates are `npm --prefix frontend run *`; the Python suite/ruff are never invoked for these tasks and remain green (verified in T8). `node_modules` is gitignored and excluded from every `git add`.
