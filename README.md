Current wiring-compatible implementation: [downstream sensor integration](docs/DOWNSTREAM_SENSOR_INTEGRATION.md), firmware 0.7.0. Start includes a bounded relay-on check at zero PWM before motor rotation is authorized.

Current protected hardware integration: [deployment, flashing and outstanding bench checks](docs/PROTECTED_HARDWARE_INTEGRATION.md). Default outputs disabled; 10–14 V and 1.5 A protection restored.

Current motor/circuit station and deployment: [branch-power update](docs/BRANCH_POWER_UPDATE.md). Firmware 0.5.2 treats voltage/current as telemetry, with no numeric motor cutoffs.

# Software-Defined Diagnostic Platform

Current STM32–Pi runtime: [hardware permission, read-only preflight, status meanings and data-preserving deployment](docs/STM32_PI_AUTOMATED_RUNTIME.md). Physical Pi commands default off via ADS_HARDWARE_CONTROL_ENABLED=false. ADS_MODE=simulation can retain the existing demos while the separately authorized automated engine is used; actual firmware capability and live protections must pass before ARM.

Current motor-data integration, temperature removal, supported procedures and Pi update steps are documented in [the integration guide](docs/MOTOR_DATA_INTEGRATION.md) and [completion report](docs/COMPLETION_REPORT.md).

November 11 current build: [supervised motor-enabled firmware and matching Pi setup](docs/SUPERVISED_OPERATOR_BUILD.md). CubeIDE Debug/Release explicitly select the operator-confirmed profile (50% PWM, up to 30 seconds, 1.5 A cutoff, 10–14 V). The motor boots stopped; live checks and per-run authorization remain required. Hardware acceptance is operator-reported, not independently verified by the coding agent. The generic Makefile default and supervised example remain output-disabled. Earlier milestone and disabled-output descriptions below are historical.

November 9 operating-mode update: [normal PC8 feedback and explicit supervised testing](docs/SUPERVISED_MOTOR_TESTING.md), firmware 0.5.0-supervised-motor. Earlier hashes and mode requirements below are historical.

Latest sensor update: [dual INA219 0x40/0x41 integration and verification](docs/DUAL_INA219_INTEGRATION.md), firmware 0.4.2-dual-ina219. Earlier firmware hashes and sizes below are historical.

November 6 motor-control update: [current configuration, flashing and Pi instructions](docs/DASHBOARD_MOTOR_CONTROL.md). This supersedes the earlier motor settings; temperature is optional, RPM is provisional, and unresolved physical protections still block starts.

The current [automated integration guide](docs/FULL_AUTOMATED_INTEGRATION.md)
covers protocol-backed simulated sequences, saved results, CRC32 firmware and
the Pi installer fix. Physical output remains disabled until commissioning;
existing simulation controls and dashboard styling are preserved.

See the [live integration and Pi launch guide](docs/LIVE_INTEGRATION.md) for passive and ADS v1 polling, archive replay, and remaining bench checks.

The Pi receiver now reads the STM32's existing plain-text motor output without firmware changes. See [plain-text motor connection and exact Pi launch commands](docs/STM32_PLAIN_TEXT_MOTOR.md). The default connection verifier listens passively; use `--protocol json` only for the existing JSON request/response firmware.

Circuit 4 (LM324 comparator) now has a physical-capture workflow and provisional multi-point rules. See [Circuit 4 setup, references and remaining STM32 integration](docs/CIRCUIT_4_CAPTURE.md). The supplied multimeter evidence is separate from live, end-to-end-verified acquisition.

For the self-contained Pi 5 / 1024×600 touchscreen presentation installation, use [the Pi install and acceptance guide](deploy/pi/README.md). The production backend can serve the built React app locally; Vite and the Mac are not needed during the presentation.

For a dashboard on a Mac with STM32 USB acquisition on a Raspberry Pi, see [Mac/Pi live monitoring setup](docs/MAC_PI_LIVE_SETUP.md). Passive monitoring is opt-in; physical motor control and calibrated live health assessment remain disabled/unverified.

