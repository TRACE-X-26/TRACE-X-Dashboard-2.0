# Implementation Roadmap

**Prepared:** October 14, 2026  
**Demonstration deadline:** November 20, 2026

Motor diagnostics, safe communication, measurement integrity, persistence, and reporting are the critical path. Circuit diagnostics and machine learning remain secondary.

## Phase 0 — Audit baseline (complete)

- Repository, dependencies, source, tests, and documentation inspected.
- No hardware was activated.
- 26 backend tests, frontend build, frontend lint, dependency checks, and simulation CLI passed.
- Current status and safety limitations documented.
- Remaining prerequisite: create the first Git commit with the user's approval/workflow.

## Milestone 1 — by October 18

### Phase 1A: contracts and configuration

1. Add validated application settings; default to simulation.
2. Add measurement source/quality/calibration/session metadata.
3. Define `DeviceConnection`, `MotorController`, and capability interfaces.
4. Adapt existing simulators without changing visible behavior.
5. Consolidate duplicated WebSocket and `MotorTestRunner` orchestration.
6. Add structured logging and a persisted event model.
7. Add frontend tests for source labels and safety-control states.

**Exit:** all current tests still pass; simulated data is explicitly labeled; new modules can be injected without editing UI or diagnostic rules.

## Milestone 2 — by October 25

### Phase 2: mock protocol before physical serial (software complete)

1. Specify versioned newline-delimited messages for hello, capabilities, status, measurements, commands, acknowledgments, faults, and heartbeat.
2. Implement strict parsing, size limits, sequence validation, stale detection, timeouts, and command correlation.
3. Build a mock STM32 connection with malformed, delayed, duplicate, missing, and disconnect scenarios.
4. Implement the full safety state machine in simulation.
5. Guarantee that disconnect/restart produces a stopped, disarmed state.
6. Only after tests pass, add a disabled-by-default `pyserial` adapter.

**Exit:** bidirectional mock communication and safe loss-of-communication behavior are demonstrated; no physical output is enabled.

Software exit status: **PASS**. The physical adapter exists but cannot be
selected by runtime configuration, motor commands are hard-disabled, and the
current STM32 firmware does not implement the protocol. Physical communication
and safe-loss-of-communication behavior remain hardware-verification items.

### Firmware prerequisite

The existing STM32CubeIDE/HAL project has now been located and audited. Extend
it only after PWM/DIR pins, signal voltage compatibility, sensor inputs, relay
polarity, watchdog behavior, and kill-switch wiring are confirmed. Preserve the
working USART2 PA2/PA3 configuration, reconcile the `.ioc`/generated clock-source
discrepancy before regeneration, and ensure firmware boots with PWM off.

## Milestone 3 — by November 1

### Controlled hardware bring-up

1. Record wiring review, fuse/current-limit values, kill-switch test, and pin map.
2. Verify serial hello/status/capabilities with motor power disconnected.
3. Calibrate supported voltage/current sensors against reference instruments.
4. Record calibration versions and uncertainty.
5. Verify stop/watchdog behavior before connecting the motor.
6. Perform low-duty manual motor tests under explicit operator authorization.
7. Persist supported measurements with source and quality metadata.

**Exit:** calibrated voltage/current and manual start/stop are **VERIFIED** with evidence; unsupported RPM remains unavailable.

## Milestone 4 — by November 8

### Reliable motor demonstration

1. Implement backend-owned, safety-bounded automated test sequences.
2. Add startup current, steady-state current, voltage stability, power, and trend calculations.
3. Version and approve healthy baselines with operating conditions.
4. Show numerical evidence for deviations.
5. Save faults and final findings for completed and interrupted sessions.

**Exit:** a known-good baseline and intentionally abnormal test can be repeated and explained. Automatic testing remains disabled until safety evidence is complete.

## Milestone 5 — by November 15

### Reporting and demonstration packaging

1. Generate CSV measurement exports.
2. Generate PDF reports and verify them against SQLite values.
3. Add operator, software version, firmware version, calibration, and test configuration to sessions.
4. Add local authentication and viewer/operator authorization before any networked hardware UI.
5. Produce a simulation-only public demo build with no physical-control route.
6. Prepare replay data for backup demonstration.

**Exit:** report values match stored data; public simulation and private hardware applications are demonstrably separated.

## Milestone 6 — by November 20

1. Freeze versions and configuration.
2. Re-run software, integration, and documented hardware checks.
3. Rehearse normal, fault, disconnect, and backup replay demonstrations.
4. Record known limitations; do not add late secondary features.

## Deferred until the motor path is stable

- Editable circuit diagrams and generalized circuit profiles.
- Resistance/continuity hardware modes.
- Frequency and PWM input measurement.
- Additional equipment categories.
- Advanced analytics and machine learning.
- Predictive-maintenance claims.

## Change discipline

Each implementation phase should be a small reviewable change with: scope, files changed, tests, results, hardware status, remaining risks, and rollback notes. Never mix hardware enablement with unrelated UI work.
