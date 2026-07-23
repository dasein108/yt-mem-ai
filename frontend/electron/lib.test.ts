import { describe, it, expect } from 'vitest'
import { resolveApiCommand, waitForApi, needsTreeKill, treeKillArgs, logLine, logsPath } from './lib'
import { readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

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

describe('needsTreeKill', () => {
  it('is true on win32', () => {
    expect(needsTreeKill('win32')).toBe(true)
  })
  it('is false on darwin', () => {
    expect(needsTreeKill('darwin')).toBe(false)
  })
})

describe('treeKillArgs', () => {
  it('builds taskkill args for a pid', () => {
    expect(treeKillArgs(123)).toEqual(['/pid', '123', '/t', '/f'])
  })
})

describe('logLine / logsPath', () => {
  it('logsPath builds the repo-root path', () => {
    expect(logsPath('/repo')).toBe(path.join('/repo', 'logs', 'common.jsonl'))
  })
  it('logLine appends a json line with ts', () => {
    const f = path.join(tmpdir(), `sp7-${process.pid}.jsonl`)
    rmSync(f, { force: true })
    logLine(f, { source: 'electron', event: 'electron.start' })
    logLine(f, { source: 'electron', event: 'electron.quit' })
    const lines = readFileSync(f, 'utf8').trim().split('\n').map((l) => JSON.parse(l))
    expect(lines.length).toBe(2)
    expect(lines[0]).toMatchObject({ source: 'electron', event: 'electron.start' })
    expect(typeof lines[0].ts).toBe('string')
    rmSync(f, { force: true })
  })
  it('logLine defaults level to info and msg to empty', () => {
    const f = path.join(tmpdir(), `sp7-def-${process.pid}.jsonl`)
    rmSync(f, { force: true })
    logLine(f, { source: 'electron', event: 'e' })
    const line = JSON.parse(readFileSync(f, 'utf8').trim())
    expect(line.level).toBe('info')
    expect(line.msg).toBe('')
    rmSync(f, { force: true })
  })
  it('logLine lets obj override the level default', () => {
    const f = path.join(tmpdir(), `sp7-err-${process.pid}.jsonl`)
    rmSync(f, { force: true })
    logLine(f, { source: 'electron', event: 'e', level: 'error' })
    const line = JSON.parse(readFileSync(f, 'utf8').trim())
    expect(line.level).toBe('error')
    rmSync(f, { force: true })
  })
})
