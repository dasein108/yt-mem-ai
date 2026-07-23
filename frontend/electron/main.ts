import { app, BrowserWindow, Tray, Menu, nativeImage } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveApiCommand, waitForApi, needsTreeKill, treeKillArgs } from './lib'
import { TRAY_ICON_DATA_URL } from './tray-icon'

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
  if (sidecar && !sidecar.killed) {
    if (sidecar.pid && needsTreeKill(process.platform)) {
      spawn('taskkill', treeKillArgs(sidecar.pid))
    } else {
      sidecar.kill()
    }
  }
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
  win.on('minimize', () => { win?.hide() })
  win.on('close', (e) => { if (!isQuitting) { e.preventDefault(); win?.hide() } })
}

function createTray(): void {
  const icon = nativeImage.createFromDataURL(TRAY_ICON_DATA_URL)
  tray = new Tray(icon)
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
        "document.title = 'API failed to start — run: uv run yt-ai serve';" +
        "document.body.insertAdjacentHTML('afterbegin', " +
        "'<div style=\"position:fixed;top:0;left:0;right:0;z-index:2147483647;" +
        "background:#c0392b;color:#fff;font:14px/1.4 sans-serif;padding:10px 16px;" +
        "text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.3);\">" +
        "API failed to start — run: uv run yt-ai serve</div>')")
    })
  }
})

app.on('before-quit', () => { isQuitting = true; stopSidecar() })
app.on('window-all-closed', () => { /* stay in tray; do not quit */ })
