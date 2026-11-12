export type Profile = {
  device_id: string
  rated_voltage: number
  rated_current: number
  rated_rpm: number
  winding_resistance: number
  max_current: number
  max_temperature: number
}

export type RecordingMetadata = {
  filename: string
  device_id: string
  condition: string
  attached_mass_g: number | null
  fixture_description: string
  target_pwm_percent: number | null
  filename_mass_label_g?: number | null
  recorded_target_pwm_labels?: string[]
}
export type RecordingSummary = { id: number; imported_at: string; metadata: RecordingMetadata }
export type Recording = {
  id: number
  metadata: RecordingMetadata
  source: string
  analysis_status: string
  running_samples: number
  samples: { sequence: number; line: number; timestamp: string; phase: string; warnings: string[];
    direction: string | null;
    voltage: number | null; current: number | null; rpm: number | null; temperature: number | null;
    input_power: number | null; recorded_power: number | null }[]
  warnings: { line: number; code: string }[]
  limitations: string[]
  features: Record<string, { count: number; mean: number | null; min: number | null; max: number | null; std: number | null }>
  recorded_features?: Recording['features']
  timestamp_basis?: string
}

export type Measurement = {
  ina219?: Record<string, ElectricalBranch>;
  rpm_calibrated?: boolean; temperature_enabled?: boolean;
  sequence: number
  timestamp: string
  voltage: number | null
  current: number | null
  rpm: number | null
  temperature: number | null
  resistance: number | null
  vibration_rms: number | null
  input_power: number | null
}

export type Finding = {
  code: string
  severity: 'PASS' | 'WARNING' | 'CRITICAL'
  message: string
  possible_causes?: string[]
}

export type Report = {
  device_id: string
  health_score: number | null
  condition: 'HEALTHY' | 'WARNING' | 'CRITICAL' | 'INSUFFICIENT_DATA' | 'TEST_INCOMPLETE' | 'FAULT'
  findings: Finding[]
}

export type Session = {
  id: number
  device_id: string
  scenario: string
  started_at: string
  completed_at: string | null
  state: string
  condition: string | null
  health_score: number | null
  sample_count: number
}

export type SessionDetail = {
  summary: Session
  measurements: Measurement[]
  findings: Finding[]
}

export type Baseline = {
  device_id: string
  created_at: string
  sample_count: number
  voltage_mean: number
  current_mean: number
  rpm_mean: number
  temperature_mean: number
  current_std: number
  rpm_std: number
}

export type MotorState = {
  enabled: boolean
  direction: 'FORWARD' | 'REVERSE'
  pwm_percent: number
  emergency_stop: boolean
  sequence: number
  updated_at: number
}

export type MotorTelemetry = {
  voltage: number
  current: number
  rpm: number
  temperature: number
  power: number
}

export type MotorStatus = {
  state: MotorState
  telemetry: MotorTelemetry
  mode: string
  sequence: MotorSequenceStatus
}

export type MotorSequenceStatus = {
  running: boolean
  name: string | null
  step_index: number
  total_steps: number
  message: string
}

export type CommandAcknowledgment = {
  command_id: string
  accepted: boolean
  message: string
  state: MotorState
}

export type MeterChannel = {
  channel: string
  label: string
  sensor: string
  value: number
  unit: string
  status: string
}

export type MeterReading = {
  timestamp: number
  sample_id: number
  motor_enabled: boolean
  channels: MeterChannel[]
}

export type CircuitTestPoint = {
  point_id: string
  label: string
  instruction: string
  sensor: string
  unit: string
  minimum: number
  maximum: number
}

export type CircuitProfile = {
  profile_id: string
  name: string
  description: string
  test_points: CircuitTestPoint[]
}

export type CircuitStepResult = CircuitTestPoint & {
  measured: number
  expected_min: number
  expected_max: number
  result: 'PASS' | 'FAIL' | 'LEARNED'
  explanation: string
}

export type CircuitReport = {
  run_id?: string; captured_count?: number; execution_state?: string;
  profile_id: string
  mode: 'LEARN' | 'DIAGNOSE'
  scenario: string
  condition: 'HEALTHY' | 'FAULT' | 'LEARNED'
  conclusion: string
  uses_learned_baseline: boolean
  steps: CircuitStepResult[]
}

export type PhysicalCircuitPoint = {
  point_id: string; label: string; instruction: string;
  channel: 'test_point_voltage' | 'circuit_supply_voltage' | 'circuit_current' | 'circuit_power';
  minimum: number; maximum: number;
}
export type PhysicalCircuitAsset = {
  asset_id: string; name: string; supply_voltage: number; components: string; connections: string;
  test_points: PhysicalCircuitPoint[];
  diagnostic_model?: string;
  evidence_status?: string;
  reference_values?: Record<string, Record<string, number>>;
}
export type CircuitDiagnostic = {
  model_version: string; classification: string; verification: string;
  suspected_region: string | null; reason: string; limitations: string[];
  normal_deviations: { point_id: string; measured: number; normal_reference: number; difference_V: number; deviation_percent: number }[];
}
export type CircuitCapture = {
  id: number; version: number; asset: PhysicalCircuitAsset; source: string; state: string;
  started_at: string; armed_at: string | null; condition: string;
  readings: (PhysicalCircuitPoint & { measured: number; unit: string; result: string; timestamp: string; explanation: string })[];
  diagnostic?: CircuitDiagnostic;
}
export type CircuitTelemetry = {
  enabled: boolean; connected: boolean; error: string | null; warnings: string[];
  circuit_channels: { asset_id: string; point_id: string; channel: string; value: number;
    timestamp: string; age_seconds: number; quality: string }[];
}

export type RegisteredTest = { id: string; name: string; available: boolean; unavailable_reason: string; pwm: number | null }
export type AutomatedRun = {
  operating_mode?: string; power_feedback_installed?: boolean; power_feedback_state?: string;
  device_state?: string; faults?: string[];
  id: string; state: string; mode: 'simulation' | 'hardware'; source: string; progress: number;
  active_test: string | null; reason?: string; condition?: Report['condition']; health_score: number | null;
  elapsed_seconds?: number; requested_pwm_percent?: number; applied_pwm_percent?: number; device_id?: string;
  samples?: { received_at: string; quality: string[]; raw: { measurements?: Record<string, { value: number | null }> } }[];
  ended_at: string | null; latest_measurement?: Measurement; stop_confirmed: boolean;
  steps: { test_id: string; result?: { findings: string[]; comparisons?: { channel: string; observed: number; reference_range: number[];
    deviation: number; observed_std: number; approved_max_std: number; possible_causes: string; followup: string }[] } | null }[];
}

export type ElectricalBranch = {
  address: number; connected: boolean; configured: boolean; status: string; valid: boolean;
  calibrated: boolean; timestamp_ms: number | null; started_ms: number | null; sequence: number | null;
  stale?: boolean; age_seconds?: number;
  measurements: Record<string, { value: number | null; unit: string; valid: boolean; timestamp_ms: number }>;
}

export type MotorHealthReplay = {
  test_catalog: Record<string, { name: string; planned_pwm_percent: number | null; present_in_archive: boolean }>;
  runs: Record<string, { test_name: string | null; status: string; target_pwm_percent: number[];
    reasons: string[]; metrics: Record<string, { median: number; min: number; max: number; samples: number }> }>;
}
