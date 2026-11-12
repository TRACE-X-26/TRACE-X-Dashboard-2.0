# TRACE-X automated integration — November 6, 2026

November 6 motor-control update: [current configuration, flashing and Pi instructions](DASHBOARD_MOTOR_CONTROL.md). This supersedes the earlier motor settings; temperature is optional, RPM is provisional, and unresolved physical protections still block starts.

This is the current implementation guide. It supersedes older implementation-
stage descriptions in CURRENT_STATE, ARCHITECTURE, SERIAL_PROTOCOL and the earlier
bounded-firmware delivery. Those files retain historical context, not acceptance
of the latest physical hardware. See FULL_INTEGRATION_AUDIT.md for the initial gap
analysis and FULL_INTEGRATION_FILES.md for the complete changed-file manifest.

**Software/simulator integration is implemented. Physical output is disabled by
default. No STM32 was flashed, reset or operated, and no powered bench testing
was performed. The user previously demonstrated RPM display with older firmware;
that is not validation of this new firmware or automated physical sequence.**

## Architecture and existing workflows

React/TypeScript and Recharts retain the existing navigation, colors, panels,
chart styling, responsive CSS and legacy simulation pages. No stylesheet, graph
renderer or navigation order was redesigned. Run diagnostic's existing Scenario
selector now includes protocol-backed individual tests, Run All eligible tests,
and explicitly unavailable hardware/procedure entries. Its Samples input maps
to duration at 100 ms/sample for automated procedures (the legacy simulation
scenarios retain their original samples workflow). New stop/emergency/report
actions reuse the current control styles; the page layout is not rebuilt.

```
Existing Run diagnostic controls
  -> POST /api/automated/runs -> AutomatedTestEngine (one owner)
  -> STM32SerialConnection -> ADS v1 JSON + CRC32
  -> STM32Simulator OR real STM32 USART2/ST-LINK
  -> validated cache acquisitions, correlated ACKs and events
  -> additive SQLite run/sample/event journal + analysis
  -> /ws/automated/{id}, saved Test history and JSON report
```

The original /ws/tests diagnostic scenarios and Motor control simulator remain
available and explicitly simulated. They do not become physical commands when a
serial cable is attached. The simulated multimeter is now explicitly named as
simulation. Actual serial measurements never silently fall back to simulation.
STM32 Sensors supports the existing motor text plus optional Motor Temperature
and temperature connection/failure messages, including valid 0 C. The validated
hardware command owner publishes actual acquisitions into the same live monitor
without a competing second serial reader. Simulation never publishes there.

## Registry, sequencing and state

`diagnostic_platform/test_registry.py` registers safe idle and the documented
10/25/50/75/100% duties. Simulation can execute all six eligible procedures via
a fresh explicitly simulated fixed-duty device configuration for each step.
These are synthetic device models, not experimental recordings. In hardware,
only idle and the single approved fixed duty are eligible; the firmware does not
support a dynamic five-level sweep. Each procedure gets a fresh handshake,
initial zero-output check, fresh heartbeat and explicit arming as applicable.

Exploratory 5/15/20% CSV labels, historical test_01–test_15 identifiers, baseline
approval, high-bandwidth noise/startup tests, automated load/friction changes,
continuous ramps and unsupported probe procedures are registered unavailable
with specific reasons. A recording identifier or filename label does not supply
an executable action, safe limits or validated test protocol. The existing manual
simulation ramp remains a clearly labeled demo on Motor control.

State transitions: IDLE -> PRECHECK -> ARMED -> RUNNING -> STOPPING -> ANALYZING
-> COMPLETED. ANALYZING may transition back to PRECHECK for the next scheduled
step. FAILED, CANCELLED, EMERGENCY_STOP and DISCONNECTED terminate a sequence.
Invalid transitions and concurrent starts are rejected. A thread lock, a
canonical-path OS process lock and a SQLite ownership row protect against
conflicting browsers/backends. Run all preserves registry ordering and skips
unavailable procedures; explicitly requesting one rejects the entire request.

