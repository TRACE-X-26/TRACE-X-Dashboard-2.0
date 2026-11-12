# Architecture

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

## Current system

Phase 1 introduced the shared contracts and orchestration described below. The
physical serial adapter remains intentionally absent and runtime mode remains
locked to simulation.

```text
React + TypeScript (Vite, Recharts)
        │ REST / WebSocket
        ▼
FastAPI application
        ├── in-memory simulated motor controller
        ├── simulated multimeter
        ├── simulated circuit diagnostic service
        └── WebSocket motor-test loop
                 │
                 ├── SimulatedMotorSource
                 ├── MotorDiagnosticEngine
                 └── DiagnosticStore → SQLite

CLI / legacy Streamlit
        └── MotorTestRunner → same simulator, rules, and SQLite store
```

The React frontend never accesses hardware directly, which is the correct boundary. FastAPI, CLI, and Streamlit now share `MotorTestSession` for acquisition, diagnostic analysis, safety enforcement, completion, and failure handling.

## Current module responsibilities

| Module | Responsibility | Current status |
|---|---|---|
| `frontend/src` | Navigation, controls, charts, profiles, history | **SIMULATED** |
| `api/main.py` | REST API, WebSocket test streaming, application lifecycle | **SIMULATED** |
| `api/schemas.py` | Request validation | **SIMULATED** |
| `models.py` | Motor-specific domain records | **SIMULATED** |
| `sources.py` | Measurement-source abstraction and motor simulator | **SIMULATED** |
| `control.py` | In-memory simulated motor commands and interlocks | **SIMULATED** |
| `diagnostics.py` | Transparent motor diagnostic rules | **SIMULATED** |
| `workflow.py` | CLI/Streamlit motor test runner | **SIMULATED** |
| `storage.py` | Profiles, sessions, measurements, findings, motor baseline | **SIMULATED** |
| `measurements.py` | Shared source/quality/calibration measurement envelope | **SIMULATED** |
| `drivers.py` | Hardware-facing protocols and replay source | **IMPLEMENTED_UNVERIFIED** |
| `config.py` | Validated environment configuration and safe mode gate | **SIMULATED** |
| `protocol.py` | Newline-delimited measurement JSON codec only | **IMPLEMENTED_UNVERIFIED** |
| `multimeter.py` | Generated channel values | **SIMULATED** |
| `circuits.py` | Fixed circuit profile and generated faults | **SIMULATED** |
| STM32 firmware | Not present | **UNSUPPORTED** |

## Target modular boundaries

```text
Frontend
  └── authenticated API client; never serial or GPIO

Application services
  ├── TestOrchestrator
  ├── SafetyCoordinator
  ├── BaselineService
  ├── DiagnosticService
  └── ReportService

Domain
  ├── MeasurementEnvelope
  ├── DeviceProfile / CapabilitySet
  ├── TestSession / TestState
  ├── Command / Acknowledgment
  └── Finding / DiagnosticReport

Ports (interfaces)
  ├── MeasurementSource
  ├── MotorController
  ├── DeviceConnection
  ├── SessionRepository
  └── ReportRenderer

Adapters
  ├── simulation
  ├── replay
  ├── STM32 USB serial
  ├── SQLite
  └── PDF / CSV
```

This is an incremental refactor, not a replacement application. Existing simulators should implement the new interfaces first; a mock STM32 adapter should follow; the physical serial adapter comes only after protocol and safety tests.

## Shared measurement envelope

Phase 1 introduced a transport-neutral envelope shaped as follows:

```json
{
  "timestamp": "2026-10-14T14:00:00Z",
  "device_id": "MOTOR-001",
  "sensor_id": "motor-ina219",
  "measurement_type": "current",
  "value": 1.82,
  "unit": "A",
  "quality": "GOOD",
  "source": "SIMULATION",
  "calibration_version": null,
  "session_id": 42,
  "sequence": 17
}
```

Allowed source labels should initially be `SIMULATION`, `REPLAY`, and `HARDWARE`. Quality should distinguish at least `GOOD`, `STALE`, `MISSING`, `OUT_OF_RANGE`, and `UNCALIBRATED`. The UI must render these labels rather than infer them.

## Hardware communication boundary

The planned Pi connection is USB serial:

```text
FastAPI service → SerialDeviceConnection → USB CDC → STM32F401RE
STM32F401RE → PWM/DIR → Cytron MD10C → DC motor
Sensors → STM32F401RE → USB CDC → backend
```

The STM32 must be the authority for watchdogs, immediate stopping, fault latching, and invalid transition rejection. The backend may impose stricter policy but may not weaken firmware safety. Reconnection must always return to a stopped, unarmed state.

## State ownership

| State | Authoritative owner |
|---|---|
| Physical PWM, direction, faults, watchdog | STM32 firmware |
| Hardware connection and command correlation | Backend hardware adapter |
| Test workflow and persistence | Backend test orchestrator |
| Display state and operator requests | Frontend |
| Diagnostic history and approved baselines | SQLite repository |

Automated sequences must run in a bounded backend/firmware workflow, never as a chain of browser timers.

## Data flow for a future motor test

1. Frontend requests a test; backend authenticates and checks role.
2. Orchestrator verifies device capabilities, calibration, profile, and safe state.
3. Operator explicitly authorizes the bounded test.
4. Backend sends a versioned command with ID and sequence number.
5. STM32 validates state, acknowledges, and independently applies safe output.
6. Measurements carry timestamps, quality, source, and calibration metadata.
7. Backend persists raw measurements before derived diagnostics.
8. Safety faults stop the STM32 independently and are latched in both event and session history.
9. Diagnostic rules operate only on compatible, sufficiently good data.
10. Reports identify software, firmware, calibration, source, and limitations.

## Configuration and deployment

Use validated environment configuration for application mode, database path, allowed origins, serial device, baud rate, and log level. Default mode must remain simulation. Physical control must require explicit local configuration and must never be enabled by a public deployment build.
