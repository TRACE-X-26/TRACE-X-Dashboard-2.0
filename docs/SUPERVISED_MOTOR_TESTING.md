# Normal and supervised motor testing — November 9, 2026

**Current enabled operator build:** [Supervised motor-enabled build](SUPERVISED_OPERATOR_BUILD.md)
records the subsequently operator-confirmed checks, enabled profile, exact ELF
and CubeIDE selection. The disabled-image instructions below are historical.

**November 11 update:** [Motor protection configuration](MOTOR_PROTECTION_LIMITS.md)
supersedes the historical cutoff/verification settings and artifact hashes below.
The current setting is 1.5 A and 11–13 V, marked operator-verified following
explicit operator confirmation. Other acceptance gates and output disable remain.
The remainder records the November 9 implementation and verification snapshot.

Firmware identity: `0.5.0-supervised-motor`. This supersedes the operating-mode
and commissioning instructions in the earlier motor guides. No firmware was
flashed and no physical run or protection setting was verified by this task.

## What changed

NORMAL mode requires installed, wiring-verified PC8 active-HIGH feedback.
ADS_Motor_InterlocksReady now reads that input; absent/unverified feedback returns
not ready. It is not an unconditional true function. A LOW input during a run
latches shutdown; HIGH recovery never restarts output. PC8 is configured as an
input with pull-down only when installation AND wiring-verification flags are
set. With default flags it is neither configured nor read.

SUPERVISED_TEST is an explicitly configured, separately approved mode. It can
operate without an uninstalled PC8 input, requires a physical emergency power
cutoff and an operator who remains present, and requires fresh per-test operator
confirmation. There is no automatic fallback from NORMAL. If feedback is installed
in supervised mode, it must be verified and is still honored; an installed LOW
input is not ignored. Software supervision does not prove operator presence or
physical power removal. Without feedback the software cannot guarantee detection
of manual switch operation or prevent a power restoration from causing motion
before a stop takes effect. After using the physical cutoff, keep it off, cancel
the run, confirm stopped state, and explicitly re-arm before restoring operation.

The provisional operator-supplied limits are 2.5 A cutoff, 11.0 V minimum, and
13.0 V maximum. The numeric settings are now present, but
ADS_PROTECTION_LIMITS_VERIFIED defaults to zero. They are NOT approved limits
merely because they are entered. Current at/above 2.5 A and voltage below 11 V
or above 13 V fail readiness/trip the existing motor-protection path. Sensor
invalidity or unverified electrical calibration rejects starts. Circuit INA219
readings never substitute for motor measurements or affect those limits.

Relays still use PB4 for CIRCUIT and PB5 for MOTOR. Safe relay polarity/reset
behavior, hardware cutoff, communication-loss shutdown, electrical calibration,
and protection settings must all be confirmed before output permission can be
compiled in. No acceptance flag was silently marked verified in this delivery.
Temperature remains disabled; provisional encoder scaling remains 11 x 34 = 374
A rising edges/output revolution. Normal/supervised operation preserves the
fixed approved duty, 30-second maximum, heartbeat watchdog, shared fault/stop
path, duplicate-request protection, and explicit re-arm after fault/disconnect.
Every reset boots with PWM zero, relay inactive and controller DISARMED. A build
with physical output permission enabled still boots stopped; permission is not
an automatic start instruction.

## Pin review and proposed feedback

| Function | Existing assignment | Change |
| --- | --- | --- |
| Circuit relay | PB4 / D5 | Preserved |
| Motor relay | PB5 / D4, HIGH active / LOW inactive | Preserved |
| Motor PWM | PB10 / TIM2 CH3 / D6 | Preserved |
| Motor direction | PA8 / D7 | Preserved |
| Encoder A / B | PA6 / PC7 | Preserved |
| INA219 I2C1 SCL / SDA | PB8 / PB9, motor 0x40 and circuit 0x41 | Preserved |
| DS18B20 | PA10 | Preserved, disabled for motor tests |
| USB serial USART2 | PA2 TX / PA3 RX, 115200 8-N-1 | Preserved |
| Circuit ADC | PA0 | Preserved |
| Proposed power feedback | PC8, active HIGH, 3.3 V | Reserved; NOT INSTALLED by default |