Run UUIDs, device-session UUIDs, motor IDs, procedure IDs, configurations,
firmware/capabilities, commissioning/calibration context, raw protected response
frames, UTC receipt times, STM32 acquisition intervals, quality/exclusion flags,
events and results are retained. Read-only queries may retry once on timeout;
start/arm commands are never automatically retried or replayed. No reconnect
resumes an interrupted run. A new run requires a new authorized precheck/arm.
A hardware browser stream disconnect requests cancellation; MCU duration and
heartbeat shutdown remain authoritative if Pi/browser cleanup fails.

## Protocol and firmware

Current firmware: `0.4.0-automated-default-disabled`, ADS envelope version 1,
USART2 PA2 TX/PA3 RX through ST-LINK, 115200 8N1.

Wire format is the existing compact JSON envelope followed by `*XXXXXXXX\n`.
XXXXXXXX is eight hexadecimal digits of standard CRC-32/IEEE (reflected
polynomial 0xEDB88320, init/final XOR 0xffffffff) over exact UTF-8 JSON bytes,
excluding the trailer/newline. CRC is integrity checking, not authentication.
The production main requires CRC; unprotected legacy framing remains available
only to explicitly configured legacy adapters/harnesses. Python rejects bad
checksums, duplicate JSON keys, nonfinite numbers and invalid sequence types.
The C parser enforces its bounded frame and owner-scoped argument lookup.

Commands: GET_DEVICE_INFO (capabilities alias), GET_CAPABILITIES, GET_STATUS,
GET_SENSOR_DATA (READ_MEASUREMENTS alias), GET_FAULTS, heartbeat, ARM_TEST,
START_TEST, SET_PWM, STOP_TEST/STOP_MOTOR, CLEAR_FAULTS and EMERGENCY_STOP.
CLEAR_FAULTS uses the same fresh-heartbeat/interlock/sensor gate as ARM_TEST; it
never starts output and cannot bypass an uncleared physical interlock. Emergency
stop requests the common shutdown and latches lockout. Responses retain
payload.reply_to; ACK acceptance must be checked explicitly. Requested/applied
PWM remain separate; applied is a software output setting, not a measured PWM
waveform. No measured-duty sensor is claimed.

Logical request before adding CRC (example input only, not approved settings):

```json
{"version":1,"type":"command","seq":10,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{"command":"START_TEST","arguments":{"pwm_percent":10,"duration_ms":1000,"direction":"FORWARD"}}}
```

Use `encode_message(request, checksum=True)` to generate the wire bytes; do not
hand-calculate a checksum over differently spaced JSON. STM32SerialConnection
with require_crc=True handles this, response correlation and queued timestamped
events. GET_STATUS.last_control_seq seeds the Pi sequence after reconnect. The
same confirmed MOTOR_START/MOTOR_STOP contract and run IDs described in
BOUNDED_STM32_MOTOR_TEST.md remain; events confirm software transitions, not
measured shaft stop or physical contact opening.

Firmware retains bounded PWM, fault/watchdog shutdown, input gates and the weak
`ADS_Motor_InterlocksReady()` hook returning false until an actual reviewed input
implementation exists. New min/max supply limits are also required. A main-loop-
fed independent IWDG resets a stalled main loop to disabled startup (nominal
~2 s; LSI tolerance/reset behavior needs bench measurement). SysTick separately
enforces communication and run deadlines. Neither is proof of protection against
welded contacts, a failed MCU or mechanical coast. PB4 remains untouched.

The existing maintained ON/OFF switch cuts power after the fuse. It has no
verified STM32 feedback described. No feedback pin or manual-reset behavior has
been fabricated. The interlock hook remains unresolved and physical commands
stay gated. Motor-driver fault feedback is likewise unavailable until a real
signal/path is documented; no invented FAULT pin is used.

## Measurement quality, health and database

