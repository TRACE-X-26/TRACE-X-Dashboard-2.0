import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { AutomatedRun, Recording, RecordingSummary } from './types'

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
  firmware_version?: string | null
  firmware_hardware_block_reason?: string | null
  preflight: { ready: boolean; reason: string; stale: boolean }
}

type LiveValue = { value: number | null; unit?: string; valid?: boolean }
type LiveSensors = {
  connected?: boolean
  stale?: boolean
  source?: string
  ina219?: Record<string, { calibrated?: boolean; valid?: boolean; stale?: boolean; measurements?: Record<string, LiveValue> }>
  rpm?: number | { value?: number | null; valid?: boolean }
  motor_sample?: { motor_rpm?: number | null; rpm?: number | null; voltage?: number | null; current?: number | null; power?: number | null; stale?: boolean }
  channels?: Record<string, { value?: number | null; quality?: string }>
}
const numeric = (value: number | null | undefined): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null
const format = (number: number | null | undefined, digits = 2) =>
  number == null || !Number.isFinite(number) ? '—' : number.toFixed(digits)
const running = (run: AutomatedRun | null) => !!run && !run.ended_at

/**
 * Simple motor station: no automatic repeating preflight and no extra UI readiness lock.
 * START always uses the protected backend endpoint; STM32 safety checks remain authoritative.
 */
