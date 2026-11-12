# Test Plan

## Purpose

Establish repeatable evidence for software behavior first, then mock communication, and finally explicitly authorized hardware tests. Automated tests must never energize physical hardware.

## Test levels

### 1. Unit tests

- Domain validation and measurement quality.
- Protocol framing, schema, versions, malformed input, size limits, and sequence handling.
- Safety state transitions and invalid-command rejection.
- Sensor conversions and calibration application.
- Diagnostic rules and numerical evidence.
- Baseline compatibility, versioning, approval, and overwrite protection.
- Storage transactions, migration behavior, and database failures.
- Authorization policy.

### 2. Integration tests

- FastAPI endpoints with isolated temporary SQLite databases.
- WebSocket streaming, disconnect, cancellation, and bounded buffers.
- Test orchestrator with simulated/replay sources.
- Mock STM32 request/acknowledgment correlation, heartbeat, timeout, reconnect, and faults.
- Report and CSV values compared with stored raw data.
- Public simulation build cannot access hardware endpoints.

### 3. Frontend tests

- LIVE/SIMULATED/REPLAYED/STALE/UNAVAILABLE labels.
- Disabled controls when capabilities, authentication, or readiness are absent.
- E-stop/fault/disconnect display behavior.
- Test start confirmation and operator authorization.
- Graph missing-sample and stale-data rendering.
- Navigation and responsive critical controls.

### 4. Hardware-in-the-loop tests

Manual only, using a separate checklist, explicit operator authorization, physical current limiting, and an observer. Results and instrumentation evidence must be stored separately from simulation results.

## Current baseline (October 14, 2026)

| Suite | Result |
|---|---|
| Python unit/API integration | PASS — 26 tests |
| React TypeScript production build | PASS |
| ESLint | PASS |
| Python dependency check | PASS |
| Simulation CLI healthy scenario | PASS |
| Hardware-in-the-loop | NOT RUN |

## Required repeatable scenarios

| Scenario | Expected result |
|---|---|
| Healthy motor | Complete test, healthy findings, persist measurements |
| Low supply voltage | Warning with measured voltage evidence |
| High current | Warning or critical based on profile limit |
| Stalled motor | Critical stall/overcurrent and safety stop |
| Missing sensor | Sensor fault; no plausible substituted value |
| Communication loss | Stop/disarm, latch/report fault, do not auto-resume |
| Invalid command | Reject without changing output state |
| Direction change under power | Reject until PWM is zero |
| Emergency stop | Immediate output zero; explicit reset required |
| Database failure | Stop or continue only according to documented safe policy; surface error |
| Duplicate/stale packet | Ignore/reject and log without corrupting sequence |
| Backend restart | Start disconnected/disarmed; never restore prior motor output |

## Protocol test matrix for Phase 2

- Valid hello/capabilities/status/measurement/command/ack/fault/heartbeat frames.
- Unsupported protocol version.
- Invalid JSON, missing fields, wrong types, extra-large line, partial line, and multiple lines.
- Duplicate, skipped, wrapped, and out-of-order sequence values.
- Unknown device, command, capability, and fault code.
- Acknowledgment timeout and mismatched command ID.
- Heartbeat timeout during READY, ARMED, and RUNNING.
- Disconnect and reconnect during every state.
- Verify reconnection state is stopped and unarmed.

## Motor diagnostic evidence

For each result, retain raw values, limits, source, quality, calibration version, device profile version, test configuration, software/firmware version, and rule output. A health score alone is not sufficient evidence.

## Hardware-in-the-loop procedure outline

1. Record date, operators, hardware revisions, firmware hash, wiring revision, and instrument IDs.
2. Keep motor power disconnected; verify continuity, polarity, ground, and safe output pins.
3. Verify physical e-stop and fuse/current-limit configuration.
4. Connect USB only; confirm hello, capabilities, watchdog, and stopped state.
5. Compare voltage/current sensors to reference instruments at safe static points.
6. Test communication loss with motor output physically inhibited.
7. Obtain explicit approval before connecting motor power.
8. Start at low current limit and low PWM; keep a person at the physical kill switch.
9. Verify normal stop, software stop, watchdog stop, and physical e-stop.
10. Only then run bounded diagnostic scenarios.

## CI policy

CI may run simulation, replay, database, API, frontend, and mock-serial tests. It must not discover or open real serial ports, toggle GPIO, run firmware flashing tools, or invoke a hardware-mode configuration. Hardware adapters should require an explicit opt-in environment setting and separate manual test marker.

## Exit criteria before hardware control

- Safety-state and protocol tests pass.
- Mock STM32 integration tests pass, including disconnect while running.
- Frontend cannot bypass backend capability/readiness gates.
- Physical wiring and protection evidence is reviewed.
- The operator understands and approves the manual procedure.

