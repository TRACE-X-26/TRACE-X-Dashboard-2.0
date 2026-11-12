import { captureRunConditions } from './runConditions'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, testSocket } from './api'
import HistoricalRecordings from './HistoricalRecordings'
import LiveSensors from './LiveSensors'
import PhysicalCircuit from './PhysicalCircuit'
import HardwareMotorControls from './HardwareMotorControls'
import TestStation from './TestStation'
import type { AutomatedRun, RegisteredTest, Baseline, CircuitProfile, CircuitReport, Finding, Measurement, MeterReading, MotorStatus, Profile, Report, Session, SessionDetail } from './types'

type Page = 'station' | 'dashboard' | 'control' | 'meter' | 'circuit' | 'test' | 'history' | 'profiles' | 'recordings' | 'sensors'

const NAV: { key: Page; label: string; icon: string }[] = [
  { key: 'sensors', label: 'STM32 sensors', icon: '⌁' },
  { key: 'recordings', label: 'CSV recordings', icon: '▤' },
  { key: 'dashboard', label: 'Overview', icon: '⌂' },
  { key: 'control', label: 'Motor control', icon: '◉' },
  { key: 'meter', label: 'Live multimeter', icon: '⌁' },
  { key: 'circuit', label: 'Circuit diagnostics', icon: '◇' },
  { key: 'test', label: 'Run diagnostic', icon: '▶' },
  { key: 'history', label: 'Test history', icon: '◷' },
  { key: 'profiles', label: 'Device profiles', icon: '▣' },
]

function fmt(value: number | null | undefined, digits = 1) {
  return value == null ? '—' : value.toFixed(digits)
}

function Status({ value }: { value: string | null }) {
  const state = (value ?? 'UNKNOWN').toLowerCase()
  return <span className={`status status-${state}`}>{value ?? 'Not evaluated'}</span>
}

function Metric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}<small>{unit}</small></strong></div>
}

function SignalChart({ data }: { data: Measurement[] }) {
  if (!data.length) return <div className="empty-chart">Measurements will appear here during the test.</div>
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ top: 12, right: 16, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="sequence" stroke="var(--muted)" tickLine={false} />
          <YAxis yAxisId="electrical" stroke="var(--muted)" tickLine={false} />
          <YAxis yAxisId="speed" orientation="right" stroke="var(--muted)" tickLine={false} />
          <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10 }} />
          <Line yAxisId="electrical" type="monotone" dataKey="voltage" name="Voltage (V)" stroke="#53c7f0" dot={false} strokeWidth={2} />
          <Line yAxisId="electrical" type="monotone" dataKey="current" name="Current (A)" stroke="#ffb24c" dot={false} strokeWidth={2} />
          <Line yAxisId="speed" type="monotone" dataKey="rpm" name="RPM" stroke="#9b87f5" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

type Readiness = { online: boolean; enabled: boolean; connected: boolean; stale: boolean }

