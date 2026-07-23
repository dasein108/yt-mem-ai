import { contextBridge } from 'electron'

const port = process.env.YT_API_PORT || '8000'

contextBridge.exposeInMainWorld('electron', {
  isElectron: true,
  platform: process.platform,
  apiBase: `http://127.0.0.1:${port}`,
})