Motor INA219, encoder and DS18B20 adapters reuse available source and preserve
separate acquisition intervals and calibration flags. Board source availability
is not proof of the currently flashed version. Motor INA219 address/shunt,
CPR/gearing/sign and limits are configurable. Circuit ADC scaling is excluded.
Voltage/current are a held triggered electrical pair; derive power only from
valid channels in that pair. Temperature zero is valid; a failed conversion is
null/invalid. No voltage/current/encoder channel is promoted to calibrated by
being connected. The main callback returns cached, timestamped acquisition data.

All raw acquisitions remain in SQLite, including failed, stale, repeated,
pre-start and post-stop samples. Repeated cache revisions and intervals crossing
start/stop are excluded from analysis. Same-channel acquisition timestamps are
deduplicated before statistics. Acquisition failure is TEST_INCOMPLETE or
INSUFFICIENT_DATA, not an automatic motor fault. Explicit valid current,
temperature or supply limit violations are recorded as FAULT without an invented
health percentage. Completed procedure execution can still yield INSUFFICIENT_DATA.

`health_analysis.py` reports voltage/current/RPM/temperature/power count, mean,
standard deviation, minimum and maximum. It requires five distinct valid
acquisitions per channel and an approved baseline from at least three independent
matched runs before scoring. Baselines must match motor, calibration, fixture,
PWM and direction; hardware baselines require independent evidence IDs. Approved
mean ranges and maximum standard deviations are supplied, not inferred from
unlabeled CSV data. Each channel outside its approved mean/stability envelope
subtracts 20 points from an engineering index; this is transparent, not a
probability or validated failure-rate estimate. No trained ML model exists;
PredictiveModel is an optional interface only. Startup/noise/load experiments
without validated timing/fixtures/thresholds remain unavailable.

The existing SQLite tables are preserved. Additive schema_migrations entries add
automated_runs, automated_samples, automated_events, automated_ownership and
simulated_circuit_runs. Startup recovery, under the OS owner lock, marks abandoned
active runs DISCONNECTED/TEST_INCOMPLETE; it never marks them completed or resumes
a motor. The durable raw journal is separate from the compact live snapshot.
Back up the database using SQLite backup rather than copying a live WAL file.

## Circuits and every existing action

Existing simulated guided circuit tests remain, but each Capture simulated
reading now advances an ordered backend capture record. It cannot mark complete
by clicking past a missing/reordered step. Physical Circuit 4 capture remains
read-only and operator guided with explicit test-point identities. References
and classifier remain provisional. Probe presence detection, automatic range
switching, INA219 #2 acquisition and protected ADC calibration are uncommissioned.
Resistance/continuity excitation is unsupported; no unknown circuit is energized.
/api/circuits/capabilities exposes these limitations. No motor action touches PB4.

Action mapping:

| Existing control / workflow | Backend behavior |
|---|---|
| Run diagnostic / legacy scenario | Existing /ws/tests simulation, labeled simulation |
| Run diagnostic / automated individual or Run All | POST /api/automated/runs, registry/precheck/ACK/event validation |
| Stop Test / Emergency Stop | Active run stop endpoint; stop requested is not a claim of physical stop |
| Motor control enable/PWM/direction/ramp | Existing simulation; conflicting physical-run commands rejected |
| Motor control disable / e-stop during an active run | Also cancels/latches the central owner; physical cutoff remains authoritative |
| Test history / View Results | Existing sessions plus saved automated runs/raw samples/analysis |
| Download Report | Persisted JSON report for a terminal run; unavailable while active |
| Use healthy baseline | Existing simulation-only legacy baseline workflow; not promoted to hardware baseline |
| Circuit Start/Capture | Backend simulation capture or existing tagged read-only physical capture |
| Unsupported physical procedure | Disabled registry option with explanation; backend also rejects |
| Profiles, CSV import, reference-rule examples | Existing working REST actions; no actuator commands |

## API reference

- GET /api/automated/registry?mode=simulation|hardware: available/unavailable procedures.
- POST /api/automated/runs: {mode,device_id,tests:[id],run_all,duration_ms,scenario,
  operator_authorized}. Returns 201/run UUID, 409 for unsafe/unavailable/conflicting
  starts, 422 for invalid input. Hardware authorization is fresh per run.