Historical CSV import is available under **CSV recordings** in the existing dashboard. See [Trace-X Phase 2 operation and connection verification](docs/TRACE_X_PHASE_2.md). Experiment recordings are not included in this checkout; offline import does not activate hardware or enable physical motor commands.

Private recordings, local databases, the detailed recording audit and derived data inventory are excluded from GitHub. A fresh clone starts without those experiment records; import your own approved archive using `python -m diagnostic_platform.import_history`. Local experiment data remains intact.

This repository contains the Raspberry Pi software for a modular electrical and
electromechanical diagnostic platform. The first supported device is a DC motor.

The current milestone runs without activating hardware. It generates realistic
simulated measurements, calculates derived values, applies multi-sensor
diagnostic rules, and provides the same status/measurement/command interface as
the disabled physical STM32 serial adapter.

## Run it

Python 3.11 or newer is recommended. Install the backend dependencies before
running the API or physical serial adapter.

```bash
python3 -m diagnostic_platform --scenario healthy --samples 5
python3 -m diagnostic_platform --scenario overloaded --samples 5
python3 -m diagnostic_platform --scenario stalled --samples 3
python3 -m diagnostic_platform --scenario communication_loss --samples 6
python3 -m unittest discover -s tests
```

## React + FastAPI application

The primary application uses a React/TypeScript frontend and FastAPI backend.

Backend terminal:

```bash
source .venv/bin/activate
python3 -m pip install -r requirements-backend.txt
python3 -m uvicorn api.main:app --reload --port 13115
```

Frontend terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. FastAPI also exposes interactive API documentation
at `http://localhost:13115/docs`.

Runtime configuration is read from environment variables. Copy `.env.example`
as a reference; simulation remains the safe default. Hardware and replay modes
are intentionally rejected until their runtime adapters are configured and
verified.

## STM32 USB serial boundary

The Raspberry Pi backend now contains a modular STM32 connection and a matching
simulation adapter. The physical transport is configured for the settings found
in the generated firmware: `/dev/ttyACM0`, 115200 baud, 8 data bits, no parity,
1 stop bit, and no flow control. The proposed application protocol uses one
versioned JSON message per line and supports status, capabilities, measurements,
commands, acknowledgments, device errors, and heartbeats.

For a communication-only Raspberry Pi test, connect the Nucleo through its
ST-LINK USB port and run:

```bash
source .venv/bin/activate
python3 -m diagnostic_platform.verify_stm32
```

The tester prefers a stable `/dev/serial/by-id/` path and falls back to
`/dev/ttyACM*`. By default it passively detects complete plain-text telemetry
or unsolicited ADS JSON without sending commands. For JSON request/response
firmware, explicitly add `--protocol json` to request status, capabilities,
faults and heartbeat. Motor commands remain disabled. An explicit port may
be supplied with `--port /dev/ttyACM0`. Stop the live backend/other serial readers
before running the verifier, then restart the backend afterward.

The existing STM32CubeIDE project now implements ADS v1 framed JSON status,
capabilities, faults, heartbeat and measurement responses. Missing sensors are
reported invalid with null values; the physical acquisition routines are still
absent. Motor commands remain disabled. The motor stop path disables TIM2 CH3,
clears PWM and gates PB5 relay drive on verified polarity, power-path and
safe-output configuration. A STM32-local 2-second communication watchdog latches
shutdown; communication recovery cannot restart the motor.

See the [current integration status](docs/STM32_INTEGRATION_STATUS.md) and
[manual relay bench procedure](docs/MOTOR_RELAY_BENCH_TEST.md). No firmware was
flashed or motor energized during these changes. Older audit/review documents
record earlier project phases and may describe superseded firmware behavior.

See [the firmware audit](docs/STM32_FIRMWARE_AUDIT.md), [serial protocol](docs/SERIAL_PROTOCOL.md),
[firmware integration plan](docs/STM32_INTEGRATION_PLAN.md),
[hardware verification plan](docs/HARDWARE_VERIFICATION.md), and [Phase 2 review guide](docs/PHASE_2_REVIEW.md).

