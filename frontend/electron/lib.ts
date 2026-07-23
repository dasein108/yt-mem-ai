export interface ApiCommand { command: string; args: string[]; cwd: string }

export function resolveApiCommand(env: Record<string, string | undefined>, repoRoot: string): ApiCommand {
  if (env.YT_API_CMD) {
    const parts = env.YT_API_CMD.trim().split(/\s+/)
    return { command: parts[0], args: parts.slice(1), cwd: repoRoot }
  }
  const port = env.YT_API_PORT || '8000'
  return { command: 'uv', args: ['run', 'yt-ai', 'serve', '--port', port], cwd: repoRoot }
}

export function needsTreeKill(platform: string): boolean {
  return platform === 'win32'
}

export function treeKillArgs(pid: number): string[] {
  return ['/pid', String(pid), '/t', '/f']
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
