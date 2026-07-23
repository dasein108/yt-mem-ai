// Resolved per-call (not module load) so the Electron preload's runtime
// `window.electron.apiBase` — set after the page loads — is honored, and so
// tests can inject it before calling the client.
export function apiBase(): string {
  return (
    (typeof window !== 'undefined' && window.electron?.apiBase) ||
    (import.meta.env.VITE_API_BASE as string | undefined) ||
    '/api'
  )
}