- GET /api/automated/runs and /api/automated/runs/{id}: summary and durable detail.
- POST /api/automated/runs/{id}/stop?emergency=true|false: bounded shutdown request.
- GET /api/automated/runs/{id}/report: JSON attachment for terminal runs only.
- WS /ws/automated/{id}: source, state, active procedure, progress, elapsed time,
  latest valid/invalid measurements, requested/applied PWM and final condition.
- GET /api/circuits/capabilities: probe support/range/calibration limitations.
- POST /api/circuits/simulated-runs/{id}/capture?index=N: ordered simulation step.
- Existing /api/live/status, /api/live/motor and /ws/live retain passive hardware
  monitoring; the hardware test owner publishes its validated acquisitions there.

## Pi 5 installation and recovery (~/Trace-X)

Use the normal desktop user. Preserve the working firmware and database before
upgrading. Node must satisfy frontend/package.json's Vite requirements (use
Node 22.12+); verify `node --version` and `npm --version`. Python, Chromium, curl,
systemd-analyze and journalctl must be available. No username is hardcoded.

```sh
cd "$HOME/Trace-X"
# Transfer/review this updated source first; it is not automatically on GitHub.
python3 -m venv .venv-pi
.venv-pi/bin/python -m pip install -r requirements-backend.txt
cd frontend
npm ci
npm run build
cd ..
bash deploy/pi/install.sh
systemd-analyze --user verify "$HOME/.config/systemd/user/trace-x.service"
systemctl --user status trace-x.service --no-pager
journalctl --user -u trace-x.service -n 60 --no-pager
curl --fail http://127.0.0.1:13115/api/health
bash deploy/pi/kiosk.sh
```

Installer generates **WorkingDirectory=/absolute/path** without literal quotes,
while ExecStart uses systemd argument quoting. Paths resolve to the actual user
home/project; spaces and percent signs are tested. Invalid control/quote/backslash
paths reject explicitly. Existing runtime.env, database and calibration files are
not overwritten. Service is validated before enable/restart; health failure
prints journal logs and fails the install. Re-running repairs the same service.
Restart=on-failure restarts only the backend; recovered tests remain incomplete.
Desktop autostart launches the existing kiosk. Boot-to-dashboard requires the
normal user desktop session/autologin or separately configured user lingering;
the installer does not silently change login policy or grant root access.

Runtime settings remain in ~/.config/trace-x/runtime.env. Defaults keep
ADS_MODE=simulation. ADS_LIVE_SERIAL_PORT opts into the old passive receiver.
ADS_AUTOMATION_HARDWARE_PROFILE, unset by default, selects an explicitly reviewed
commissioning JSON for the separate automated owner; it does not turn legacy
simulation controls physical. Configuring an owner suppresses the competing
passive reader. Do not enable two services/readers on the same serial port.

Copy deploy/pi/hardware-profile.example.json to a private configuration location
and fill only measured, reviewed settings. All flags/limits in the example fail
closed. Exact USB serial identity is discovered using pyserial list_ports, then
ADS device ID, firmware version, CRC, zero initial PWM, approved duty/duration,
actual sensor validity/calibration and operator intent are checked. A JSON flag
is not physical evidence and cannot override firmware/interlock gates.

Serial permissions: inspect `ls -l /dev/serial/by-id/` and `id -nG`; if owned by
dialout, an administrator may grant the desktop user that group, followed by a
logout/login. Never solve this by running the dashboard as root.

## Build, commissioning and troubleshooting

```sh
# Development Mac, repository root:
.venv/bin/python -m unittest discover -s tests -q
make -C ADS -j4
# ARM compiler path can be overridden with TOOLCHAIN=/path/to/bin or TOOLCHAIN= for PATH.
cd frontend
npm run build
npm run lint
```