The existing STM32CubeIDE project is stored in `ADS/`. Its current incremental
firmware includes safe protocol parsing, measurement responses and shutdown
logic. Host tests and ARM-target syntax checks cover the latest safety additions;
a complete target build and physical acceptance still require verification. Generated build output and the local `TraceX.app` bundle are excluded
from Git; the CubeIDE project metadata, source, HAL/CMSIS dependencies, startup
code, linker scripts, and `.ioc` remain available for normal MacBook use.

The backend provides REST endpoints for profiles and history plus a WebSocket
endpoint for live diagnostic tests. The frontend includes the system dashboard,
real-time graphs, explainable findings, test history, and profile management.

### Motor control simulator

The **Motor control** screen provides enable/disable control, forward/reverse
selection, PWM speed commands, an automated ramp sequence, live simulated motor
feedback, and a latched emergency stop. Commands travel through FastAPI and
receive explicit accepted/rejected acknowledgments. Backend safety interlocks
block PWM while disabled, block direction changes while the motor is turning,
and block all output until a latched emergency stop is reset. This API boundary
is designed to remain stable when the simulator is replaced by the STM32 serial
transport.

The automated PWM ramp is owned by the backend rather than browser timers. It
is bounded to ten steps and always disables simulated motor output when it
completes or is cancelled. Motor commands and sequence actions are recorded in
the SQLite system-event log.

### Live multimeter

The **Live multimeter** screen samples all planned sensing paths twice per
second, provides hold and clear controls, plots the selected signal, and tracks
minimum, average, and maximum values. Its channels map directly to motor INA219,
circuit INA219, external voltage-divider probe, and DS18B20 temperature sensor
inputs. Values are simulated now; the frontend contract can remain unchanged
when real sensor readings arrive from the STM32.

### Guided circuit diagnostics

The **Circuit diagnostics** workspace implements a test-point workflow for the
protected 12 V load circuit. Learn Mode captures known-healthy behavior;
Diagnose Mode guides the operator through supply, fuse, current, and resistance
checks and compares each reading with specification or learned limits. Built-in
simulation faults include a blown fuse, open load, shorted load, and supply
voltage drop, each producing an explainable final conclusion.

### Adaptive baseline workflow

1. Run a test using a known-healthy motor.
2. Open **Test history** and select the completed test.
3. Choose **Use this test as healthy baseline**.
4. Future tests for that device are compared with its learned current and RPM
   behavior in addition to the rated specification limits.

The first two samples are treated as the motor startup window. After that
window, a critical diagnostic finding triggers a software safety stop and the
session is saved with the `SAFETY_TRIP` state.

## Legacy Streamlit prototype

Create a virtual environment, install the UI dependencies, and launch the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

The prototype includes a system dashboard, live simulated motor tests, scenario fault
injection, diagnostic results, SQLite-backed test history, charts, and editable
device profiles.

Available scenarios are `healthy`, `overloaded`, `undervoltage`, `overheating`,
`stalled`, `sensor_failure`, and `communication_loss`. Each completed run is
stored in `diagnostics.db` unless `--database` specifies another path.

## Architecture

```text
MeasurementSource (stateful simulator now, STM32 serial later)
        -> MotorMeasurement
        -> MotorDiagnosticEngine + MotorProfile
        -> MotorTestRunner state machine
        -> DiagnosticReport + SQLite history
        -> CLI now, GUI/reports later
```

## Recommended next milestones

1. Review the Phase 2 simulator and communication tests.
2. Confirm MD10C and sensor pin assignments plus 3.3 V signal compatibility.
3. Connect the missing physical sensor acquisition routines to ADS v1.
4. Verify USB communication with motor power disconnected.
5. Complete electrical safety, calibration, stop, and watchdog tests before any
   physical motor command is enabled.

## GitHub development branch

The integration branch is `trace-x-integration-2026-10-30` in
[TRACE-X-26/Dashboard](https://github.com/TRACE-X-26/Dashboard).
See [publishing and retrieval notes](docs/GITHUB_PUBLICATION.md) for the exact
clone command and files intentionally kept local.

For the November 6 default-disabled STM32 bounded-test firmware, build results,
manual flash steps and remaining Pi runner work, see
[bounded motor-test delivery](docs/BOUNDED_STM32_MOTOR_TEST.md). This is not
an enabled dashboard motor-control release.
