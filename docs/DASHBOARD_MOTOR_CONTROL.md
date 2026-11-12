# Dashboard motor control — November 6, 2026

November 9 operating-mode update: [normal PC8 feedback and explicit supervised testing](SUPERVISED_MOTOR_TESTING.md), firmware 0.5.0-supervised-motor. Earlier hashes and mode requirements below are historical.

Latest sensor update: [dual INA219 0x40/0x41 integration and verification](DUAL_INA219_INTEGRATION.md), firmware 0.4.2-dual-ina219. Earlier firmware hashes and sizes below are historical.

This update supersedes the motor configuration in FULL_AUTOMATED_INTEGRATION.md.
Firmware identity: `0.4.1-dashboard-motor`. No board was flashed or operated.
The end-to-end command implementation is present, but this delivery deliberately
rejects physical starts while essential protection configuration is unresolved.
The output permission flag remains zero. This is not a powered-test acceptance.

## Recorded configuration

The operator supplied JGA25-371, 12 V, nominal output speed 130 RPM, Cytron MD10C
R3; PB5/D4 relay active HIGH/inactive LOW with successful 3.3 V triggering;
PB10/D6 TIM2 CH3 PWM; PA8/D7 direction; USART2 115200 8-N-1.
Relay output is preloaded LOW at startup, before changing PB5 to output. PWM is
held LOW and stopped. PB4 circuit relay is independent and untouched.
Physical reset/contact behavior still needs measurement; a written GPIO LOW is
not contact feedback. The supplied working main.c initializes PA8 LOW, so the
fixed FORWARD command reuses LOW. Verify actual rotation before treating that
name/sign as a calibrated direction convention.

Provisional encoder scaling is 11 A-channel rising edges per motor-shaft turn
and 34 motor-shaft turns per output turn: 374 counts/output turn. These are not
quadrature x4 counts. Signed output RPM = delta counts * 60000 / (11 * 34 * elapsed_ms).
The B channel establishes sign using the existing driver convention. Zero RPM
is valid telemetry, not proof that an encoder is connected. `encoder_calibrated`
stays false until measured shaft rotation confirms scaling/sign. Numerical RPM
is transmitted even when uncalibrated; the UI labels it provisional and analysis
abstains. The 130 RPM label is not a measured speed or a safety limit.

Temperature is disabled for this motor configuration. PA10 is not initialized or
polled by the acquisition driver, temperature stays null/invalid, and neither
STM32 readiness nor the Pi runner requires it. Setting ADS_TEMPERATURE_ENABLED=1
restores the existing DS18B20 driver and requires valid calibrated temperature
and a configured cutoff. Other simulation and circuit features are preserved.

The prior supplied source actually applies 50% (`period / 2U`) for 30 seconds
(`30000U`), despite comments saying 10%/10 seconds. The new configured duty is
50%, maximum duration 30000 ms. The dashboard exposes 10/25/50/75/100 presets;
only the separately commissioned fixed duty can start on hardware. Other values
remain blocked. To approve a different preset, both firmware fixed duty and Pi
profile must be reviewed and changed together. There is no physical PWM sweep
or duty change during a run. An assumed motor rating never approves a preset.

## Command path and shutdown

Motor control page -> real-hardware Start Motor -> POST /api/automated/runs ->
single-owner Pi engine -> CRC32 ADS v1 over USB serial -> fresh heartbeat,
ARM_TEST, SET_PWM staging, START_TEST -> correlated ACK and MOTOR_START event.
The STM32 sets direction, stages compare with the PWM channel disabled,
activates the relay, then enables PWM. Applied PWM means the STM32 register
setting, not a measured waveform or independently confirmed shaft motion.

GET_STATUS/READ_MEASUREMENTS feed the page's voltage, current, power, provisional
RPM, requested/applied PWM, command state, faults and elapsed time. This panel
never substitutes simulation values. Existing simulator controls remain separate.
Stop Motor, emergency stop, cancellation, limits, interlock loss and watchdog
loss use the common PWM-off/relay-off path. STM32 enforces the deadline locally;
heartbeat loss stops sooner at 2 seconds. No automatic restart/reconnect occurs.
Duplicate start requests cannot restart or extend the test; repeated stops are
safe. Leaving the hardware page closes its stream and requests cancellation.
STM32 timestamps describe software events, not measured relay contact motion.

