> Superseded: use [PROTECTED_HARDWARE_INTEGRATION.md](PROTECTED_HARDWARE_INTEGRATION.md). Version 0.6.0 restores electrical protection and requires verified upstream sensing; default outputs are disabled.

> Current behavior: motor voltage/current cutoffs were removed at the operator's request. Use [BRANCH_POWER_UPDATE.md](BRANCH_POWER_UPDATE.md) for firmware 0.5.2, matching Pi profile migration, flashing and deployment. Older threshold statements below describe earlier versions.

# STM32–Pi automated motor runtime

## Findings from the existing implementation

This investigation inspected the local TRACE-X-26/Dashboard checkout. It did
not access the Pi, attach to ST-LINK, flash, reset, or energize hardware. Live
ADS JSON, both connected INA219s and profile_ready=true are operator-reported.
The source tree cannot prove which firmware image is currently on the board.

There were three independent gates/statuses:

1. `Settings.from_environment` rejected ADS_MODE=hardware unconditionally.
2. `/api/health` hardcoded hardware_control=false for the legacy simulation
   service. It did not query firmware. ADS_MODE=simulation does not prevent
   read-only monitoring or inherently describe the separate automated engine.
3. Actual firmware capabilities have their own hardware_control and
   hardware_block_reason. A loaded Pi profile cannot override them.

The new health/status responses distinguish configured permission, actual
last-observed firmware permission, and a fresh read-only preflight result.
Before probing, firmware_hardware_control is null, not an inferred false.

## Existing firmware inspection

| Function | Header / MCU assignment |
| --- | --- |
| Circuit relay | D5 / PB4, independent of motor control |
| Motor relay | D4 / PB5, HIGH active / LOW inactive |
| Direction | D7 / PA8, configured FORWARD level LOW |
| PWM | D6 / PB10, TIM2 CH3, 1 kHz |
| Encoder A / B | D12 / PA6 rising-edge interrupts; D9 / PC7 direction input |
| Motor / circuit INA219 | I2C1 PB8 SCL / PB9 SDA; 0x40 / 0x41 (HAL shifts addresses) |
| Serial | USART2/ST-LINK, 115200 baud, 8-N-1 |
| Proposed feedback | PC8, active HIGH; configured absent in supervised profile |

`main.c` registers sensor/test callbacks and processes serial commands.
`ads_protocol.c` uses ADS JSON v1, CRC32 and reply_to sequence correlation.
`ads_test.c` requires fresh heartbeat and explicit ARM, stages SET_PWM without
energizing, accepts one bounded START, rejects replayed control sequences,
and emits timestamped MOTOR_START/MOTOR_STOP events. STOP is idempotent.
`ads_motor.c` sets direction, activates only PB5, then enables TIM2 CH3. Its
shared stop disables the channel/timer, holds PWM low and requests relay LOW.

Output permission is the conjunction ADS_BOARD_ACCEPTED. It includes physical
permission, mode acceptance, verified limits, wiring, relay/reset acceptance,
cutoff/communication-stop acceptance and electrical calibration. ADS_Test_Init
also rejects invalid fixed PWM or durations over 30000 ms. Thus output_enabled
may be false even when every motor command exists in the source. Capabilities
publish disabled_reason/hardware_block_reason; the new read-only preflight
reports that exact value instead of changing gates.

Current configured operator profile: 1.5 A cutoff, 10–14 V supply, fixed 50%
PWM, maximum 30000 ms, SUPERVISED_TEST, no PC8, temperature disabled. These
verification flags record earlier operator attestations; they are not new
independent bench measurements. The generic Makefile default and supervised
example remain physically disabled. The already-existing CubeIDE Debug/Release
configurations explicitly select the operator-enabled profile; do not confuse
those with the generic disabled Makefile build. This task changes no firmware
permission, threshold, pin or shutdown code.

Normal mode requires installed/verified PC8 HIGH. Supervised mode is separate,
requires operator presence/cutoff confirmation, and does not require absent
PC8. If feedback is installed it is enforced. Invalid/stale motor measurements,
current at/above cutoff or voltage outside range block/start shutdown. Circuit
INA219 data never substitutes for motor data. Encoder scaling remains an
uncalibrated assumption of 374 A rising edges/output revolution.

The firmware maintains a 2-second heartbeat deadline and a local run deadline
of at most 30 seconds, plus existing IWDG reset handling. Fault recovery requires
explicit re-arm; reconnect/reset never automatically starts output. Software
shutdown is not proof of shaft standstill or relay contact opening.

## Runtime and API behavior

