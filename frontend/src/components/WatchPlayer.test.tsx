import { describe, it, expect, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
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
  it('exposes a seek callback that maps to iframe start param (non-electron fallback)', () => {
    let seek: ((s: number) => void) | undefined
    render(<WatchPlayer videoId="abc" url={null} onClose={() => {}} onReady={(s) => { seek = s }} />)
    expect(typeof seek).toBe('function')
    act(() => seek!(90))
    const iframe = screen.getByTitle('player') as HTMLIFrameElement
    expect(iframe.src).toContain('start=90')
  })
})
