import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Activities = lazy(() => import('./pages/Activities'))
const ActivityDetail = lazy(() => import('./pages/ActivityDetail'))
const SettingsPage = lazy(() => import('./pages/Settings'))

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="animate-pulse text-sm text-slate-400">Loading...</div>
    </div>
  )
}

function App() {
  return (
    <Layout>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/activities" element={<Activities />} />
          <Route path="/activities/:id" element={<ActivityDetail />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}

export default App