Physical Pi commands now additionally require explicit
ADS_HARDWARE_CONTROL_ENABLED=true. Default is false, including fresh installs.
No configuration is enabled automatically. A true flag requires a complete
verified hardware profile. ADS_MODE can remain simulation while the separate
automated engine serves explicitly authorized hardware runs. Explicit
ADS_MODE=hardware is now supported only with the opt-in and valid profile.
Legacy motor/manual/ST-LINK demo routes remain labelled SIMULATION; recorded
CSV/archive replay is unchanged. The global replay runtime retains its earlier
unsupported guard; existing replay APIs and finite replay source are preserved.

POST `/api/motor/hardware/preflight` acquires the existing single-owner serial
lock and selects the exact configured USB identity. It sends only
GET_CAPABILITIES, GET_STATUS, READ_MEASUREMENTS and GET_STATUS. It sends no ARM,
SET_PWM, START, STOP, fault-clear or heartbeat, including on disconnect. If
firmware permission is false it reports the exact blocker before sensor checks.
GET `/api/motor/hardware/status` and GET `/api/health` do not open the hardware.

A successful preflight snapshot expires after 15 seconds. The dashboard's
**Check hardware · no motor commands** button displays that result; Start stays
disabled unless it passes. The hardware registry is unavailable before a fresh
successful check. An explicit API run may request fresh preflight directly;
it still cannot ARM until the run-time checks pass. A cached check is not
authorization: each run repeats profile, capability and sensor checks before
ARM. Supervision/operator_authorized flags remain strict per-run booleans.

Preflight requires matching firmware/device identity, voltage/current limits,
fixed PWM, duration, mode, feedback configuration, fixed direction, command set,
CRC32 and heartbeat bound. Fresh calibrated motor values must be valid, with
same-acquisition electrical timestamps and valid acquisition sequences/intervals.
Unverified limit flags remain blockers. The engine confirms START running state,
requested/applied PWM, run ID and timestamped matching start event. Completion
requires the matching stop event and accepted stopped/zero-PWM acknowledgment.
Failures never retry START or fall back to simulation. A failed stop remains
unconfirmed and is not a successful/healthy run. Emergency stop follows the same
owner and shutdown path. Simulation fault scenarios never become physical fault
injection commands.

## Deploy the code without replacing data

These changes are local until explicitly published. The prepared
`deliverables/Trace-X-runtime-update.zip` contains source and built UI, not
databases, recordings, baseline directories, private environment files or local
CubeIDE settings. Do not use a data-bearing full-install bundle to overwrite
an existing Pi installation. Copy this update ZIP to `/home/amirzoom8/` first.

With motor power disconnected, run on the Pi:

```sh
systemctl --user stop trace-x.service
unzip -o "$HOME/Trace-X-runtime-update.zip" -d "$HOME"
cd /home/amirzoom8/Trace-X
bash deploy/pi/install.sh
systemctl --user stop trace-x.service
.venv-pi/bin/python -m serial.tools.list_ports -v
```

The installer preserves an existing runtime.env. Preserve the existing
`~/.config/trace-x/motor-hardware.json`; do not copy over it with a template.
Verify its real USB serial identity, approvals and limits against the actual
board. The earlier observed ST-LINK serial was 066AFF505487525067194658;
confirm what list_ports reports on this Pi rather than guessing.

```sh
.venv-pi/bin/python -c 'from pathlib import Path; from diagnostic_platform.automated_engine import load_hardware_profile; p=load_hardware_profile(Path.home()/".config/trace-x/motor-hardware.json"); print(p["operating_mode"], p["limits"])'
nano "$HOME/.config/trace-x/runtime.env"
```

For the initial read-only inspection, manually set these entries once each:

```dotenv
ADS_MODE=simulation
ADS_HARDWARE_CONTROL_ENABLED=false
ADS_AUTOMATION_HARDWARE_PROFILE=/home/amirzoom8/.config/trace-x/motor-hardware.json
ADS_LIVE_PROTOCOL=ads_json
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0
ADS_SERIAL_BAUD=115200
```

```sh
systemctl --user restart trace-x.service
curl -s http://127.0.0.1:13115/api/motor/hardware/status
curl -s -X POST http://127.0.0.1:13115/api/motor/hardware/preflight
journalctl --user -u trace-x.service -n 60 --no-pager
```

If a sensor-monitor acquisition owns the port, retry the preflight while idle.
With permission false, ready remains false even if firmware reports permission
true. With firmware permission false, inspect capabilities.hardware_block_reason
and the selected build; changing ADS_MODE will not fix that firmware gate.

