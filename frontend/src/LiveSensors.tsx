import { useEffect, useState } from 'react'
import INA219Readings from './INA219Readings'
import type { ElectricalBranch } from './types'

type LiveState = {
  ina219?: Record<string, ElectricalBranch>;
  enabled: boolean; connected: boolean; stale: boolean; error: string | null;
  sequence: number; recorded_motor_phase: string; warnings: string[];
  channels: Record<string, { value: number | string; quality: string; timestamp: string; age_seconds: number }>;
  diagnosis: { status: string; reason: string };
  hardware_connected: boolean; motor_format: string; complete_motor_frames: number; pending_motor_fields: string[];
  motor_sample: null | { motor_rpm: number; voltage: number; current: number; power: number;
    encoder_status: string; ina219_status: string; source: string; format: string;
    timestamp: string; timestamp_basis: string; age_seconds: number; stale: boolean; power_origin: string };
}

export default function LiveSensors() {
  const [state, setState] = useState<LiveState | null>(null)
  const [online, setOnline] = useState(false)
  useEffect(() => {
    let socket: WebSocket | undefined
    let retry: number | undefined
    let disposed = false
    function connect() {
      if (disposed) return
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/live`)
      socket.onmessage = event => { setState(JSON.parse(event.data)); setOnline(true) }
      socket.onclose = () => { setOnline(false); if (!disposed) retry = window.setTimeout(connect, 2000) }
      socket.onerror = () => setOnline(false)
    }
    connect()
    return () => { disposed = true; window.clearTimeout(retry); socket?.close() }
  }, [])
  const sample = state?.motor_sample
  const fresh = online && state?.hardware_connected && sample && !sample.stale
  const channel = (key: string) => {
    const reading = state?.channels[key]
    return online && state?.hardware_connected && reading?.quality !== 'STALE' ? reading?.value : undefined
  }
  const motorValue = (key: string, value?: number) =>
    state?.motor_format === 'plain_text' ? (fresh ? value : undefined) : channel(key)
  const show = (value: number | string | undefined, digits: number) =>
    typeof value === 'number' ? (value === 0 ? '0' : value.toFixed(digits)) : 'Unavailable'
  const status = (key: string, fallback?: string) => !online || !state?.hardware_connected ? 'Disconnected' :
    state.channels[key]?.quality === 'STALE' ? 'STALE' : state.channels[key]?.value ?? fallback ?? 'Not reported'
  return <>
    <header><div><p className="eyebrow">ACTUAL STM32 TELEMETRY · READ ONLY</p><h1>Live motor measurements</h1><p>STM32 USB → Pi backend → dashboard. No simulated values or motor commands on this page.</p></div></header>
    <section className="metric-grid" aria-label="Actual STM32 motor measurements">
      <div className="metric"><span>Motor RPM</span><strong>{show(motorValue('rpm', sample?.motor_rpm), 1)}<small> RPM</small></strong></div>
      <div className="metric"><span>Branch voltage</span><strong>{show(motorValue('voltage', sample?.voltage), 3)}<small> V</small></strong></div>
      <div className="metric"><span>Branch current</span><strong>{show(motorValue('current', sample?.current), 3)}<small> A</small></strong></div>
      <div className="metric"><span>Input power</span><strong>{show(motorValue('input_power', sample?.power), 3)}<small> W</small></strong></div>
    </section>
    <INA219Readings branches={state?.ina219} fresh={!!online && !!state?.hardware_connected && !state?.stale}/>
    <section className="panel"><h2>Connection</h2>
      <p>{!online ? 'Dashboard stream disconnected' : !state?.enabled ? 'Pi serial monitoring is not configured' : !state.connected ? 'Serial disconnected' : state.stale ? 'Serial open; telemetry missing or stale' : 'Receiving unverified hardware telemetry'}</p>
      <p>Direction: {channel('direction') ?? 'Unavailable'}</p>
      <p>Recorded motor event state: {online ? state?.recorded_motor_phase : 'Unknown'} · Received frames: {state?.sequence ?? 0}</p>
      <p>Protocol: {state?.motor_format ?? 'UNKNOWN'} · Complete motor cycles: {state?.complete_motor_frames ?? 0}</p>
      <p>Latest status observations · Encoder: {status('encoder_status', sample?.encoder_status)} · INA219: {status('ina219_status', sample?.ina219_status)}</p>
      {sample && <p>Source: {sample.source} · Last complete cycle: {new Date(sample.timestamp).toLocaleTimeString()} · {online ? `${sample.age_seconds.toFixed(2)} s old` : 'stream disconnected'} · Power: {sample.power_origin}</p>}
      {(!online || state?.stale) && <p role="status">Waiting for fresh hardware telemetry.</p>}
      {!sample && !!state?.pending_motor_fields?.length && <p>Missing cycle fields: {state.pending_motor_fields.filter(name => !/temp/i.test(name)).join(', ')}</p>}
      {state?.error && <p role="alert">{state.error}</p>}
      <p>Branch voltage/current/power are measured before the driver. Plain-text cycles are grouped within three seconds using unique fields; this is receive-time association, not proof of simultaneous acquisition. Sensor calibration and the encoder direction convention remain unverified.</p>
      <h2>Individual channel observations</h2><p>Partial readings below are separate from the complete-cycle tiles.</p>
      <div className="table-wrap"><table><thead><tr><th>Channel</th><th>Last reported value</th><th>Quality</th><th>Age (s)</th></tr></thead><tbody>
        {Object.entries(state?.channels ?? {}).filter(([key]) => key !== 'temperature').map(([key, c]) => <tr key={key}><td>{key}</td><td>{c.value} {({ voltage: 'V', current: 'A', rpm: 'RPM', temperature: '°C', recorded_power: 'W', input_power: 'W' } as Record<string, string>)[key] ?? ''}</td><td>{online ? c.quality : 'DISCONNECTED'}</td><td>{online ? c.age_seconds.toFixed(2) : 'Unknown'}</td></tr>)}
      </tbody></table></div>
      {!Object.keys(state?.channels ?? {}).length && <p>No sensor values received.</p>}
      <p>{state?.warnings.filter(warning => !/temp|ds18/i.test(warning)).join(' · ')}</p>
    </section>
    <section className="panel"><h2>Diagnostic readiness</h2><p>{state?.diagnosis.status ?? 'NO_DATA'}</p><p>{state?.diagnosis.reason ?? 'Connect the Pi receiver to begin checking measurement quality.'}</p>
      <p>Sensor availability and freshness can be checked now. Motor or circuit health requires the correct asset definition, verified measurement channels, and calibrated limits/baselines. No hardware health percentage is assigned.</p>
    </section>
  </>
}