Temperature-disabled hardware may run with provisional encoder telemetry once
all essential protections are accepted. Electrical calibration/validity remains
required for starting. Confirmed sensor wiring enables INA219/encoder acquisition
in the default USB-only image; successful uncalibrated readings are transmitted
with explicit calibration=false metadata, rather than substituted zeros.
INA219 current uses the inherited unverified 0.1 ohm shunt assumption. Sensor warm-up reads are bounded and occur before any start; no start
command is retried. Invalid current/voltage data still rejects/stops the test.

## Remaining physical blockers — do not replace with unconditional true

- No verified current cutoff was supplied. 0.5 A is an assumed operating reference,
  not a protection threshold; ADS_MOTOR_MAX_CURRENT_MA and Pi max_current remain
  unset. Determine a suitable limit from the motor, shunt, driver, wiring, fuse
  and supply constraints, including startup current. Existing fuses and the
  physical power switch remain in place; software does not replace them.
- Supply minimum/maximum limits and INA219 #1 calibration/shunt acceptance remain
  unconfigured. Confirm INA219 placement: precheck currently requires valid
  in-range supply while the relay is off. A downstream sensor reading zero with
  an open relay will be rejected; the system must not bypass the relay merely
  to make that precheck pass. Resolve that topology before enabling a run.
- Relay contact/reset behavior and communication-loss shutdown need bench checks.
- No power-switch/supply-feedback STM32 input was supplied. The existing
  ADS_Motor_InterlocksReady() hook still returns false. A reviewed fail-closed,
  ISR-safe feedback implementation and power-restoration/no-restart verification
  remain required. No GPIO has been invented, and the hook has not been bypassed.
- Firmware output permission and Pi operator_enable remain false. The Pi template
  also leaves identity/calibration/evidence details and unverified gates unset.

Firmware GET_CAPABILITIES includes temperature_enabled and hardware_block_reason.
Disabled command ACKs carry the recorded rejection reason. Pi
GET /api/motor/hardware/status shows profile readiness and missing gate names;
profile readiness alone does not prove that the connected board can start.

## Files changed for this increment

- ADS/Core/Inc/ads_board_config.h — motor configuration, optional temperature.
- ADS/Core/Inc/ads_motor.h, ADS/Core/Src/ads_motor.c — confirmed relay polarity,
  inactive startup, relay-before-PWM ordering, explicit blocking reasons.
- ADS/Core/Inc/ads_test.h, ADS/Core/Src/ads_test.c — board-specific disabled reason.
- ADS/Core/Src/main.c — registers that reason with the controller.
- ADS/Core/Src/ads_protocol.c — 0.4.1 identity, temperature/block capabilities.
- ADS/Core/Src/ads_acquisition.c — valid provisional RPM separate from calibration.
- ADS/Core/Src/ads_sensors.c — optional one-wire IO and readiness.
- diagnostic_platform/automated_engine.py — optional temperature, provisional RPM,
  bounded read-only warm-up, detailed profile errors, run CSV persistence.
- diagnostic_platform/motor_csv.py (new) — durable journal CSV rendering.
- api/main.py, api/schemas.py — hardware readiness, CSV download, 30 s default.
- frontend/src/HardwareMotorControls.tsx (new), App.tsx, api.ts, types.ts — hardware
  controls and status using existing visual styles; simulator kept separate.
- deploy/pi/hardware-profile.example.json — confirmed/provisional configuration
  with unresolved limits and gates explicitly blocked.
- tests/bounded_motor_harness.c, bounded_output_harness.c, motor_safety_harness.c,
  test_bounded_motor.py, test_automated_api.py, test_motor_dashboard_integration.py
  (new) — presets/deadline, relay ordering, optional temperature, provisional RPM,
  limits, CSV and API checks.
- docs/DASHBOARD_MOTOR_CONTROL.md (new), FULL_AUTOMATED_INTEGRATION.md,
  FULL_INTEGRATION_FILES.md, README.md — current handoff pointers and manifest.

## Build and flash on the Mac

Build command (does not flash):

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
make -C ADS -j4
```

Image: build/stm32-default-disabled/ADS.elf. It is the complete firmware; no old
main.c or old ADS/Debug/ADS.elf needs to be copied over it. Keep a backup of the
previously working firmware project and binary before replacing the board image.

For an initial USB-only verification, physically disconnect external motor power.
In CubeIDE import this repository's ADS project into a separate workspace,
select NUCLEO-F401RE, and explicitly select this exact ELF in the launch/load
configuration. Disable any automatic rebuild that would substitute Debug/ADS.elf.
Alternatively use STM32CubeProgrammer's Open File, select the exact ELF, select
the actual ST-LINK, connect through SWD, download, and verify. The default image
will keep motor output disabled. Do not enable a powered test by flipping flags
without resolving the listed blockers.

A CLI flash command for the operator is included below; it is NOT executed by
this integration task. Use only after checking the target and disconnecting
motor power. It downloads/verifies the ELF and resets the STM32:

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
PROGRAMMER="/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.macosaarch64_1.0.100.202603051304/tools/bin/STM32_Programmer_CLI"
"$PROGRAMMER" -c port=SWD -d "$PWD/build/stm32-default-disabled/ADS.elf" -v -rst
```