export default function HardwareMotorControls() {
  const [status, setStatus] = useState<HardwareStatus | null>(null)
  const [live, setLive] = useState<LiveSensors | null>(null)
  const [recordings, setRecordings] = useState<RecordingSummary[]>([])
  const [savedExample, setSavedExample] = useState<Recording | null>(null)
  const [run, setRun] = useState<AutomatedRun | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [checking, setChecking] = useState(false)
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

    // Motor status stays live; operator requests a separate read-only preflight only when desired.
    async function refreshLive() {
      try {
        const response = await fetch('/api/live/status', { cache: 'no-store' })
        if (!response.ok) throw new Error('Live feed unavailable')
        const next: LiveSensors = await response.json()
        if (mounted.current) setLive(next)
      } catch {
        if (mounted.current) setLive(null)
      }
    }
    void refresh()
    void refreshLive()
    void api.recordings().then(items => {
      if (!mounted.current) return
      setRecordings(items)
      const newest = items[items.length - 1]
      if (newest) void api.recording(newest.id).then(item => {
        if (mounted.current) setSavedExample(item)
      }).catch(() => {})
    }).catch(() => {})
    const liveTimer = window.setInterval(() => { void refreshLive() }, 1000)
    const statusTimer = window.setInterval(() => { void refresh() }, 1000)
    return () => {
      mounted.current = false
      window.clearInterval(statusTimer)
      window.clearInterval(liveTimer)
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
  // Readiness is information, not a second frontend authorization gate.
  // Actual starts are accepted/rejected by the Pi backend and STM32.
  const canRequestStart = !!status && !pending && !active
  const pwm = status?.fixed_pwm_percent
  const maxDuration = status?.max_duration_ms ?? 30000
  const durationMs = Math.min(30000, maxDuration)
  const latestRun = status?.active_run ?? run
  const motorSensor = live?.ina219?.MOTOR
  const motorReadings = motorSensor?.measurements
  // No synthetic values: live cards use only values explicitly marked valid.
  const sensorsLive = live?.connected === true && live.stale !== true &&
    motorSensor?.stale !== true && motorSensor?.valid !== false
  const electrical = (key: string) => {
    const reading = motorReadings?.[key]
    return sensorsLive && reading?.valid === true ? numeric(reading.value) : null
  }
  const rpmReading = live?.rpm
  const sensorRpm = sensorsLive
    ? (typeof rpmReading === 'number' ? numeric(rpmReading)
      : rpmReading?.valid === true ? numeric(rpmReading.value)
      : live?.motor_sample?.stale === false ? numeric(live.motor_sample.motor_rpm ?? live.motor_sample.rpm)
      : live?.channels?.rpm?.quality !== 'STALE' ? numeric(live?.channels?.rpm?.value) : null)
    : null
  const sample = active ? latestRun?.latest_measurement : null
  const value = (key: 'voltage' | 'current' | 'rpm' | 'input_power') => {
    const activeValue = numeric(sample?.[key])
    if (activeValue !== null) return activeValue
    if (key === 'rpm') return sensorRpm
    const electricalValue = electrical(key === 'input_power' ? 'power' : key)
    if (electricalValue !== null) return electricalValue
    const sampleKey = key === 'input_power' ? 'power' : key
    return sensorsLive && live?.motor_sample?.stale === false ? numeric(live.motor_sample[sampleKey]) : null
  }
  const firmwareBlock = status?.firmware_hardware_block_reason
  const reason = !status
    ? 'Connecting to the Raspberry Pi…'
    : !status.profile_ready
      ? status.reason || 'Hardware profile needs commissioning.'
      : !status.hardware_control_enabled
        ? 'Pi hardware control has not been enabled.'
        : status.firmware_hardware_control === false
          ? `STM32 motor output disabled: ${firmwareBlock || status.preflight.reason || 'no block reason reported'}`
          : status.preflight.reason || 'Checking STM32 and sensors…'

  async function checkHardware() {
    if (checking || pending || active) return
    setChecking(true)
    setError('')
    try {
      const result = await api.hardwareMotorPreflight()
      setError(result.ready ? '' : result.reason || 'Hardware check did not pass')
    } catch (err) {
      setError(String(err))
    } finally {
      try {
        setStatus(await api.hardwareMotorStatus())
      } catch (err) {
        setError(`Unable to refresh hardware status: ${String(err)}`)
      }
      setChecking(false)
    }
  }

  async function start() {
    if (!canRequestStart || pwm == null || pwm <= 0 || durationMs < 100) return
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
      <strong>{active ? 'Running' : checking ? 'Checking hardware' : status ? 'Idle' : 'Connecting'}</strong>
      {!active && status && !status.hardware_control ? ` · ${reason}` : ''}
    </p>
    {status && <p className="muted" role="status">STM32 firmware: {status.firmware_version || 'Not yet identified — use CHECK HARDWARE'} · {status.firmware_hardware_control === true ? 'Motor output configured' : status.firmware_hardware_control === false ? `Output blocked: ${firmwareBlock || 'reason unavailable'}` : 'Firmware output state not yet checked'}</p>}
    <section className="metric-grid motor-metrics" aria-label="Live motor measurements">
      <div className="metric"><span>Voltage</span><strong>{format(value('voltage'))}<small> V</small></strong></div>
      <div className="metric"><span>Current</span><strong>{format(value('current'))}<small> A</small></strong></div>
      <div className="metric"><span>Motor Speed</span><strong>{format(value('rpm'), 0)}<small> RPM</small></strong></div>
      <div className="metric"><span>Power</span><strong>{format(value('input_power'))}<small> W</small></strong></div>
    </section>
    <p className="muted" role="status">
      Sensor feed: {live == null ? 'Unavailable' : live.connected !== true ? 'Disconnected' : live.stale ? 'Stale' : 'Connected'}
      {' · '}Motor INA219: {motorSensor == null ? 'Not reported' : motorSensor.stale ? 'Stale' : motorSensor.valid === false ? 'Invalid' : 'Reporting'}
      {' · '}Values marked — are unavailable, not zero. Motor relay may be OFF while sensors still report.
    </p>
    <div className="driver-state">
      <div><span>PWM</span><strong>{pwm == null ? '—' : `${pwm}%`}</strong></div>
      <div><span>Test Duration</span><strong>{durationMs / 1000} seconds maximum</strong></div>
    </div>
    <div className="control-bar">
      <button className="primary" disabled={!canRequestStart || pwm == null || pwm <= 0 || durationMs < 100} onClick={() => { void start() }}>START MOTOR</button>
      <button className="secondary" disabled={checking || pending || active} onClick={() => { void checkHardware() }}>CHECK HARDWARE</button>
      <button className="danger" disabled={!active} onClick={() => { void stop() }}>STOP MOTOR</button>
      <button className="estop" disabled={!active} onClick={() => { void stop(true) }}>EMERGENCY STOP</button>
    </div>
    {run && <p role="status">{run.state} · {run.stop_confirmed ? 'STM32 stop acknowledged' : 'Physical stop not independently verified'}</p>}
    {error && <p role="alert">{error}</p>}
    {run?.faults?.length ? <p role="alert">Faults: {run.faults.join(', ')}</p> : null}
    <section aria-label="Previously recorded motor tests" className="panel">
      <h3>Previous motor test recordings</h3>
      <p className="muted">Saved measurements from earlier tests — not live data. Shown even if today's motor start is blocked.</p>
      {savedExample && <div className="metric-grid" aria-label="Recorded measurement averages">
        {(['voltage', 'current', 'rpm', 'input_power'] as const).map(key => {
          const metric = savedExample.features[key]
          return <div className="metric" key={key}>
            <span>Recorded {key === 'input_power' ? 'power' : key}</span>
            <strong>{format(metric?.mean)}<small> {({ voltage: 'V', current: 'A', rpm: 'RPM', input_power: 'W' })[key]}</small></strong>
          </div>
        })}
      </div>}
      {savedExample && <p className="muted">Historical recording: {savedExample.metadata.filename} · {savedExample.analysis_status} · averages shown above are not live measurements.</p>}
      {recordings.length === 0 ? <p>No previously imported recordings found. Historical results can be imported through the backend.</p>
        : <ul>{recordings.slice(-5).reverse().map(item =>
          <li key={item.id}>
            <strong>{item.metadata.filename}</strong>
            {' · '}{item.metadata.condition || 'Condition not specified'}
            {' · '}{item.imported_at}
            {' · '}<a href={`/api/recordings/${item.id}`} target="_blank" rel="noreferrer">View saved recording data</a>
          </li>)}</ul>}
    </section>
    <p className="muted">The dashboard does not repeatedly preflight or impose a second readiness gate. START may be rejected by the Pi or STM32 if the relay configuration, sensing, or output protections are invalid. CHECK HARDWARE is read-only. Keep the physical cutoff accessible; RPM remains provisional until encoder calibration.</p>
  </section>
}
