import { useEffect, useState } from 'react'
import { api } from './api'
import TestStation from './TestStation'

/**
 * TRACE-X 2.0 operator interface.
 * Only the commissioned physical test station is shown.
 * Legacy simulator/diagnostic tools remain in the codebase but are not
 * exposed as competing controls on the Raspberry Pi touchscreen.
 */
export default function App() {
  const [online, setOnline] = useState(false)

  useEffect(() => {
    let mounted = true
    async function checkBackend() {
      try {
        const health = await api.health()
        if (mounted) setOnline(health.status === 'ok')
      } catch {
        if (mounted) setOnline(false)
      }
    }
    void checkBackend()
    const interval = window.setInterval(() => { void checkBackend() }, 5000)
    return () => { mounted = false; window.clearInterval(interval) }
  }, [])

  return <div className="trace-x2">
    <div className="trace-x2-topbar">
      <div className="trace-x2-brand">
        <span className="trace-x2-mark" aria-hidden="true">X</span>
        <div><strong>TRACE-X 2.0</strong><small>Hardware diagnostic station</small></div>
      </div>
      <div className="trace-x2-connection" role="status">
        <i className={online ? 'dot ready' : 'dot danger'} aria-hidden="true" />
        {online ? 'Raspberry Pi connected' : 'Backend unavailable'}
      </div>
    </div>
    <main className="trace-x2-main">
      <TestStation />
      <footer className="trace-x2-footer">
        Physical outputs remain controlled by the STM32 and the Raspberry Pi backend.
        Motor start requires approved firmware, operator confirmation and automatic hardware readiness.
      </footer>
    </main>
  </div>
}
