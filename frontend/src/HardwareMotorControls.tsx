import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { AutomatedRun } from './types'

type HardwareStatus = {
  operating_mode: string
  profile_ready: boolean
  reason: string
  asset_id: string
  fixed_pwm_percent: number | null
  max_duration_ms: number
  active_run: AutomatedRun | null
  hardware_control_enabled: boolean
  hardware_control: boolean
  firmware_hardware_control: boolean | null
  preflight: { ready: boolean; reason: string; stale: boolean }
}

const format = (number: number | null | undefined, digits = 2) =>
  number == null || !Number.isFinite(number) ? '—' : number.toFixed(digits)
const running = (run: AutomatedRun | null) => !!run && !run.ended_at

/**
 * Simple motor station: read-only readiness happens automatically.
 * The start API and STM32 independently repeat every required safety check.
 * No status result here is used to override backend permissions.
 */
export default function HardwareMotorControls() {
  const [status, setStatus] = useState<HardwareStatus | null>(null)
  const [run, setRun] = useState<AutomatedRun | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [checking, setChecking] = useState(false)
  const preflightBusy = useRef(false)
  const activeRef = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true

    async function refresh() {
      try {
        const next = await api.hardwareMotorStatus()
        if (!mounted.current) return
        setStatus(next)
        if (next.active_run) {
          setRun(next.active_run)
          activeRef.current = !next.active_run.ended_at
        } else if (!activeRef.current) {
          activeRef.current = false
        }
      } catch {
        if (mounted.current) {
          setStatus(null)
          setError('Cannot reach the TRACE-X backend.')
        }
      }
    }

    async function checkReadiness() {
      if (preflightBusy.current || activeRef.current) return
      preflightBusy.current = true
      if (mounted.current) setChecking(true)
      try {
        // Read-only; does not ARM, switch relays, set PWM, or start a motor.
        await api.hardwareMotorPreflight()
        await refresh()
      } catch (err) {
        if (mounted.current) setError(String(err))
      } finally {
        preflightBusy.current = false
        if (mounted.current) setChecking(false)
      }
    }

    void refresh().then(() => checkReadiness())
    const statusTimer = window.setInterval(() => { void refresh() }, 1000)
    // Preflight expires after 15 s; refresh periodically without user interaction.
    const readinessTimer = window.setInterval(() => { void checkReadiness() }, 8000)
    return () => {
      mounted.current = false
      window.clearInterval(statusTimer)
      window.clearInterval(readinessTimer)
    }
  }, [])

  const runId = run?.id
  useEffect(() => {
    if (!runId) return
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/automated/${runId}`)
    socket.onmessage = event => {
      const next: AutomatedRun = JSON.parse(event.data)
      setRun(next)
      activeRef.current = !next.ended_at
      if (next.ended_at) socket.close()
    }
    socket.onerror = () => setError('Motor status stream unavailable. Use the physical power cutoff if a stop cannot be confirmed.')
    return () => { socket.close() }
  }, [runId])

  const active = running(run) || !!status?.active_run && running(status.active_run)
  const ready = !!status?.hardware_control && !checking && !pending && !active
  const pwm = status?.fixed_pwm_percent
  const maxDuration = status?.max_duration_ms ?? 30000
  const durationMs = Math.min(30000, maxDuration)
  const sample = active ? run?.latest_measurement : null
  const reason = !status
    ? 'Connecting to the Raspberry Pi…'
    : !status.profile_ready
      ? status.reason || 'Hardware profile needs commissioning.'
      : !status.hardware_control_enabled
        ? 'Pi hardware control has not been enabled.'
        : status.firmware_hardware_control === false
          ? 'STM32 firmware reports motor output disabled.'
          : status.preflight.reason || 'Checking STM32 and sensors…'

  async function start() {
    if (!ready || pwm == null || pwm <= 0 || durationMs < 100) return
    // Single explicit confirmation is the supervised operator authorization.
    if (!window.confirm(`Start the physical motor at ${pwm}% PWM for up to ${durationMs / 1000} seconds? Stay present with the physical power cutoff accessible.`)) return
    setPending(true)
    setError('')
    try {
      const next = await api.startAutomated({
        mode: 'hardware',
        device_id: status?.asset_id,
        tests: [`pwm_${pwm}`],
        duration_ms: durationMs,
        operator_authorized: true,
        supervised_confirmed: status?.operating_mode === 'SUPERVISED_TEST',
      })
      setRun(next)
      activeRef.current = true
    } catch (err) {
      setError(String(err))
    } finally {
      setPending(false)
    }
  }

  async function stop(emergency = false) {
    const current = status?.active_run ?? run
    if (!current) return
    setPending(true)
    setError('')
    try {
      await api.stopAutomated(current.id, emergency)
      // Do not claim motor shutdown until STM32 acknowledgment is reported.
    } catch (err) {
      setError(`Stop was not confirmed: ${String(err)}. Use the physical power cutoff.`)
    } finally {
      setPending(false)
    }
  }

  return <section className="panel motor-controls">
    <div className="panel-title">
      <div><p className="eyebrow">TRACE-X 2.0</p><h2>Motor Testing</h2></div>
      <span className="mode-chip">HARDWARE</span>
    </div>
    <p role="status">
      <strong>{active ? 'Running' : ready ? 'Ready' : checking ? 'Checking' : 'Not Ready'}</strong>
      {!ready && !active ? ` · ${reason}` : ''}
    </p>
    <section className="metric-grid motor-metrics" aria-label="Live motor measurements">
      <div className="metric"><span>Voltage</span><strong>{format(sample?.voltage)}<small> V</small></strong></div>
      <div className="metric"><span>Current</span><strong>{format(sample?.current)}<small> A</small></strong></div>
      <div className="metric"><span>Motor Speed</span><strong>{format(sample?.rpm, 0)}<small> RPM</small></strong></div>
      <div className="metric"><span>Power</span><strong>{format(sample?.input_power)}<small> W</small></strong></div>
    </section>
    <div className="driver-state">
      <div><span>PWM</span><strong>{pwm == null ? '—' : `${pwm}%`}</strong></div>
      <div><span>Test Duration</span><strong>{durationMs / 1000} seconds maximum</strong></div>
    </div>
    <div className="control-bar">
      <button className="primary" disabled={!ready || pwm == null || durationMs < 100} onClick={() => { void start() }}>START MOTOR</button>
      <button className="danger" disabled={!active} onClick={() => { void stop() }}>STOP MOTOR</button>
      <button className="estop" disabled={!active} onClick={() => { void stop(true) }}>EMERGENCY STOP</button>
    </div>
    {run && <p role="status">{run.state} · {run.stop_confirmed ? 'STM32 stop acknowledged' : 'Physical stop not independently verified'}</p>}
    {error && <p role="alert">{error}</p>}
    {run?.faults?.length ? <p role="alert">Faults: {run.faults.join(', ')}</p> : null}
    <p className="muted">Automatic checks remain active in the Pi backend and STM32. The physical cutoff is independent of this screen. RPM may be provisional until encoder calibration is verified.</p>
  </section>
}
