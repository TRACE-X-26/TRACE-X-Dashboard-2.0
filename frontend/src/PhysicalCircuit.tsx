import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import Circuit4Diagram from './Circuit4Diagram'
import type { CircuitCapture, CircuitTelemetry, PhysicalCircuitAsset, PhysicalCircuitPoint } from './types'

const channels: Record<PhysicalCircuitPoint['channel'], string> = {
  test_point_voltage: 'Probe test-point voltage (V)', circuit_supply_voltage: 'INA219 circuit supply (V)',
  circuit_current: 'INA219 circuit current (A)', circuit_power: 'Circuit branch power (W)',
}
type PointForm = Omit<PhysicalCircuitPoint, 'minimum' | 'maximum'> & { minimum: string; maximum: string }
const emptyPoint = (): PointForm => ({ point_id: '', label: '', instruction: '', channel: 'test_point_voltage', minimum: '', maximum: '' })

export default function PhysicalCircuit() {
  const [assets, setAssets] = useState<PhysicalCircuitAsset[]>([])
  const [history, setHistory] = useState<CircuitCapture[]>([])
  const [selected, setSelected] = useState('')
  const [session, setSession] = useState<CircuitCapture | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [telemetry, setTelemetry] = useState<CircuitTelemetry | null>(null)
  const [online, setOnline] = useState(false)
  const [conditionsConfirmed, setConditionsConfirmed] = useState(false)
  const [references, setReferences] = useState<Awaited<ReturnType<typeof api.circuit4ReferenceAnalysis>> | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ asset_id: '', name: '', supply_voltage: '', components: '', connections: '' })
  const [points, setPoints] = useState<PointForm[]>([emptyPoint()])
  const point = session?.asset.test_points[session.readings.length]
  useEffect(() => {
    Promise.all([api.physicalCircuits(), api.circuitCaptureHistory()]).then(([a, h]) => { setAssets(a); setHistory(h); setSelected(a[0]?.asset_id ?? '') }).catch(e => setError(String(e)))
  }, [])
  useEffect(() => {
    let active = true
    async function refresh() {
      try { const result = await api.circuitTelemetry(); if (active) { setTelemetry(result); setOnline(true) } }
      catch { if (active) setOnline(false) }
    }
    void refresh()
    const timer = window.setInterval(refresh, 1000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  async function action(operation: () => Promise<CircuitCapture>) {
    setBusy(true); setError('')
    try { const result = await operation(); setSession(result); setHistory(await api.circuitCaptureHistory()) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const asset = await api.savePhysicalCircuit({ ...form, supply_voltage: Number(form.supply_voltage),
        test_points: points.map(p => ({ ...p, minimum: Number(p.minimum), maximum: Number(p.maximum) })) })
      setAssets(await api.physicalCircuits()); setSelected(asset.asset_id); setEditing(false)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  const asset = assets.find(a => a.asset_id === selected)
  const isCircuit4 = asset?.diagnostic_model === 'circuit4-lm324-v1'
  return <>
    <header><div><p className="eyebrow">HARDWARE CAPTURE · UNVERIFIED</p><h1>Test a physical circuit</h1><p>Configure the built circuit, confirm probe placement, and capture STM32 readings.</p></div></header>
    <section className="panel"><p>Capture is read-only: it does not energize relays, switch branches, or start a motor. Expected ranges are operator supplied and remain unverified. Probe presence and measurement-range switching are unavailable. Resistance/continuity are unsupported without verified excitation and protection.</p>
      <div className="control-bar"><label>Built circuit<select value={selected} disabled={busy || session?.state === 'IN_PROGRESS'} onChange={e => setSelected(e.target.value)}><option value="">Choose circuit</option>{assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.name}</option>)}</select></label>
        <button className="secondary" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? 'Close configuration' : 'Add circuit definition'}</button>
        <button className="primary" disabled={!asset || busy || session?.state === 'IN_PROGRESS' || (isCircuit4 && !conditionsConfirmed)} onClick={() => action(() => api.startCircuitCapture(selected, conditionsConfirmed))}>Start capture session</button>
      </div>
      {asset && <><h2>{asset.name} · {asset.supply_voltage} V nominal</h2><p>Components: {asset.components}</p><p>Connections: {asset.connections}</p></>}
      {!assets.length && <p>No physical circuit is configured. Enter the actual built components and measured/expected ranges; no example circuit is assumed.</p>}
      {isCircuit4 && <><p>TP0–TP4 are sequential measurements relative to GND. Normal operation is S1 closed, S2 open, RV1 approximately 2.0 V. Never give the classifier the introduced fault as an input.</p>
        <label className="fixture-confirm"><input type="checkbox" checked={conditionsConfirmed} onChange={e => setConditionsConfirmed(e.target.checked)}/>I will keep the supply, potentiometer and switch states unchanged throughout TP0–TP4 capture.</label>
        <details><summary>Show Circuit 4 topology and multimeter references</summary><Circuit4Diagram/>
          <div className="table-wrap"><table><thead><tr><th>Point</th><th>Normal (V)</th><th>S1 open (V)</th><th>S2 shunt (V)</th></tr></thead><tbody>{['TP0','TP1','TP2','TP3','TP4'].map(id => <tr key={id}><td>{id}</td>{['NORMAL','S1_OPEN','S2_SHUNT'].map(label => <td key={label}>{asset.reference_values?.[label]?.[id]}</td>)}</tr>)}</tbody></table></div>
          <p>References are the supplied multimeter readings; TP0 is nominal/expected ≈5 V. The comparison tolerances are provisional and STM32 calibration is not verified.</p>
          <button className="secondary" onClick={async () => { try { setReferences(await api.circuit4ReferenceAnalysis()) } catch(e) { setError(String(e)) } }}>Check rules against supplied multimeter examples</button>
          {references && <div><p>RECORDED MULTIMETER REFERENCE · not live STM32 measurements</p>{references.cases.map(c => <p key={c.label}>{c.label}: {c.diagnostic.classification}</p>)}<p>Matching three supplied examples is not an independent accuracy or repeatability validation.</p></div>}
        </details></>}
    </section>
    <section className="panel"><h2>Circuit sensor connection</h2><p>{!online ? 'Backend disconnected' : !telemetry?.enabled ? 'Serial receiver not configured' : !telemetry.connected ? 'STM32 disconnected' : 'Receiver connected · calibration unverified'}</p>
      {online && telemetry?.warnings?.filter(w => !/temp|ds18/i.test(w)).map(warning => <p key={warning} role="status">{warning}</p>)}
      {telemetry?.error && <p role="alert">{telemetry.error}</p>}
      <div className="table-wrap"><table><thead><tr><th>Point</th><th>Channel</th><th>Reading</th><th>Quality</th><th>Age (s)</th></tr></thead><tbody>{telemetry?.circuit_channels?.filter(c => c.asset_id === (session?.asset.asset_id ?? selected)).map(c => <tr key={`${c.point_id}-${c.channel}`}><td>{c.point_id}</td><td>{c.channel}</td><td>{online && telemetry?.connected && c.quality !== 'STALE' ? c.value : 'Unavailable'} {c.channel === 'circuit_current' ? 'A' : c.channel === 'circuit_power' ? 'W' : 'V'}</td><td>{online ? c.quality : 'DISCONNECTED'}</td><td>{online ? c.age_seconds.toFixed(2) : 'Unknown'}</td></tr>)}</tbody></table></div>
      <p>Supply measurements and probe voltage are distinct channels. ADC divider conversion belongs in calibrated firmware; engineering-value telemetry is not scaled again.</p>
    </section>
    {editing && <form className="panel profile-form" onSubmit={save}><h2>Actual circuit definition</h2><div className="form-grid">
      {(['asset_id', 'name', 'supply_voltage', 'components', 'connections'] as const).map(key => <label key={key}>{({asset_id:'Asset ID (must match telemetry)', name:'Circuit name', supply_voltage:'Nominal supply (V)', components:'Components and values', connections:'Node connections / topology'})[key]}<input required type={key === 'supply_voltage' ? 'number' : 'text'} step="any" min={key === 'supply_voltage' ? '0.001' : undefined} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}/></label>)}
      </div>{points.map((p, i) => <fieldset key={i}><legend>Measurement {i + 1}</legend><div className="form-grid">
        {(['point_id', 'label', 'instruction', 'minimum', 'maximum'] as const).map(key => <label key={key}>{({point_id:'Unique test-point ID',label:'Label',instruction:'Probe placement instruction',minimum:'Expected minimum (channel units)',maximum:'Expected maximum (channel units)'})[key]}<input required type={key === 'minimum' || key === 'maximum' ? 'number' : 'text'} step="any" value={p[key]} onChange={e => setPoints(points.map((v, n) => n === i ? { ...v, [key]: e.target.value } : v))}/></label>)}
        <label>Measurement channel<select value={p.channel} onChange={e => setPoints(points.map((v,n) => n === i ? { ...v, channel: e.target.value as PointForm['channel'] } : v))}>{Object.entries(channels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      </div>{points.length > 1 && <button type="button" className="secondary" onClick={() => setPoints(points.filter((_, n) => n !== i))}>Remove measurement</button>}</fieldset>)}
      <div className="button-row"><button type="button" className="secondary" disabled={points.length >= 20} onClick={() => setPoints([...points, emptyPoint()])}>Add test point</button><button className="primary" disabled={busy}>Save circuit definition</button></div>
    </form>}
    {error && <p className="circuit-error" role="alert">{error}</p>}
    {session && <section className="panel"><h2>Capture #{session.id} · {session.asset.name}</h2><p>{session.state} · {session.condition}</p>
      {session.state === 'IN_PROGRESS' && point && <><h2>{point.point_id} · {point.label}</h2><p>{point.instruction}</p><p>{channels[point.channel]} · Expected {point.minimum}–{point.maximum}</p>
        <div className="safety-note">Confirm the physical probe position. After confirmation, wait for a new matching STM32 reading before capture. Limits and calibration are unverified.</div>
        <div className="button-row"><button className="secondary" disabled={busy} onClick={() => action(() => api.armCircuitCapture(session.id, point.point_id))}>Confirm probe placement</button><button className="primary" disabled={busy || !session.armed_at} onClick={() => action(() => api.captureCircuitPoint(session.id))}>Capture fresh reading</button></div>
        {session.armed_at && <p>Probe confirmed. Waiting for fresh telemetry with this asset ID, point ID and channel.</p>}
      </>}
      {session.readings.map(r => <div className="test-point-result" key={r.point_id}><strong>{r.point_id}</strong><div><strong>{r.measured} {r.unit} · {r.result}</strong><p>{r.explanation}</p><p>Expected {r.minimum}–{r.maximum} {r.unit}</p></div><span>{new Date(r.timestamp).toLocaleTimeString()}</span></div>)}
      {session.diagnostic && <section className="circuit4-diagnostic"><h2>Predicted classification: {session.diagnostic.classification}</h2><p>{session.diagnostic.reason}</p>{session.diagnostic.suspected_region && <p>Suspected region: {session.diagnostic.suspected_region}</p>}<p>{session.diagnostic.verification}</p>
        <div className="table-wrap"><table><thead><tr><th>Point</th><th>Measured (V)</th><th>Normal reference (V)</th><th>Difference (V)</th><th>Deviation (%)</th></tr></thead><tbody>{session.diagnostic.normal_deviations.map(r => <tr key={r.point_id}><td>{r.point_id}</td><td>{r.measured.toFixed(4)}</td><td>{r.normal_reference.toFixed(4)}</td><td>{r.difference_V.toFixed(4)}</td><td>{r.deviation_percent.toFixed(1)}%</td></tr>)}</tbody></table></div>
        {session.diagnostic.limitations.map(s => <p key={s}>{s}</p>)}
      </section>}
      <p>Range comparisons do not establish a calibrated health score or uniquely identify a faulty component.</p>
    </section>}
    <section className="panel"><h2>Saved physical tests</h2><p>Separate from simulation and motor history.</p><div className="session-list">{history.map(h => <button className="session" key={h.id} disabled={busy} onClick={() => setSession(h)}><span>#{h.id} · {h.asset.name}</span><span>{h.state} · {h.readings.length}/{h.asset.test_points.length} · {h.condition}</span></button>)}</div>{!history.length && <p>No hardware captures saved.</p>}</section>
  </>
}