## Raspberry Pi commands

After copying the updated package into ~/Trace-X, install/update dependencies
and the user service. The installer preserves existing runtime.env settings:

```sh
cd "$HOME/Trace-X"
bash deploy/pi/install.sh
systemctl --user stop trace-x.service
ls -l /dev/serial/by-id/
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port /dev/ttyACM0 --protocol json --crc32
```

Replace ttyACM0 with the actual port. Run only one serial reader. The initial
USB-only check should report disabled hardware control. It does not demonstrate
motor operation, sensor calibration, relay contacts or stop timing.

Prepare a private commissioning profile (the example remains blocked):

```sh
mkdir -p "$HOME/.config/trace-x"
cp deploy/pi/hardware-profile.example.json "$HOME/.config/trace-x/motor-hardware.json"
nano "$HOME/.config/trace-x/motor-hardware.json"
nano "$HOME/.config/trace-x/runtime.env"
```

In runtime.env set the ABSOLUTE path, for this Pi username:

```dotenv
ADS_AUTOMATION_HARDWARE_PROFILE=/home/amirzoom8/.config/trace-x/motor-hardware.json
```

Complete serial_identity (the actual USB serial number), firmware identity,
asset/fixture/calibration/evidence IDs and accepted limits/gates only after the
corresponding requirements are resolved. A nonempty profile setting transfers
serial ownership to the automated engine and suppresses the passive reader.
The template cannot override disabled STM32 firmware.

Start and inspect the service:

```sh
systemctl --user restart trace-x.service
journalctl --user -u trace-x.service -n 60 --no-pager
curl -s http://127.0.0.1:13115/api/motor/hardware/status
chromium --kiosk http://127.0.0.1:13115/
```

Open Motor control -> STM32 motor test. Start Motor remains unavailable until
Pi profile approval, and the STM32 still independently rejects unsafe starts.
After physical commissioning, select the approved PWM, choose duration (default
30 seconds), explicitly confirm Start Motor, observe actual readings/source,
and verify Stop Motor and the local deadline with an instrumented controlled
setup. Establish cable-removal, reset, interlock/power-restoration and no-restart
behavior before presenting automated operation as physically verified.

## Logs and verification

SQLite retains raw protected frames, samples, quality flags, status and events.
At finalization the engine also writes <database directory>/automated_csv/<run ID>.csv.
Download motor CSV is available from the panel and
GET /api/automated/runs/{id}/csv, including a snapshot during an active run.
Columns contain run/test ID, source, host and STM32 timestamps, requested/applied
PWM, V/A/W/RPM, calibration, motor state, stop reason, stop confirmation and
quality. Start/stop events are separate rows with STM32 timestamps. Blank values
mean invalid/missing; valid zero is preserved. Partial/disconnected runs stay
incomplete and never imply a confirmed physical stop. Simulation CSVs are labeled.

Verification results are recorded after the final checks below. Hardware/LCD
visual testing, flashing and powered operation were not performed here.

Final software checks:

- Python unittest discovery: 151 passed (11.334 seconds), including host C harnesses,
  protocol interoperability, API/WebSocket workflow and new motor regressions.
- Motor safety harness additionally checks that the production gates reject output.
- ARM GCC 14.3.rel1 target build: passed, text 26480 bytes, data 92, BSS 12108.
- ARM syntax checks cover temperature enabled and disabled configurations.
- Frontend TypeScript/Vite build and ESLint: passed. Existing >500 kB bundle warning
  remains; resulting JavaScript is 653.02 kB (193.74 kB gzip).
- Git whitespace check with CRLF-aware settings: passed.
- CubeProgrammer 2.23.0 local help verified CLI download/verify/reset options; it
  reported sandbox preference-write warnings. No device connect/download occurred.

Firmware SHA-256: `6e13d12e6fd9f835c5768aa6eca64fac4c3ead908a24c1bef1fbde0188f6fc15`.
The .elf.sha256 file is alongside the image. The updated Pi ZIP is
`deliverables/Trace-X-Pi.zip`, with its checksum alongside; firmware is separate.
All changes remain local. GitHub publication requires a separate instruction.
