import { useEffect, useState } from 'react'
import { api } from './api'
import HardwareMotorControls from './HardwareMotorControls'
import type { AutomatedRun, ElectricalBranch } from './types'

type CircuitSession = { id: string; state: string; power_on: boolean | null; stop_confirmed: boolean;
  ended_at: string | null; reason: string; measurements?: ElectricalBranch }
export type StationStatus = { selected_branch: 'MOTOR' | 'CIRCUIT' | null; circuit: CircuitSession | null;
  motor: AutomatedRun | null; hardware_runtime_enabled: boolean }

export default function TestStation() {
  const [status, setStatus] = useState<StationStatus | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [duration, setDuration] = useState(30)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let mounted = true
    const refresh = () => api.stationStatus().then(next => { if (mounted) setStatus(next) })
      .catch(err => { if (mounted) setError(String(err)) })
    refresh()
    const timer = window.setInterval(refresh, 750)
    return () => {
      mounted = false; window.clearInterval(timer)
      // Leaving the station requests shutdown; MCU heartbeat/deadline remain independent.
      api.circuitPower(false).catch(() => {})
    }
  }, [])
  const circuit = status?.circuit
  const circuitActive = !!circuit && !circuit.ended_at
  const busy = circuitActive || (!!status?.motor && !status.motor.ended_at)
  async function select(branch: 'MOTOR' | 'CIRCUIT') {
    setPending(true); setError(''); setConfirmed(false)
    try { await api.selectBranch(branch); setStatus(await api.stationStatus()) }
    catch (err) { setError(String(err)) }
    finally { setPending(false) }
  }
  async function power(on: boolean) {
    setPending(true); setError('')
    try { await api.circuitPower(on, Math.round(duration * 1000), confirmed); setStatus(await api.stationStatus()); setConfirmed(false) }
    catch (err) { setError(String(err)) }
    finally { setPending(false) }
  }
  return <>
    <header><div><p className="eyebrow">TRACE-X TEST STATION</p><h1>What are you testing?</h1><p>Choose a branch, then press Start Motor or Circuit Power On. Choosing alone keeps power off.</p></div></header>
    <section className="branch-choice" aria-label="Select test branch">{(['MOTOR', 'CIRCUIT'] as const).map(branch =>
      <button key={branch} className={status?.selected_branch === branch ? 'branch-card selected' : 'branch-card'}
        aria-pressed={status?.selected_branch === branch} disabled={busy || pending || !status} onClick={() => select(branch)}>
        <strong>{branch === 'MOTOR' ? 'Motor' : 'Circuit'}</strong><span>{branch === 'MOTOR' ? 'Speed, current and motor health' : 'Supply power and circuit measurements'}</span>
      </button>)}</section>
    {error && <p role="alert">{error}</p>}
    {status?.selected_branch === 'MOTOR' && <HardwareMotorControls/>}
    {status?.selected_branch === 'CIRCUIT' && <section className="panel">
      <div className="panel-title"><div><h2>Circuit supply</h2><p>Real STM32 · INA219 0x41 · D5 relay channel 2</p></div><span className="mode-chip">HARDWARE</span></div>
      <p>Manual supervised supply session, up to 30 seconds. Test-point fault diagnosis remains in Advanced tools.</p>
      {!status.hardware_runtime_enabled && <p role="status">Hardware runtime is disabled. Power On requires the commissioned Pi profile and explicit hardware permission.</p>}
      <label><input type="checkbox" checked={confirmed} disabled={circuitActive || pending} onChange={e => setConfirmed(e.target.checked)}/> I am supervising, the circuit supply is appropriate, and the physical cutoff is accessible.</label>
      <div className="control-bar"><label>Duration (seconds)<input type="number" min="0.1" max="30" step="0.1" value={duration} disabled={circuitActive || pending} onChange={e => setDuration(Number(e.target.value))}/></label>
        <button className="primary" disabled={!status.hardware_runtime_enabled || !confirmed || busy || pending || !Number.isFinite(duration) || duration < .1 || duration > 30} onClick={() => power(true)}>Circuit Power On</button>
        <button className="danger" disabled={pending} onClick={() => power(false)}>Circuit Power Off</button></div>
      <p role="status">{circuit ? `${circuit.state} · ${circuit.reason || 'Waiting for STM32 acknowledgment'}` : 'No circuit session started.'}</p>
      <p>{circuit?.stop_confirmed ? 'STM32 relay-off command acknowledged. Physical power is not measured by a relay feedback input.' : 'Relay-off acknowledgment not yet available.'}</p>
      <section className="metric-grid">{(['voltage', 'current', 'power'] as const).map(key => {
        const branch = circuit?.measurements; const item = branch?.measurements[key]
        return <div className="metric" key={key}><span>Circuit {key}</span><strong>{circuitActive && branch?.valid && item?.valid && item.value != null ? item.value.toFixed(3) : '—'}<small> {({ voltage: 'V', current: 'A', power: 'W' })[key]}</small></strong></div>
      })}</section>
      <p>Sensor: {circuitActive ? circuit?.measurements?.status ?? 'Waiting' : 'Not live'} · Calibration: {circuit?.measurements?.calibrated ? 'verified' : 'unverified'}. Supply current does not identify individual circuit faults.</p>
      {circuit?.ended_at && <a href={`/api/station/circuit/${circuit.id}/csv`}>Download circuit supply CSV</a>}
    </section>}
  </>
}
