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