function Dashboard({ sessions, refresh, readiness }: { sessions: Session[]; refresh: () => void; readiness: Readiness }) {
  const complete = sessions.filter(s => s.state === 'COMPLETE').length
  const attention = sessions.filter(s => ['WARNING', 'CRITICAL'].includes(s.condition ?? '')).length
  const average = sessions.filter(s => s.health_score != null)
  const health = average.length ? Math.round(average.reduce((sum, s) => sum + (s.health_score ?? 0), 0) / average.length) : 0
  return <>
    <header><div><p className="eyebrow">SYSTEM OVERVIEW</p><h1>Diagnostic command center</h1><p>Monitor tests, system readiness, and device health from one workspace.</p></div><button className="secondary" onClick={refresh}>Refresh</button></header>
    <section className="metric-grid">
      <Metric label="Tests recorded" value={String(sessions.length)} />
      <Metric label="Completed" value={String(complete)} />
      <Metric label="Simulation rule score" value={String(health)} unit="%" />
      <Metric label="Need attention" value={String(attention)} />
    </section>
    <section className="split overview-split">
      <div className="panel"><div className="panel-title"><div><h2>System readiness</h2><p>Current software and connection state</p></div></div>
        <div className="readiness"><div><i className="dot ready"/><span>FastAPI service</span><strong>{readiness.online ? 'Online' : 'Unavailable'}</strong></div><div><i className="dot ready"/><span>Simulation engine</span><strong>{readiness.online ? 'Available' : 'Unknown'}</strong></div><div><i className="dot idle"/><span>STM32 receiver</span><strong>{!readiness.enabled ? 'Not configured' : !readiness.connected ? 'Disconnected' : readiness.stale ? 'No fresh telemetry' : 'Receiving · unverified'}</strong></div><div><i className="dot ready"/><span>SQLite storage</span><strong>{readiness.online ? 'Accessible' : 'Unknown'}</strong></div></div>
      </div>
      <div className="panel"><div className="panel-title"><div><h2>Recent tests</h2><p>Latest stored diagnostic sessions</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Test</th><th>Device</th><th>Scenario</th><th>Result</th><th>Health</th></tr></thead><tbody>{sessions.slice(0, 6).map(s => <tr key={s.id}><td>#{s.id}</td><td>{s.device_id}</td><td>{s.scenario.replaceAll('_', ' ')}</td><td><Status value={s.condition ?? s.state} /></td><td>{s.health_score == null ? '—' : `${s.health_score}%`}</td></tr>)}</tbody></table>{!sessions.length && <p className="empty">No tests recorded.</p>}</div>
      </div>
    </section>
  </>
}

function MotorControl() {
  const [motor, setMotor] = useState<MotorStatus | null>(null)
  const [targetPwm, setTargetPwm] = useState(0)
  const [acknowledgment, setAcknowledgment] = useState('Controller ready for commands.')
  const [accepted, setAccepted] = useState(true)
  const [busy, setBusy] = useState(false)

  const refreshMotor = useCallback(async () => {
    try {
      const next = await api.motorStatus()
      setMotor(next); setBusy(next.sequence.running)
      if (next.sequence.running) setTargetPwm(next.state.pwm_percent)
    } catch { setAcknowledgment('Motor controller is unavailable.'); setAccepted(false) }
  }, [])

  useEffect(() => {
    refreshMotor()
    const timer = window.setInterval(refreshMotor, 400)
    return () => window.clearInterval(timer)
  }, [refreshMotor])

  async function send(action: string, value?: number | string) {
    const reply = await api.motorCommand(crypto.randomUUID(), action, value)
    setAccepted(reply.accepted); setAcknowledgment(reply.message)
    await refreshMotor()
    return reply.accepted
  }

  async function emergencyStop() {
    setBusy(false); setTargetPwm(0)
    await send('emergency_stop')
  }

  async function runSequence() {
    const reply = await api.startMotorSequence()
    setAccepted(reply.accepted); setAcknowledgment(reply.message); setBusy(reply.accepted)
    await refreshMotor()
  }

  const state = motor?.state
  const telemetry = motor?.telemetry
  return <>
    <header><div><p className="eyebrow">MOTOR TEST BENCH</p><h1>Motor control</h1><p>Run a permitted STM32 test or use the separately labeled simulator below.</p></div><span className="mode-chip">SEPARATE DATA SOURCES</span></header>
    <HardwareMotorControls />
    <section className="motor-layout">
      <div className="panel motor-controls">
        <div className="panel-title"><div><h2>Driver controls</h2><p>Commands are checked by backend safety interlocks before being accepted.</p></div><span className="mode-chip">SIMULATION</span></div>
        <div className="driver-state"><div><span>Driver</span><strong>{state?.enabled ? 'Enabled' : 'Disabled'}</strong></div><div><span>Direction</span><strong>{state?.direction?.toLowerCase() ?? '—'}</strong></div><div><span>Output</span><strong>{state?.pwm_percent ?? 0}%</strong></div></div>
        <div className="button-row"><button className="primary" disabled={busy || state?.enabled || state?.emergency_stop} onClick={() => send('enable')}>Enable driver</button><button className="secondary" disabled={!state?.enabled} onClick={() => { setBusy(false); setTargetPwm(0); send('disable') }}>Disable</button></div>
        <div className="control-group"><div className="control-heading"><span>Direction</span><small>Motor must be stopped before changing direction</small></div><div className="segmented"><button className={state?.direction === 'FORWARD' ? 'selected' : ''} disabled={busy} onClick={() => send('set_direction', 'FORWARD')}>Forward</button><button className={state?.direction === 'REVERSE' ? 'selected' : ''} disabled={busy} onClick={() => send('set_direction', 'REVERSE')}>Reverse</button></div></div>
        <div className="control-group"><div className="control-heading"><span>PWM speed command</span><strong>{targetPwm}%</strong></div><input className="pwm-slider" type="range" min="0" max="100" step="5" value={targetPwm} disabled={busy || !state?.enabled || state?.emergency_stop} onChange={event => setTargetPwm(Number(event.target.value))}/><div className="slider-labels"><span>Stopped</span><span>Full output</span></div><button className="secondary full" disabled={busy || !state?.enabled || state?.emergency_stop} onClick={() => send('set_pwm', targetPwm)}>Apply PWM command</button></div>
        <button className="sequence-button" disabled={state?.emergency_stop} onClick={busy ? async () => { const reply = await api.cancelMotorSequence(); setAcknowledgment(reply.message); setAccepted(true); setBusy(false); setTargetPwm(0); await refreshMotor() } : runSequence}>{busy ? `Cancel automated ramp · step ${motor?.sequence.step_index ?? 0}/${motor?.sequence.total_steps ?? 10}` : 'Run automated PWM ramp'}</button>
        <button className="estop" onClick={emergencyStop}>EMERGENCY STOP</button>
        {state?.emergency_stop && <button className="reset-estop" onClick={() => send('reset_emergency_stop')}>Reset emergency stop</button>}
      </div>
      <div className="motor-side">
        <section className="metric-grid motor-metrics"><Metric label="Output voltage" value={fmt(telemetry?.voltage, 2)} unit=" V"/><Metric label="Motor current" value={fmt(telemetry?.current, 2)} unit=" A"/><Metric label="Estimated speed" value={fmt(telemetry?.rpm, 0)} unit=" RPM"/></section>
        <div className={`panel command-ack ${accepted ? 'ack-accepted' : 'ack-rejected'}`}><div><span>{accepted ? '✓' : '!'}</span><div><h2>{accepted ? 'Command acknowledged' : 'Command rejected'}</h2><p>{acknowledgment}</p></div></div><small>Controller sequence {state?.sequence ?? 0} · {state ? new Date(state.updated_at * 1000).toLocaleTimeString() : 'waiting'}</small></div>
        <div className="panel safety-panel"><div className="panel-title"><div><h2>Active safety interlocks</h2><p>These rules will transfer to the STM32 implementation.</p></div></div><div className="safety-rule"><i className={state?.emergency_stop ? 'dot danger' : 'dot ready'}/><div><strong>Emergency stop latch</strong><span>{state?.emergency_stop ? 'Latched — output blocked' : 'Clear'}</span></div></div><div className="safety-rule"><i className="dot ready"/><div><strong>Direction-change guard</strong><span>Requires 0% PWM before reversal</span></div></div><div className="safety-rule"><i className="dot ready"/><div><strong>Enable guard</strong><span>PWM blocked while driver is disabled</span></div></div></div>
      </div>
    </section>
  </>
}

function LiveMultimeter() {
  const [reading, setReading] = useState<MeterReading | null>(null)
  const [history, setHistory] = useState<MeterReading[]>([])
  const [selected, setSelected] = useState('motor_voltage')
  const [hold, setHold] = useState(false)
  const [online, setOnline] = useState(true)

  useEffect(() => {
    let active = true
    async function sample() {
      try {
        const next = await api.meterReading()
        if (!active) return
        setOnline(true); setReading(next)
        if (!hold) setHistory(current => [...current.slice(-59), next])
      } catch { if (active) setOnline(false) }
    }
    sample()
    const timer = window.setInterval(sample, 500)
    return () => { active = false; window.clearInterval(timer) }
  }, [hold])

  const channel = reading?.channels.find(item => item.channel === selected)
  const chartData = history.map(item => ({
    time: new Date(item.timestamp * 1000).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
    value: item.channels.find(candidate => candidate.channel === selected)?.value,
  }))
  const values = chartData.map(item => item.value).filter((value): value is number => value != null)
  const minimum = values.length ? Math.min(...values) : null
  const maximum = values.length ? Math.max(...values) : null
  const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null

  return <>
    <header><div><p className="eyebrow">SIMULATED INSTRUMENTS</p><h1>Digital multimeter</h1><p>Inspect every planned sensing channel before the physical hardware arrives.</p></div><Status value={online ? hold ? 'HOLD' : 'RUNNING' : 'FAILED'} /></header>
    <section className="meter-toolbar"><label>Displayed channel<select value={selected} onChange={event => setSelected(event.target.value)}>{reading?.channels.map(item => <option value={item.channel} key={item.channel}>{item.label} — {item.sensor}</option>)}</select></label><button className={hold ? 'primary' : 'secondary'} onClick={() => setHold(current => !current)}>{hold ? 'Resume sampling' : 'Hold reading'}</button><button className="secondary" onClick={() => setHistory([])}>Clear graph</button></section>
    <section className="meter-layout">
      <div className="panel meter-display"><div className="meter-screen"><span>{channel?.label ?? 'Waiting for channel'}</span><strong>{channel ? fmt(channel.value, channel.unit === 'RPM' ? 0 : 3) : '—'}<small>{channel?.unit}</small></strong><div><i className={online ? 'dot ready' : 'dot danger'}/>{channel?.sensor ?? 'No sensor'}<em>{reading?.motor_enabled ? 'MOTOR ON' : 'MOTOR OFF'}</em></div></div><div className="meter-stats"><div><span>Minimum</span><strong>{fmt(minimum, 3)}</strong></div><div><span>Average</span><strong>{fmt(average, 3)}</strong></div><div><span>Maximum</span><strong>{fmt(maximum, 3)}</strong></div></div>
        <div className="meter-chart"><ResponsiveContainer width="100%" height={260}><LineChart data={chartData}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)"/><XAxis dataKey="time" stroke="var(--muted)" tickLine={false}/><YAxis domain={['auto', 'auto']} stroke="var(--muted)" tickLine={false}/><Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10 }}/><Line type="monotone" dataKey="value" name={`${channel?.label ?? 'Reading'} (${channel?.unit ?? ''})`} stroke="#41c5e7" dot={false} strokeWidth={2}/></LineChart></ResponsiveContainer></div>
      </div>
      <div className="panel channel-panel"><div className="panel-title"><div><h2>Available channels</h2><p>Live simulated values mapped to the Fritzing hardware.</p></div></div>{reading?.channels.map(item => <button className={selected === item.channel ? 'channel selected' : 'channel'} onClick={() => setSelected(item.channel)} key={item.channel}><div><span>{item.label}</span><small>{item.sensor}</small></div><strong>{fmt(item.value, 2)} <small>{item.unit}</small></strong></button>)}</div>
    </section>
    <section className="sensor-map"><div><strong>INA219 #1</strong><span>Motor voltage, current, and power</span></div><div><strong>INA219 #2</strong><span>Circuit-under-test voltage and current</span></div><div><strong>Voltage probe</strong><span>External DC test point through divider</span></div></section>
  </>
}

function CircuitDiagnostics({ hardware, setHardware }: { hardware: boolean; setHardware: (value: boolean) => void }) {
  const [profiles, setProfiles] = useState<CircuitProfile[]>([])
  const [scenarios, setScenarios] = useState<string[]>([])
  const [profileId, setProfileId] = useState('')
  const [mode, setMode] = useState<'LEARN' | 'DIAGNOSE'>('DIAGNOSE')
  const [scenario, setScenario] = useState('healthy')
  const [report, setReport] = useState<CircuitReport | null>(null)
  const [captured, setCaptured] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => { api.circuitProfiles().then(data => { setProfiles(data.profiles); setScenarios(data.scenarios); setProfileId(data.profiles[0]?.profile_id ?? '') }).catch(() => setError('Unable to load circuit profiles.')) }, [])
  const profile = profiles.find(item => item.profile_id === profileId)
  const current = report?.steps[captured]
  const finished = !!report && captured >= report.steps.length

  async function start() {
    try {
      setError('')
      const next = await api.runCircuit(profileId, mode, mode === 'LEARN' ? 'healthy' : scenario)
      setReport(next); setCaptured(0)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to start circuit test.') }
  }

  const sourcePicker = <div className="source-picker" role="group" aria-label="Circuit data source"><button className={hardware ? 'secondary' : 'primary'} onClick={() => setHardware(false)}>Simulation</button><button className={hardware ? 'primary' : 'secondary'} onClick={() => setHardware(true)}>Physical circuit capture</button></div>
  if (hardware) return <>{sourcePicker}<PhysicalCircuit/></>

  return <>
    {sourcePicker}
    <header><div><p className="eyebrow">GUIDED TROUBLESHOOTING</p><h1>Circuit diagnostics</h1><p>Follow a safe probe sequence and turn measurements into a clear fault diagnosis.</p></div><Status value={finished ? report?.condition ?? null : report ? 'RUNNING' : 'READY'} /></header>
    <section className="circuit-setup panel"><label>Circuit profile<select value={profileId} onChange={event => { setProfileId(event.target.value); setReport(null) }}>{profiles.map(item => <option value={item.profile_id} key={item.profile_id}>{item.name}</option>)}</select></label><label>Workflow mode<select value={mode} onChange={event => { const next = event.target.value as 'LEARN' | 'DIAGNOSE'; setMode(next); if (next === 'LEARN') setScenario('healthy'); setReport(null) }}><option value="DIAGNOSE">Diagnose a circuit</option><option value="LEARN">Learn healthy behavior</option></select></label><label>Simulation fault<select value={scenario} disabled={mode === 'LEARN'} onChange={event => { setScenario(event.target.value); setReport(null) }}>{scenarios.map(item => <option value={item} key={item}>{item.replaceAll('_', ' ')}</option>)}</select></label><button className="primary" onClick={start} disabled={!profileId}>Start guided test</button></section>
    {error && <p className="circuit-error">{error}</p>}
    {!report && <section className="panel circuit-intro"><div><span>1</span><h2>Select a workflow</h2><p>Use Learn Mode on a known-good circuit or Diagnose Mode to locate a simulated fault.</p></div><div><span>2</span><h2>Follow probe guidance</h2><p>The app identifies the test point, sensor, and safe action for each measurement.</p></div><div><span>3</span><h2>Review the diagnosis</h2><p>Readings are compared with specifications or the learned healthy circuit.</p></div></section>}
    {report && <section className="guided-layout">
      <div className="panel probe-guide">
        {!finished && current ? <><div className="step-count">STEP {captured + 1} OF {report.steps.length}</div><h2>{current.point_id} · {current.label}</h2><p className="probe-instruction">{current.instruction}</p><div className="probe-diagram"><div className="probe-icon">+</div><span>{current.sensor}</span><div className="probe-line"/><div className="test-point">{current.point_id}</div></div><div className="safety-note">Confirm the probe position before capturing the reading.</div><button className="primary full" onClick={async () => { try { if (!report.run_id) throw new Error('Backend capture session missing'); const result = await api.captureSimulatedCircuit(report.run_id, captured); setReport(result); setCaptured(result.captured_count ?? 0) } catch (caught) { setError(String(caught)) } }}>Capture simulated reading</button></> : <div className={`circuit-conclusion conclusion-${report.condition.toLowerCase()}`}><span>{report.condition === 'FAULT' ? '!' : '✓'}</span><h2>{report.condition === 'LEARNED' ? 'Baseline learned' : report.condition === 'HEALTHY' ? 'Circuit passed' : 'Fault located'}</h2><p>{report.conclusion}</p>{report.uses_learned_baseline && <small>Compared against the learned healthy baseline.</small>}<button className="secondary" onClick={() => { setReport(null); setCaptured(0) }}>Start another test</button></div>}
      </div>
      <div className="panel test-results"><div className="panel-title"><div><h2>Test-point results</h2><p>{profile?.description}</p></div></div>{report.steps.map((step, index) => <div className={`test-point-result ${index < captured ? `result-${step.result.toLowerCase()}` : ''}`} key={step.point_id}><div className="result-index">{index < captured ? step.result === 'FAIL' ? '!' : '✓' : index + 1}</div><div><strong>{step.point_id} · {step.label}</strong><span>{index < captured ? step.explanation : 'Waiting for measurement'}</span></div><div className="result-reading">{index < captured ? <><strong>{fmt(step.measured, 3)} {step.unit}</strong><small>Expected {fmt(step.expected_min, 2)}–{fmt(step.expected_max, 2)}</small></> : <strong>—</strong>}</div></div>)}</div>
    </section>}
  </>
}

function RunTest({ profiles, scenarios, onComplete, hardware, setHardware }: { profiles: Profile[]; scenarios: string[]; onComplete: () => void; hardware: boolean; setHardware: (value: boolean) => void }) {
  const [device, setDevice] = useState(profiles[0]?.device_id ?? '')
  const [scenario, setScenario] = useState('healthy')
  const [registry, setRegistry] = useState<RegisteredTest[]>([])
  const [hardwareRegistry, setHardwareRegistry] = useState<RegisteredTest[]>([])
  const [automated, setAutomated] = useState<AutomatedRun | null>(null)
  const [samples, setSamples] = useState(30)
  const [measurements, setMeasurements] = useState<Measurement[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [status, setStatus] = useState('Ready')
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const socketRef = useRef<WebSocket | null>(null)
  const latest = measurements.at(-1)
  const scripted = scenario.startsWith('auto:') || scenario.startsWith('hardware:')

  useEffect(() => {
    if (!device && profiles.length) setDevice(profiles[0].device_id)
  }, [device, profiles])
  useEffect(() => () => socketRef.current?.close(), [])

  useEffect(() => {
    api.testRegistry('simulation').then(setRegistry).catch(() => setStatus('Test registry unavailable'))
    api.testRegistry('hardware').then(setHardwareRegistry).catch(() => setStatus('Hardware registry unavailable'))
  }, [])

  async function start() {
    if (scenario.startsWith('auto:') || scenario.startsWith('hardware:')) {
      const physical = scenario.startsWith('hardware:')
      let supervisedConfirmed = false
      if (physical) {
        try {
          const configuration = await api.hardwareMotorStatus()
          const supervised = configuration.operating_mode === 'SUPERVISED_TEST'
          if (!window.confirm(supervised ? 'SUPERVISED TEST: confirm you will remain present with an accessible physical emergency power cutoff. Power feedback may not be installed. Run the approved test?' : 'Arm and run the selected physical motor test with the commissioned settings?')) return
          supervisedConfirmed = supervised
        } catch (error) { setStatus(String(error)); return }
      }
      const selection = scenario.split(':')[1]
      const needsConditions = physical || ['load_response', 'friction_response', 'steady_state', 'voltage_stability', 'power_consumption'].includes(selection)
      const conditions = needsConditions ? captureRunConditions() : {}
      if (needsConditions && !conditions) return
      setRunning(true); setMeasurements([]); setReport(null); setProgress(0)
      try {
        const run = await api.startAutomated({ mode: physical ? 'hardware' : 'simulation', device_id: device,
          tests: selection === 'all' ? [] : [selection], run_all: selection === 'all', duration_ms: Math.round(samples * 100),
          operator_authorized: physical, supervised_confirmed: supervisedConfirmed, ...conditions })
        setAutomated(run)
        const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/automated/${run.id}`)
        socketRef.current = socket
        socket.onmessage = event => {
          const update: AutomatedRun = JSON.parse(event.data)
          setAutomated(update); setStatus(`${update.source} · ${update.state} · ${update.active_test ?? ''} · ${(update.elapsed_seconds ?? 0).toFixed(1)} s · PWM ${update.requested_pwm_percent ?? 0}% requested / ${update.applied_pwm_percent ?? 0}% applied ${update.reason ?? ''}`)
          setProgress(update.progress)
          if (update.latest_measurement) {
            const sample = update.latest_measurement
            setMeasurements(current => current.at(-1)?.timestamp === sample.timestamp ? current : [...current, sample])
          }
          if (update.ended_at) {
            setRunning(false); socket.close(); socketRef.current = null; onComplete()
            setReport({ device_id: device, condition: update.condition ?? 'INSUFFICIENT_DATA',
              health_score: update.health_score,
              findings: update.steps.flatMap(step => [
                ...(step.result?.findings ?? []).map(message => ({ code: step.test_id, severity: 'WARNING' as const, message, possible_causes: [] })),
                ...(step.result?.comparisons ?? []).map(item => ({ code: step.test_id + '_' + item.channel,
                  severity: item.observed < item.reference_range[0] || item.observed > item.reference_range[1] || item.observed_std > item.approved_max_std ? 'WARNING' as const : 'PASS' as const,
                  message: `${item.channel}: ${item.observed.toFixed(3)} against ${item.reference_range.join('–')}; difference ${item.deviation.toFixed(3)}. ${item.followup}`,
                  possible_causes: [item.possible_causes] }))
              ]) })
          }
        }
        socket.onclose = () => {
          setRunning(false)
          api.automatedRun(run.id).then(update => { setAutomated(update); setStatus(`${update.state}: ${update.reason ?? 'Stream closed; check saved results'}`) }).catch(() => setStatus('Telemetry disconnected; completion not confirmed'))
        }
        socket.onerror = () => setStatus('Telemetry disconnected; completion not confirmed')
      } catch (error) { setStatus(String(error)); setRunning(false) }
      return
    }
    setAutomated(null)
    setMeasurements([]); setReport(null); setProgress(0); setRunning(true); setStatus('Connecting')
    const socket = testSocket()
    socketRef.current = socket
    socket.onopen = () => socket.send(JSON.stringify({ device_id: device, scenario, samples, interval_ms: 100 }))
    socket.onmessage = event => {
      const message = JSON.parse(event.data)
      if (message.type === 'started') setStatus(`Running test #${message.session_id}`)
      if (message.type === 'measurement') {
        setMeasurements(current => [...current, message.measurement])
        setReport(message.report)
        setProgress(Math.round((message.measurement.sequence / samples) * 100))
      }
      if (message.type === 'completed') { setStatus(`Test #${message.session_id} complete`); setReport(message.report); setProgress(100); setRunning(false); socket.close(); socketRef.current = null; onComplete() }
      if (message.type === 'failed' || message.type === 'error') { setStatus(`${message.state ?? 'Error'}: ${message.message}`); if (message.report) setReport(message.report); setRunning(false); socket.close(); socketRef.current = null; onComplete() }
    }
    socket.onerror = () => { setStatus('Unable to connect to the diagnostic API'); setRunning(false); socketRef.current = null }
  }

  return <>
    <header><div><p className="eyebrow">{hardware ? 'COMMISSIONED HARDWARE TEST' : 'SIMULATION LAB'}</p><h1>Run motor diagnostic</h1><p>{hardware ? 'Only approved procedures can arm the STM32. No simulation fallback.' : 'Simulated tests are labeled separately from STM32 measurements.'}</p></div><Status value={running ? 'RUNNING' : report?.condition ?? 'READY'} /></header>
    <section className="control-bar">
      <label>Device<select value={device} onChange={e => setDevice(e.target.value)} disabled={running}>{profiles.map(p => <option key={p.device_id}>{p.device_id}</option>)}</select></label>
      <label>Scenario<select value={scenario} onChange={e => { setScenario(e.target.value); setHardware(e.target.value.startsWith('hardware:')) }} disabled={running}>{scenarios.map(s => <option value={s} key={s}>Simulation: {s.replaceAll('_', ' ')}</option>)}<option value="auto:all">Simulation: run all eligible tests</option>{registry.map(test => <option value={`auto:${test.id}`} key={`auto:${test.id}`} disabled={!test.available} title={test.unavailable_reason}>{test.name}{!test.available ? ` — ${test.unavailable_reason}` : ''}</option>)}<option value="hardware:all" disabled={!hardwareRegistry.some(test => test.available)}>Hardware: run all approved tests</option>{hardwareRegistry.map(test => <option value={`hardware:${test.id}`} key={`hardware:${test.id}`} disabled={!test.available} title={test.unavailable_reason}>Hardware: {test.name}{!test.available ? ` — ${test.unavailable_reason}` : ''}</option>)}</select></label>
      <label>{scripted ? 'Duration (seconds)' : 'Samples'}<input type="number" min={scripted ? 0.1 : 5} max={scripted ? 30 : 500} step={scripted ? 0.1 : 1} value={scripted ? samples / 10 : samples} onChange={e => setSamples(Number(e.target.value) * (scripted ? 10 : 1))} disabled={running}/></label>
      <button className="primary" onClick={start} disabled={running || !device}>{running ? 'Test running…' : 'Start diagnostic'}</button>
    </section>
    <div className="progress"><span style={{ width: `${progress}%` }}/></div><p className="run-status">{status} · {progress}%</p>
    {automated && <div className="control-bar"><button className="secondary" disabled={!running} onClick={() => api.stopAutomated(automated.id).catch(error => setStatus(String(error)))}>Stop Test</button><button className="danger" disabled={!running} onClick={() => api.stopAutomated(automated.id, true).catch(error => setStatus(String(error)))}>Emergency Stop</button><button className="secondary" disabled={!automated.ended_at} onClick={() => window.open(`/api/automated/runs/${automated.id}/report`, '_blank')}>Download Report</button></div>}
    <section className="metric-grid">
      <Metric label="Voltage" value={fmt(latest?.voltage, 2)} unit=" V"/><Metric label="Current" value={fmt(latest?.current, 2)} unit=" A"/><Metric label="Power" value={fmt(latest?.input_power, 1)} unit=" W"/><Metric label="Speed" value={fmt(latest?.rpm, 0)} unit=" RPM"/>
    </section>
    <section className="split chart-split"><div className="panel"><div className="panel-title"><div><h2>Live signals</h2><p>Electrical and mechanical measurements by sample</p></div></div><SignalChart data={measurements}/></div>
      <div className="panel findings"><div className="panel-title"><div><h2>Diagnostic analysis</h2><p>{report ? `${report.health_score == null ? 'No validated health score' : `${report.health_score}% health`} · ${report.condition}` : 'Waiting for measurement data'}</p></div></div>
        {report?.findings.map(f => <FindingCard finding={f} key={f.code}/>)}{!report && <p className="empty">Start a test to generate explainable findings.</p>}
      </div></section>
  </>
}

function FindingCard({ finding }: { finding: Finding }) {
  return <div className={`finding finding-${finding.severity.toLowerCase()}`}><div><strong>{finding.code.replaceAll('_', ' ')}</strong><span>{finding.severity}</span></div><p>{finding.message}</p>{finding.possible_causes?.length ? <small>Possible causes: {finding.possible_causes.join(', ')}</small> : null}</div>
}

function History({ sessions, onBaseline }: { sessions: Session[]; onBaseline: () => void }) {
  const [selectedId, setSelectedId] = useState<number | null>(sessions[0]?.id ?? null)
  const [automatedRuns, setAutomatedRuns] = useState<AutomatedRun[]>([])
  const [automatedDetail, setAutomatedDetail] = useState<AutomatedRun | null>(null)
  useEffect(() => { api.automatedRuns().then(setAutomatedRuns).catch(() => setMessage('Automated history unavailable')) }, [])
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (selectedId == null && sessions.length) setSelectedId(sessions[0].id)
  }, [selectedId, sessions])
  useEffect(() => { if (selectedId) api.session(selectedId).then(setDetail) }, [selectedId])
  async function learnBaseline() {
    if (!selectedId) return
    try {
      const baseline = await api.createBaseline(selectedId)
      setMessage(`Learned ${baseline.device_id} baseline from ${baseline.sample_count} samples.`)
      onBaseline()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to create baseline')
    }
  }
  return <><header><div><p className="eyebrow">TEST RECORDS</p><h1>Diagnostic history</h1><p>Inspect stored signals, findings, and health results.</p></div></header>
    <section className="history-layout"><div className="panel session-list">{automatedRuns.map(run => <button className={automatedDetail?.id === run.id ? 'session selected' : 'session'} onClick={() => api.automatedRun(run.id).then(setAutomatedDetail).catch(error => setMessage(String(error)))} key={run.id}><span><strong>{run.active_test ?? 'Automated sequence'}</strong><small>{run.source} · {run.id.slice(0, 8)}</small></span><Status value={run.state}/></button>)}{sessions.map(s => <button className={selectedId === s.id ? 'session selected' : 'session'} onClick={() => { setAutomatedDetail(null); setSelectedId(s.id) }} key={s.id}><span><strong>Test #{s.id}</strong><small>{s.device_id} · {s.scenario.replaceAll('_', ' ')}</small></span><Status value={s.condition ?? s.state}/></button>)}</div>
      <div className="panel detail">{automatedDetail ? <><div className="panel-title"><div><h2>Automated test · {automatedDetail.id.slice(0,8)}</h2><p>{automatedDetail.source} · {automatedDetail.device_id} · {automatedDetail.reason ?? automatedDetail.condition}</p></div><Status value={automatedDetail.state}/></div><section className="metric-grid compact"><Metric label="Health" value={automatedDetail.health_score == null ? '—' : String(automatedDetail.health_score)} unit="%"/><Metric label="Source" value={automatedDetail.source}/><Metric label="State" value={automatedDetail.state}/></section><SignalChart data={(automatedDetail.samples ?? []).map((sample,index) => ({ sequence: index+1, timestamp: sample.received_at, voltage: sample.raw.measurements?.voltage?.value ?? null, current: sample.raw.measurements?.current?.value ?? null, rpm: sample.raw.measurements?.rpm?.value ?? null, temperature: sample.raw.measurements?.temperature?.value ?? null, input_power: sample.raw.measurements?.power?.value ?? null, resistance: null, vibration_rms: null }))}/>{automatedDetail.steps.map(step => <div className="finding-list" key={step.test_id}>{step.result?.findings.map((message, index) => <p key={index}>{message}</p>)}{step.result?.comparisons?.map(item => <p key={item.channel}>{item.channel}: {item.observed.toFixed(3)} · Approved range {item.reference_range.join('–')} · Difference {item.deviation.toFixed(3)} · {item.possible_causes} {item.followup}</p>)}</div>)}<p>{automatedDetail.stop_confirmed ? 'Software stop acknowledged; physical stop is not measured here.' : 'Stop confirmation unavailable.'}</p><button className="secondary" disabled={!automatedDetail.ended_at} onClick={() => window.open(`/api/automated/runs/${automatedDetail.id}/report`,'_blank')}>Download Report</button></> : detail ? <><div className="panel-title"><div><h2>Test #{detail.summary.id}</h2><p>{new Date(detail.summary.started_at).toLocaleString()} · {detail.summary.sample_count} samples</p></div><Status value={detail.summary.condition ?? detail.summary.state}/></div>
        <section className="metric-grid compact"><Metric label="Health" value={detail.summary.health_score == null ? '—' : String(detail.summary.health_score)} unit="%"/><Metric label="Scenario" value={detail.summary.scenario.replaceAll('_', ' ')}/><Metric label="State" value={detail.summary.state}/></section><SignalChart data={detail.measurements}/><div className="finding-list">{detail.findings.map(f => <FindingCard finding={f} key={f.code}/>)}</div></> : <p className="empty">Select a test.</p>}</div></section>
    {!automatedDetail && detail?.summary.state === 'COMPLETE' && <div className="history-actions"><button className="primary" onClick={learnBaseline} disabled={detail.summary.condition !== 'HEALTHY'}>Use this test as healthy baseline</button><span>{message || (detail.summary.condition !== 'HEALTHY' ? 'Only a healthy result can be learned as a baseline.' : '')}</span></div>}
  </>
}

const EMPTY_PROFILE: Profile = { device_id: '', rated_voltage: 12, rated_current: 2, rated_rpm: 2500, winding_resistance: 1.2, max_current: 3, max_temperature: 80 }

function Profiles({ profiles, baselines, refresh }: { profiles: Profile[]; baselines: Baseline[]; refresh: () => void }) {
  const [form, setForm] = useState<Profile>(EMPTY_PROFILE)
  const [message, setMessage] = useState('')
  async function submit(event: FormEvent) { event.preventDefault(); try { await api.saveProfile(form); setMessage(`Saved ${form.device_id}`); setForm(EMPTY_PROFILE); refresh() } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to save') } }
  return <><header><div><p className="eyebrow">DEVICE LIBRARY</p><h1>Motor profiles</h1><p>Define specifications used by the diagnostic engine.</p></div></header>
    <section className="split profiles"><form className="panel profile-form" onSubmit={submit}><div className="panel-title"><div><h2>Add or update profile</h2><p>All limits must be positive engineering values.</p></div></div>
      <label>Device ID<input required value={form.device_id} onChange={e => setForm({...form, device_id:e.target.value})}/></label><div className="form-grid">{([
        ['rated_voltage','Rated voltage','V'],['rated_current','Rated current','A'],['rated_rpm','Rated speed','RPM'],['winding_resistance','Winding resistance','Ω'],['max_current','Maximum current','A'],
      ] as [keyof Profile,string,string][]).map(([key,label,unit]) => <label key={key}>{label}<div className="input-unit"><input type="number" step="any" min="0.001" required value={form[key]} onChange={e => setForm({...form,[key]:Number(e.target.value)})}/><span>{unit}</span></div></label>)}</div><button className="primary" type="submit">Save profile</button>{message && <p className="form-message">{message}</p>}</form>
      <div className="panel"><div className="panel-title"><div><h2>Saved devices</h2><p>{profiles.length} configured profile{profiles.length === 1 ? '' : 's'}</p></div></div>{profiles.map(p => { const baseline = baselines.find(b => b.device_id === p.device_id); return <div className="profile-row" key={p.device_id}><div><strong>{p.device_id}</strong><small>{p.rated_voltage} V · {p.rated_current} A · {p.rated_rpm} RPM</small></div><span>{baseline ? `Baseline: ${baseline.sample_count} samples` : 'No baseline'}</span></div> })}</div></section>
  </>
}

export default function App() {
  const [page, setPage] = useState<Page>('station')
  const [advanced, setAdvanced] = useState(false)
  const [circuitHardware, setCircuitHardware] = useState(false)
  const [testHardware, setTestHardware] = useState(false)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [scenarios, setScenarios] = useState<string[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [baselines, setBaselines] = useState<Baseline[]>([])
  const [online, setOnline] = useState(false)
  const [receiver, setReceiver] = useState({ enabled: false, connected: false, stale: true })
  const refresh = useCallback(async () => {
    try { const [health, nextProfiles, nextScenarios, nextSessions, nextBaselines, nextReceiver] = await Promise.all([api.health(), api.profiles(), api.scenarios(), api.sessions(), api.baselines(), api.liveStatus()]); setReceiver(nextReceiver); setOnline(health.status === 'ok'); setProfiles(nextProfiles); setScenarios(nextScenarios); setSessions(nextSessions); setBaselines(nextBaselines) } catch { setOnline(false) }
  }, [])
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer) }, [refresh])
  const content = useMemo(() => {
    if (page === 'station') return <TestStation/>
    if (page === 'sensors') return <LiveSensors/>
    if (page === 'recordings') return <HistoricalRecordings/>
    if (page === 'control') return <MotorControl/>
    if (page === 'meter') return <LiveMultimeter/>
    if (page === 'circuit') return <CircuitDiagnostics hardware={circuitHardware} setHardware={setCircuitHardware}/>
    if (page === 'test') return <RunTest profiles={profiles} scenarios={scenarios} onComplete={refresh} hardware={testHardware} setHardware={setTestHardware}/>
    if (page === 'history') return <History sessions={sessions} onBaseline={refresh}/>
    if (page === 'profiles') return <Profiles profiles={profiles} baselines={baselines} refresh={refresh}/>
    return <Dashboard sessions={sessions} refresh={refresh} readiness={{ online, ...receiver }}/>
  }, [page, profiles, scenarios, sessions, baselines, refresh, online, receiver, circuitHardware, testHardware])
  return <div className="app"><aside><div className="brand"><div className="brand-mark">A</div><div><strong>TRACE-X</strong><span>Diagnostic station</span></div></div><nav><button className={page === 'station' ? 'active' : ''} onClick={() => setPage('station')}>Test station</button><button aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>Advanced tools {advanced ? '−' : '+'}</button>{advanced && NAV.map(item => <button className={page === item.key ? 'active' : ''} aria-current={page === item.key ? 'page' : undefined} aria-label={item.label} onClick={() => { setPage(item.key); if (item.key !== 'test') setTestHardware(false); window.scrollTo(0, 0) }} key={item.key}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="connection"><i className={online ? 'dot ready' : 'dot danger'}/><div><strong>{online ? 'API connected' : 'API offline'}</strong><span>Motor controls: separate hardware / simulation</span></div></div></aside><main><div className="source-banner" role="status"><strong>{page === 'station' ? 'TEST STATION · EXPLICIT POWER CONTROL' : page === 'control' ? 'MOTOR BENCH · HARDWARE / SIMULATION' : page === 'test' && testHardware ? 'HARDWARE TEST · COMMISSIONING REQUIRED' : page === 'circuit' && circuitHardware ? 'HARDWARE CAPTURE · UNVERIFIED' : page === 'sensors' ? 'HARDWARE MONITOR · UNVERIFIED' : page === 'recordings' ? 'RECORDED DATA' : 'SIMULATION'}</strong><span>{online ? 'Backend connected' : 'Backend unavailable'} · {page === 'station' || page === 'control' || (page === 'test' && testHardware) ? 'Physical commands require backend prechecks and authorization' : 'Simulation controls / separate hardware monitoring'}</span></div>{content}</main></div>
}