PC8 has no existing assignment in the checked-in .ioc or application. ST's
[UM1724 Rev 17, Table 29, page 59](https://www.st.com/resource/en/user_manual/um1724-.pdf)
places PC8 on NUCLEO-F401RE Morpho CN10 pin 2. That verifies the documented board
mapping, not the actual header orientation, attached wiring, or signal behavior
on this prototype. Inspect the physical board before connecting it. Source
macros reserve PC8; .ioc regeneration is not used to enable an unverified input.
A normal-mode feedback signal must be ready HIGH before motor activation, not a
signal that can only become HIGH after the motor relay closes. It must be a
verified 3.3 V logic signal; never connect the 12 V rail directly to PC8. Verify
LOW/disconnected behavior and an appropriate external fail-closed bias/interface
before setting the wiring-verification flag. PB4/PB5 are never feedback pins.

## Protocol and dashboard

Existing ADS v1 envelopes, CRC32 and sequence correlation are preserved. Example
ARM request payload for the supervised mode:

```json
{"command":"ARM_TEST","arguments":{"supervised_confirmed":true}}
```

Only literal true in the arguments object counts. Missing, false, number, string,
nested confirmations or replayed request sequences do not authorize a new run. A fresh
heartbeat and new control sequence are still required. Confirmation is consumed
by ARM, held for that armed run, and cleared by stop, completion or fault.
CLEAR_FAULTS uses the same confirmation gate. START_TEST still requires successful
ARM, the approved PWM, FORWARD direction and a bounded duration. A new run after
a stop/fault requires a new explicit confirmation. Read-only polls never arm.

Capabilities and correlated status/ACK results identify operating_mode,
power_feedback_installed and power_feedback_state (NOT_INSTALLED, UNVERIFIED,
LOW or HIGH). Capabilities also report protection_limits_verified and the exact
millivolt/milliamp limits. ARM/START report rejection reasons. The Pi rejects
mode, feedback-installation or protection-limit mismatches before ARM. A
provisional firmware limit flag remains a blocker even if the Pi profile claims
it was verified.

The existing Motor control page shows Pi mode, STM32 mode, feedback status and
protection-verification status. Supervised mode has a per-test confirmation
checkbox and an explicit Start Motor confirmation. The existing Run diagnostic
hardware path also requests explicit supervised confirmation. The API independently
requires supervised_confirmed=true and operator_authorized=true for a supervised
sequence; a profile alone cannot authorize it. Mode/feedback information is
retained in the run configuration, status, raw records and CSV. Existing
simulation controls, archive replay, dual-INA219 monitoring and layout styles
are preserved. LCD/touch operation has not been physically checked here.

## Builds and current artifacts

The default NORMAL build remains output-disabled:

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
make -C ADS -j4
```

Artifact: build/stm32-default-disabled/ADS.elf.

A separately configured supervised example is provided. It deliberately keeps
all unverified acceptance flags and physical output permission zero:

```sh
make -C ADS OUT=../build/stm32-supervised-disabled BENCH_PROFILE=bench/supervised.example.h -j4
```

Artifact: build/stm32-supervised-disabled/ADS.elf. This image reports
SUPERVISED_TEST and NOT_INSTALLED, but rejects starts until the required approvals
are completed. The Makefile requires a separate output directory when a bench
profile is selected, preventing reuse of default-mode objects. Use a new OUT
when switching between different bench profiles. Header edits within a profile
are included in dependency tracking.

For an actual approved supervised build, copy ADS/bench/supervised.example.h to
a separate reviewed header and record the hardware acceptance. Only after those
checks, change the corresponding flags in that private build profile:

- ADS_RELAY_SAFE_OUTPUT_VERIFIED — relay inactive on reset/startup, safe polarity
  and stop behavior measured; power path and polarity are separately checked.
- ADS_KILL_SWITCH_VERIFIED — physical cutoff actually interrupts motor energy.
- ADS_COMM_LOSS_STOP_VERIFIED — measured stop on heartbeat/USB loss and watchdog.
- ADS_INA219_CALIBRATED — motor electrical measurements checked against references.
- ADS_PROTECTION_LIMITS_VERIFIED — the selected limits/protection have been accepted.
- ADS_SUPERVISED_TESTING_APPROVED — supervised procedure and accessible cutoff accepted.
- ADS_PHYSICAL_OUTPUT_ENABLED — permission for explicit accepted motor commands.

Keep MODE=1 and feedback installation/wiring flags zero when PC8 is uninstalled.
Do not claim NORMAL feedback/interlock verification in a supervised profile.
For normal mode, install/verify PC8 and use MODE=0 instead. Required voltage
precheck is unchanged: INA219 placement must supply an in-range motor supply
reading before start while the relay is inactive. If the sensor is downstream
and reads zero with the relay open, that topology remains a blocker; this task
does not energize the motor branch just to bypass precheck.

No output-enabled ELF is supplied based on unverified protection/relay settings.
Both delivered images can be flashed for USB-only inspection with external motor
energy disconnected, following the explicit image-selection instructions in
DASHBOARD_MOTOR_CONTROL.md. Do not flash the old ADS/Debug/ADS.elf or the separate
older /Users/markussanford/ADS project. CubeIDE-managed builds do not automatically
inherit Makefile BENCH_PROFILE: select the exact prebuilt ELF rather than allowing
an automatic rebuild to substitute another image.

## Pi profile and operator sequence

The default example is NORMAL. The new supervised example is explicit and still
blocked until its acceptance fields are completed:

```sh
cd "$HOME/Trace-X"
mkdir -p "$HOME/.config/trace-x"
cp deploy/pi/supervised-hardware-profile.example.json "$HOME/.config/trace-x/motor-hardware.json"
nano "$HOME/.config/trace-x/motor-hardware.json"
nano "$HOME/.config/trace-x/runtime.env"
```

The profile sets operating_mode=SUPERVISED_TEST, power_feedback_installed=false,
11/13 V and 2.5 A provisional settings, 50% fixed duty and 30000 ms maximum.
Supply the real USB serial identity, asset/fixture/calibration/evidence IDs and
verified acceptance fields. Keep interlock_verified=false when no normal
feedback interlock exists. Relay, cutoff, communication-stop, calibration,
protection_limits_verified, supervised_testing_approved and operator_enable
remain required. NORMAL requires interlock_verified and installed/verified
feedback instead. Firmware and profile versions/modes/limits must agree.

Set the reviewed profile's absolute path in runtime.env:

```dotenv
ADS_AUTOMATION_HARDWARE_PROFILE=/home/amirzoom8/.config/trace-x/motor-hardware.json
ADS_LIVE_PROTOCOL=ads_json
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0
```

Read-only monitoring remains independent of motor authorization and yields the
serial port while the automated engine owns a run. Stop the service before a
standalone verifier. For a default-disabled USB-only protocol check:

```sh
systemctl --user stop trace-x.service
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port /dev/ttyACM0 --protocol json --crc32
.venv-pi/bin/python -m diagnostic_platform.verify_ina219 --port /dev/ttyACM0 --samples 5
systemctl --user restart trace-x.service
curl -s http://127.0.0.1:13115/api/motor/hardware/status
```

The older generic connection verifier intentionally expects hardware_control=false;
its safety check should not be used as a pass criterion for a later approved
output-enabled bench build. For that build inspect capabilities/status explicitly
and perform the instrumented acceptance procedure. In the dashboard verify
SUPERVISED_TEST / NOT INSTALLED, check the presence/cutoff confirmation, select
the approved duty and duration, then explicitly press Start Motor. Stop Motor,
local deadline, emergency stop, invalid measurement, and communication loss must
all remove PWM and request relay LOW. Verify this with motor isolated before any
supervised powered run, and establish expected physical stop timing. Mode labels
and software ACKs are not independent contact or shaft-motion feedback.

## Files changed in this task

- ADS/Core/Inc/ads_board_config.h — restored delivered configuration, provisional limits, explicit mode/feedback/verification flags.
- ADS/Core/Inc/main.h — proposed PC8 reservation only.
- ADS/Core/Inc/ads_motor.h and ADS/Core/Src/ads_motor.c — real normal-mode feedback and separate supervised readiness.
- ADS/Core/Inc/ads_test.h and ADS/Core/Src/ads_test.c — one-run supervisor confirmation and clearing.
- ADS/Core/Src/ads_protocol.c — strict confirmation arguments, mode/feedback/protection reports, version 0.5.0.
- ADS/Core/Src/main.c — mode and feedback callback registration.
- ADS/Makefile and ADS/bench/supervised.example.h (new) — explicit separate bench build.
- diagnostic_platform/automated_engine.py — profile gates, fresh confirmation, mode/limit matching, ACK and CSV metadata.
- diagnostic_platform/motor_csv.py — mode and feedback columns.
- api/main.py and api/schemas.py — mode status and strict supervisor request field.
- deploy/pi/hardware-profile.example.json and supervised-hardware-profile.example.json (new) — normal/supervised examples.
- frontend/src/HardwareMotorControls.tsx, App.tsx, api.ts and types.ts — mode labels and per-test confirmation.
- tests/bounded_motor_harness.c, hal_stub/stm32f4xx_hal.h, test_bounded_motor.py and test_motor_dashboard_integration.py — fixtures for new verification gates.
- tests/power_feedback_harness.c and tests/test_supervised_mode.py (new) — normal/supervised GPIO, protocol and engine tests.
- README.md, docs/DASHBOARD_MOTOR_CONTROL.md, docs/DUAL_INA219_INTEGRATION.md, .env.example and this guide — current operating instructions.

Local IDE preferences under ADS/.settings were already modified by the operator
and were left untouched. Pre-task copies of the locally edited configuration
and protocol source are in ignored deliverables/pre-supervised-source-backup/.
Their safe default/dual-address/temperature-off behavior is preserved in the
updated implementation; earlier zeroed motor parameters were reconciled with
the operator-supplied settings. Nothing was pushed to GitHub in this task.

Final build, test and artifact results follow below.

Final verification:

- Full unittest suite: 174 passed (16.117 seconds). New checks cover strict/fresh
  supervisor confirmation, grant clearing on stop/heartbeat fault, CLEAR_FAULTS,
  normal LOW/HIGH feedback, uninstalled/unverified PC8, no automatic restart,
  supervised mode approval/limit gates, deadline/watchdog shutdown, mode mismatch,
  API strict boolean validation, and a complete in-memory supervised sequence.
- ARM syntax-only checks compile the verified PC8 paths for both modes against
  real F401 headers. These do not produce an output-enabled image.
- Both default-disabled ARM target builds passed with GCC 14.3.rel1.
  NORMAL: text 29652 / data 92 / BSS 19532 bytes.
  SUPERVISED_TEST: text 29632 / data 92 / BSS 19532 bytes.
- Frontend TypeScript/Vite build and ESLint passed; existing size advisory remains
  (658.04 kB JavaScript / 195.01 kB gzip).
- CRLF-aware Git whitespace check passed.
- Hardware, LCD/touch and physical protection checks were not performed.

NORMAL ELF SHA-256: `8214f57559b59e69d14129ddd484e80427c63e07b5d888fed042dc25300fb51b`.

SUPERVISED_TEST ELF SHA-256: `bded64e0d7840762fd4e247c8c2f337f4dbe774a44b8884cacd03776adb34482`.

Both images have .elf.sha256 and .elf.manifest.json files alongside them. The
manifests explicitly record disabled output permission, operating mode,
provisional limits, feedback installation, and configuration fingerprints.
The refreshed deployable source/UI bundle is deliverables/Trace-X-Pi.zip.
These November 9 changes are local and have not been pushed to GitHub.