Only after independently reviewing commissioning and actual firmware should
the operator manually set ADS_HARDWARE_CONTROL_ENABLED=true, restart, and repeat
Check hardware. Keep ADS_MODE=simulation if retaining the existing runtime UI.
No automatic physical test is part of deployment. For a later authorized run,
select hardware mode, confirm supervision, use the single approved duty and a
short bounded duration, explicitly Start, and verify Stop before longer tests.

The motor INA219 must report in-range supply voltage with the relay inactive.
If it is downstream of the relay and reads zero, the current topology/precheck
is incompatible; this integration does not energize a relay to bypass precheck.

## Firmware build/flash instructions

No firmware change is required merely to use this adapter. Query the actual
firmware first. Do not flash based only on a source-file name or successful
telemetry. The safe default build is:

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
make -C ADS -j4
```

It produces `build/stm32-default-disabled/ADS.elf`. To review the previously
operator-approved enabled build without changing its flags:

```sh
make -C ADS OUT=../build/stm32-supervised-enabled BENCH_PROFILE=bench/supervised.operator.h -j4
```

For operator-controlled flashing, disconnect motor power, import ADS/.project
in CubeIDE, refresh from disk and select the exact intended ELF in the debug
configuration or CubeProgrammer. Download/verify, then inspect capabilities
while motor energy is isolated. Flashing/reset was not executed by this task.
Never mark an unresolved physical gate verified solely to make a start pass.

## Remaining physical/diagnostic requirements

- Confirm actual flashed build/capabilities, motor power path and motor INA219
  location, electrical accuracy, relay reset/contact behavior, physical cutoff,
  communication-loss stop latency and runtime fault stops on the actual setup.
- Confirm the 1.5 A and 10–14 V settings are accepted protections for this motor
  and wiring. Historical one-second logs do not independently validate them.
- Confirm encoder counts/gearing/sign for calibrated RPM; temperature stays off.
- Health scoring still requires approved matched healthy baselines. The merged
  upstream motor-data update retires temperature from motor assessment and adds
  separately approved guided procedures and baseline review. Those features are
  preserved; no baseline was generated or retrained during this runtime update,
  and no validated hardware health percentage is claimed.
- Fit/touch performance on the physical LCD remains a bench check. Existing
  styles, navigation, simulation and recording/replay routes are preserved.

## Files changed

- diagnostic_platform/hardware_runtime.py (new): default-off adapter, exact USB
  identity, strict firmware/sensor contract checks and expiring preflight status.
- diagnostic_platform/config.py: explicit hardware opt-in/profile configuration.
- diagnostic_platform/automated_engine.py: shared preflight/contract integration,
  runtime permission, stronger start/stop confirmation and registry gating.
- diagnostic_platform/stm32.py: adapter permission documentation only.
- diagnostic_platform/device_simulator.py: explicit command/direction/watchdog
  capabilities for protocol-backed simulations.
- api/main.py: status separation and read-only preflight endpoint.
- frontend/src/HardwareMotorControls.tsx and api.ts: existing panel preflight
  button/status and gated Start; layout/CSS unchanged.
- .env.example and deploy/pi/configure.py: default-off permission setting.
- deploy/pi/build_bundle.py: source-only upgrade option that excludes evidence.
- tests/test_hardware_runtime.py (new), test_supervised_mode.py and
  test_deployment.py: synthetic transports, opt-in, fault and preservation checks.
- README.md and this guide: current configuration and deployment instructions.

Pre-existing local CubeIDE preferences, launch state and main.h comment edits
were left untouched. Subsequent GitHub publication merges the existing upstream
motor-data/temperature-retirement work without replacing its data or approvals.

## Verification results

- After merging the existing upstream motor-data update,
  `.venv/bin/python -m unittest discover -s tests -q`: **201 passed** (24.151 s).
  Includes C controller/protocol tests with simulated MCU ticks through the
  full 30000 ms bound, duplicate requests, heartbeat lockout, simulated GPIO,
  successful supervised transport run, preflight with no control/heartbeat
  writes, request correlation failure with no START retry, rejected starts,
  stale samples, exact overcurrent/voltage trips, emergency stop and stop failure.
- TypeScript/Vite production build: passed. ESLint: passed. Existing bundle-size
  advisory remains (660.11 kB JavaScript, 195.77 kB gzip).
- `make -C ADS -j4`: passed, output-disabled NUCLEO-F401RE target. ARM GCC
  14.3.rel1, text 29652 / data 92 / BSS 19532 bytes.
- Source-only package preservation test: passed; no database, baseline,
  recording or private environment entry in the update, originals unchanged.
- Git whitespace check: passed (existing CRLF firmware files accounted for).
- Actual Pi deployment, flashed firmware identity, sensor calibration, relay
  operation, shutdown timing, physical motor run and LCD touch: not tested here.
