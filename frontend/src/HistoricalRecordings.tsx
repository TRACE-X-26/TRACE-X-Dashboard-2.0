import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from './api'
import type { MotorHealthReplay, Recording, RecordingSummary } from './types'

export default function HistoricalRecordings() {
  const [replay, setReplay] = useState<MotorHealthReplay | null>(null)
  const [archivePath, setArchivePath] = useState('')
  const [replayError, setReplayError] = useState('')
  const archived = replay?.runs[archivePath]
  const [recordings, setRecordings] = useState<RecordingSummary[]>([])
  const [result, setResult] = useState<Recording | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [device, setDevice] = useState('MOTOR-001')
  const [mass, setMass] = useState('')
  const [pwm, setPwm] = useState('')
  const [condition, setCondition] = useState('UNKNOWN')
  const [fixture, setFixture] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.recordings().then(setRecordings).catch(e => setError(String(e))) }, [])
  useEffect(() => { api.motorHealthReplay().then(setReplay).catch(e => setReplayError(String(e))) }, [])
  async function importFile() {
    if (!file) return
    setBusy(true); setError('')
    try {
      if (file.size > 2_000_000) throw new Error('Choose a CSV smaller than 2 MB.')
      const next = await api.importRecording({ filename: file.name, device_id: device,
        condition, attached_mass_g: mass === '' ? null : Number(mass),
        fixture_description: fixture, target_pwm_percent: pwm === '' ? null : Number(pwm) }, await file.text())
      setResult(next); setRecordings(await api.recordings())
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  async function select(id: number) {
    setError('')
    try { setResult(await api.recording(id)) } catch (e) { setError(String(e)) }
  }
  return <>
    <header><div><p className="eyebrow">HISTORICAL DATA</p><h1>Motor recordings</h1><p>Import saved CSV data without activating hardware. Calibration remains unverified.</p></div></header>
    <section className="panel">
      <div className="control-bar">
        <label>CSV file<input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] ?? null)}/></label>
        <label>Device<input value={device} onChange={e => setDevice(e.target.value)}/></label>
        <label>Experiment condition<input value={condition} onChange={e => setCondition(e.target.value)}/></label>
        <label>Attached mass (g)<input type="number" min="0" step="any" value={mass} onChange={e => setMass(e.target.value)}/></label>
        <label>Target PWM (%)<input type="number" min="0" max="100" step="any" value={pwm} onChange={e => setPwm(e.target.value)}/></label>
        <label>Fixture description<input value={fixture} onChange={e => setFixture(e.target.value)}/></label>
        <button className="primary" disabled={!file || busy || !device} onClick={importFile}>{busy ? 'Importing…' : 'Import recording'}</button>
      </div>
      <p>Mass and target PWM are operator labels. PWM is not independently measured. Reimporting identical CSV content returns the original recording and metadata.</p>
      {error && <p role="alert">{error}</p>}
      <label>Saved recording<select value={result?.id ?? ''} onChange={e => { if (e.target.value) void select(Number(e.target.value)) }}>
        <option value="">Select recording</option>{recordings.map(r => <option key={r.id} value={r.id}>#{r.id} · {r.metadata.filename} · {r.metadata.condition}</option>)}
      </select></label>
    </section>
    {(replayError || (replay && Object.keys(replay.runs).length > 0)) && <section className="panel">
      <h2>Motor test archive replay</h2>
      {replayError && <p role="alert">{replayError}</p>}
      {replay && <>
        <p>Historical results · Baseline pending</p>
        <p>Tests without archive records: {Object.entries(replay.test_catalog).filter(([, test]) => !test.present_in_archive).map(([id, test]) => `${id} · ${test.name}`).join(', ') || 'None'}</p>
        <label>Archived run<select value={archivePath} onChange={e => setArchivePath(e.target.value)}>
          <option value="">Select archived run</option>
          {Object.entries(replay.runs).map(([path, run]) => <option key={path} value={path}>{run.test_name ?? 'Unknown test'} · {path.split('/').pop()}</option>)}
        </select></label>
        {archived && <>
          <p>Health: {archived.status === 'not_assessed' ? 'Not assessed' : archived.status.replaceAll('_', ' ')} · Recorded PWM target: {archived.target_pwm_percent.join(', ') || 'Unavailable'}{archived.target_pwm_percent.length > 0 ? '%' : ''} · Reported PWM: Unavailable</p>
          <p>{archived.reasons.filter(reason => reason !== 'housing_temperature_unverified').map(reason => reason.replaceAll('_', ' ')).join(' · ')}</p>
          <div className="table-wrap"><table><thead><tr><th>Channel</th><th>Median</th><th>Min</th><th>Max</th><th>Samples</th></tr></thead><tbody>
            {Object.entries(archived.metrics).filter(([name]) => name !== 'motor_temperature_C').map(([name, metric]) => <tr key={name}><td>{name}</td><td>{metric.median}</td><td>{metric.min}</td><td>{metric.max}</td><td>{metric.samples}</td></tr>)}
          </tbody></table></div>
        </>}
      </>}
    </section>}
    {result && <>
      <section className="panel"><h2>{result.metadata.filename}</h2>
        <p>{result.source} · {result.analysis_status} · {result.samples.length} extracted rows · {result.running_samples} RUNNING rows</p>
        <p>Device: {result.metadata.device_id} · Condition: {result.metadata.condition} · Attached mass: {result.metadata.attached_mass_g ?? 'unknown'} g · Target PWM: {result.metadata.target_pwm_percent ?? 'unknown'}%</p>
        <p>Fixture: {result.metadata.fixture_description || 'Not provided'}</p>
        {result.metadata.filename_mass_label_g != null && <p>Unverified filename mass label: {result.metadata.filename_mass_label_g} g. Fixture and actual mass remain unconfirmed.</p>}
        <p>Timestamp basis: {result.timestamp_basis ?? 'Unverified'}</p>
        {!!result.metadata.recorded_target_pwm_labels?.length && <p>CSV target PWM labels: {result.metadata.recorded_target_pwm_labels.join(', ')}%. These are commanded targets, not measured PWM.</p>}
        <p>Recorded direction labels: {[...new Set(result.samples.map(s => s.direction).filter(Boolean))].join(', ') || 'Unavailable'} (calibration unverified)</p>
        {result.limitations.filter(text => !/temperature/i.test(text)).map(s => <p key={s}>{s}</p>)}
        <div className="table-wrap"><table><thead><tr><th>RUNNING channel</th><th>Count</th><th>Mean</th><th>Min</th><th>Max</th><th>Std</th></tr></thead><tbody>
          {Object.entries(result.features).filter(([name]) => name !== 'temperature').map(([name, f]) => <tr key={name}><td>{name}</td><td>{f.count}</td>{[f.mean, f.min, f.max, f.std].map((v, i) => <td key={i}>{v == null ? 'Unavailable' : v.toFixed(3)}</td>)}</tr>)}
        </tbody></table></div>
      </section>
      {result.recorded_features && <section className="panel"><h2>All recorded phases</h2><p>Descriptive channel statistics only; includes pre-start and post-stop values and receive-buffer bursts. Not a steady-state or calibrated baseline.</p>
        <div className="table-wrap"><table><thead><tr><th>Channel</th><th>Count</th><th>Mean</th><th>Min</th><th>Max</th></tr></thead><tbody>{Object.entries(result.recorded_features).filter(([name]) => name !== 'temperature').map(([name, f]) => <tr key={name}><td>{name}</td><td>{f.count}</td>{[f.mean, f.min, f.max].map((v, i) => <td key={i}>{v == null ? 'Unavailable' : v.toFixed(3)}</td>)}</tr>)}</tbody></table></div>
      </section>}
      <section className="panel"><h2>Recorded signals</h2><p>Row sequence; isolated points preserve missing channels without joining asynchronous readings. Voltage (V), current (A), power (W) on left; signed RPM on right.</p>
        <ResponsiveContainer width="100%" height={320}><LineChart data={result.samples}>
          <CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="sequence"/><YAxis yAxisId="electrical"/><YAxis yAxisId="speed" orientation="right"/><Tooltip/>
          <Line yAxisId="electrical" dataKey="voltage" name="Branch voltage (V)" stroke="#53c7f0" dot={{ r: 2 }}/><Line yAxisId="electrical" dataKey="current" name="Branch current (A)" stroke="#ffb24c" dot={{ r: 2 }}/><Line yAxisId="electrical" dataKey="recorded_power" name="Recorded branch power (W)" stroke="#6bcf85" dot={{ r: 2 }}/><Line yAxisId="speed" dataKey="rpm" name="Reported signed RPM" stroke="#9b87f5" dot={{ r: 2 }}/>
        </LineChart></ResponsiveContainer>
      </section>
      <section className="panel"><h2>Data quality ({result.warnings.filter(w => !/temp/i.test(w.code)).length} warnings)</h2>
        <p>{[...new Set(result.warnings.filter(w => !/temp/i.test(w.code)).map(w => w.code))].join(' · ') || 'No parser warnings'}</p>
        <div className="table-wrap"><table><thead><tr><th>CSV line</th><th>Timestamp</th><th>Phase</th><th>Warnings</th></tr></thead><tbody>{result.samples.slice(0, 100).map(s => <tr key={s.sequence}><td>{s.line}</td><td>{s.timestamp}</td><td>{s.phase}</td><td>{s.warnings.filter(w => !/temp/i.test(w)).join(', ')}</td></tr>)}</tbody></table></div><p>Showing first 100 extracted rows. Full parsed results remain available through the API.</p>
      </section>
    </>}
  </>
}