New image: build/stm32-default-disabled/ADS.elf. Do not flash the old ADS/Debug ELF
or the separate /Users/markussanford/ADS project by mistake. Follow the manual
CubeIDE image-selection and isolated-motor flash procedure in
BOUNDED_STM32_MOTOR_TEST.md. Nothing in this task invokes flash/erase/reset.
Current protocol checks, with motor energy physically disconnected:

```sh
cd "$HOME/Trace-X"
systemctl --user stop trace-x.service
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port /dev/ttyACM0 --protocol json --crc32
# Optional read-only recorder for the new request/response firmware:
.venv-pi/bin/python -m diagnostic_platform.collector --port /dev/ttyACM0 --crc32 --test-id usb-only --directory data/experiments
```

The recorder sends heartbeat/read requests but no motor commands; stop it before
restarting the service. For the existing unflashed plain-text firmware, retain
passive verification without --protocol json/--crc32. Protocol selection must
match the installed image; a timeout is not permission to flash or bypass gates.

Supervised physical acceptance remains separate:

- Identify/read back the actually flashed image and preserve its matching source.
- Verify relay polarity, COM/NO, cold/reset/power-loss behavior and PB4 isolation.
- Resolve the maintained power switch's restart/feedback design and implement an
  ISR-safe, fail-closed interlock hook; verify physical kill independently.
- Verify INA219 #1 address/shunt/calibration, encoder x1 CPR/gearing/sign, DS18B20
  mounting and conversion failures, acquisition intervals and motor limits.
- Scope normal stop, cancel, CRC/UART faults, USB/heartbeat loss, main-loop stall,
  IWDG reset, interlock loss/recovery and no automatic restart with motor isolated.
- Only then approve fixed PWM/duration and separately authorize supervised powered
  tests. Establish repeated independently labeled matching baselines before health
  scoring. Unknown circuit excitation remains prohibited.

Troubleshooting: quoted WorkingDirectory -> rerun updated installer and inspect
unit; no serial port -> check USB identity/permissions and other readers; CRC
errors -> confirm matching firmware/framing and capture raw logs; invalid sensor
-> fix acquisition/calibration, not substitute zeros; health unavailable -> check
in-window distinct samples and approved matched baseline; interrupted test ->
review incomplete record and explicitly re-arm a new run. Do not retry actuation
or restart the old run automatically.

## Observed final validation

- Python: **147 tests passed**, 11.257 seconds, including API/WebSocket full
  simulated sequences, concurrent browser rejection, cancellation/emergency stop,
  corrupt CRC, C/Python protocol compatibility, fake-register motor shutdown,
  gated ARM-header compilation, raw/persistent quality and health abstention,
  interrupted-run recovery, sensor zero/failure handling and deployment regression.
- Frontend: TypeScript/Vite production build and ESLint passed. Existing >500 kB
  bundle-size advisory remains (main JS approximately 648 kB); no build error.
- STM32: GNU ARM GCC 14.3.rel1 F401 Cortex-M4 compile/link passed. Text 22,032,
  data 92, BSS 12,004; total size-tool result 34,128 bytes. Physical outputs remain
  disabled. No output-enabled image was produced; gated branches are syntax/
  fake-register tested only.
- Shell scripts: bash -n passed. Git whitespace check passed with cr-at-eol for
  preserved STM32Cube line endings.
- Pi service path generation is regression-tested; installer invokes actual
  systemd-analyze verification on the Pi. **No Linux systemd runtime, physical
  Pi deployment, LCD touch/visual QA, serial throughput or new hardware operation
  was exercised here.** HTTP/WebSocket tests are not physical validation.

Current ELF SHA-256: `f33b08cd839cf51d01041a320427b48c2d5216ffc75f6b2be39ce48ef699f731`.
Checksum file is beside the image. Rebuilt portable source bundle:
`deliverables/Trace-X-Pi.zip` plus SHA-256. It preserves a consistent SQLite backup
and original supplied recording archive; build/old Debug outputs and machine
ownership locks are excluded. The ELF is supplied separately, not hidden in the
Pi source bundle. No commit, GitHub push or device flash was performed.
