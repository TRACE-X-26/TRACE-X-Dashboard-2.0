import type { StationStatus } from './TestStation'
import type { AutomatedRun, RegisteredTest } from './types'
import type { Baseline, CircuitProfile, CircuitReport, CommandAcknowledgment, MeterReading, MotorStatus, Profile, Session, SessionDetail } from './types'
import type { MotorHealthReplay, Recording, RecordingMetadata, RecordingSummary } from './types'
import type { PhysicalCircuitAsset, CircuitCapture, CircuitTelemetry, CircuitDiagnostic } from './types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = Array.isArray(body.detail) ? body.detail.map((item: { msg?: string }) => item.msg ?? 'Invalid input').join('; ') : body.detail
    throw new Error(detail ?? 'Request failed')
  }
  return response.json() as Promise<T>
}

export const api = {
  stationStatus: () => request<StationStatus>('/api/station/status'),
  selectBranch: (branch: 'MOTOR' | 'CIRCUIT') => request('/api/station/select', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ branch }) }),
  circuitPower: (on: boolean, duration_ms = 30000, supervised_confirmed = false) => request('/api/station/circuit/power', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on, duration_ms, supervised_confirmed }) }),
  captureSimulatedCircuit: (id: string, index: number) => request<CircuitReport>(`/api/circuits/simulated-runs/${id}/capture?index=${index}`, { method: 'POST' }),
  testRegistry: (mode: string) => request<RegisteredTest[]>(`/api/automated/registry?mode=${mode}`),
  hardwareMotorStatus: () => request<{ operating_mode: string; power_feedback_installed: boolean; electrical_limits_enabled: boolean | null; protection_limits_verified: boolean; supply_sensing_verified: boolean; profile_ready: boolean; reason: string; asset_id: string; fixed_pwm_percent: number | null; max_duration_ms: number; active_run: AutomatedRun | null; hardware_control_enabled: boolean; hardware_control: boolean; firmware_hardware_control: boolean | null; preflight: { ready: boolean; reason: string; stale: boolean } }>('/api/motor/hardware/status'),
  hardwareMotorPreflight: () => request<{ ready: boolean; reason: string }>('/api/motor/hardware/preflight', { method: 'POST' }),
  automatedRuns: () => request<AutomatedRun[]>('/api/automated/runs'),
  startAutomated: (configuration: object) => request<AutomatedRun>('/api/automated/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(configuration),
  }),
  stopAutomated: (id: string, emergency = false) => request(`/api/automated/runs/${id}/stop?emergency=${emergency}`, { method: 'POST' }),
  automatedRun: (id: string) => request<AutomatedRun>(`/api/automated/runs/${id}`),
  circuit4ReferenceAnalysis: () => request<{ source: string; cases: { label: string; voltages: Record<string, number>; diagnostic: CircuitDiagnostic }[] }>('/api/circuits/circuit4/reference-analysis'),
  circuitTelemetry: () => request<CircuitTelemetry>('/api/live/status'),
  physicalCircuits: () => request<PhysicalCircuitAsset[]>('/api/circuits/assets'),
  savePhysicalCircuit: (asset: PhysicalCircuitAsset) => request<PhysicalCircuitAsset>('/api/circuits/assets', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(asset),
  }),
  circuitCaptureHistory: () => request<CircuitCapture[]>('/api/circuits/captures'),
  startCircuitCapture: (assetId: string, conditionsConfirmed = false) => request<CircuitCapture>('/api/circuits/captures', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_id: assetId, conditions_confirmed: conditionsConfirmed }),
  }),
  armCircuitCapture: (id: number, pointId: string) => request<CircuitCapture>(`/api/circuits/captures/${id}/arm`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ point_id: pointId, probe_confirmed: true }),
  }),
  captureCircuitPoint: (id: number) => request<CircuitCapture>(`/api/circuits/captures/${id}/capture`, { method: 'POST' }),
  liveStatus: () => request<{ enabled: boolean; connected: boolean; stale: boolean }>('/api/live/status'),
  motorHealthReplay: () => request<MotorHealthReplay>('/api/recordings/motor-health-replay'),
  recordings: () => request<RecordingSummary[]>('/api/recordings'),
  recording: (id: number) => request<Recording>(`/api/recordings/${id}`),
  importRecording: (metadata: RecordingMetadata, content: string) => request<Recording>('/api/recordings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...metadata, content }),
  }),
  health: () => request<{ status: string; mode: string; database: string; hardware_control: boolean; measurement_source: string }>('/api/health'),
  scenarios: () => request<string[]>('/api/scenarios'),
  profiles: () => request<Profile[]>('/api/profiles'),
  sessions: () => request<Session[]>('/api/sessions'),
  baselines: () => request<Baseline[]>('/api/baselines'),
  motorStatus: () => request<MotorStatus>('/api/motor/status'),
  meterReading: () => request<MeterReading>('/api/multimeter/readings'),
  circuitProfiles: () => request<{ profiles: CircuitProfile[]; scenarios: string[] }>('/api/circuits/profiles'),
  runCircuit: (profileId: string, mode: 'LEARN' | 'DIAGNOSE', scenario: string) =>
    request<CircuitReport>('/api/circuits/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId, mode, scenario }),
    }),
  motorCommand: (commandId: string, action: string, value?: number | string) =>
    request<CommandAcknowledgment>('/api/motor/commands', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command_id: commandId, action, value }),
    }),
  startMotorSequence: () => request<{ accepted: boolean; message: string }>('/api/motor/sequences/pwm-ramp', { method: 'POST' }),
  cancelMotorSequence: () => request<{ accepted: boolean; message: string }>('/api/motor/sequences/cancel', { method: 'POST' }),
  session: (id: number) => request<SessionDetail>(`/api/sessions/${id}`),
  createBaseline: (id: number) => request<Baseline>(`/api/sessions/${id}/baseline`, {
    method: 'POST',
  }),
  saveProfile: (profile: Profile) => request<Profile>('/api/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  }),
}

export function testSocket(): WebSocket {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${protocol}://${location.host}/ws/tests`)
}
