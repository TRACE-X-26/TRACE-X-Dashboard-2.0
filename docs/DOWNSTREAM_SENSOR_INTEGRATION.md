# Sensors after the relays — firmware 0.7.0-downstream-protected

This is the current implementation and supersedes the upstream-only 0.6.0
instructions. Both INA219s may remain AFTER their respective relays. No sensor
rewiring is required for this motor-start sequence. Existing supervised Start
authorization covers the bounded power check; there is no additional approval
prompt. No hardware was flashed or operated by the coding agent.

## Motor Start sequence

1. Read-only checks verify the actual firmware, protection capabilities, stopped
   output, calibration/freshness, motor stationarity and off-state readings.
   Approximately zero motor voltage/current is expected with its relay open.
2. The operator presses Start Motor and confirms the existing supervised action.
3. ARM_TEST explicitly re-arms. PREPARE_TEST_POWER closes only motor relay IN1
   (D4/PB5 LOW), with TIM2 CH3 disabled and PWM D6/PB10 held LOW (0%).
4. STM32 accepts a motor electrical conversion only if it began at least 50 ms
   after relay activation. Old/pre-relay measurements cannot authorize PWM.
5. The fresh sample must be valid, calibrated, within 10.0–14.0 V inclusive and
   below 1.5 A absolute current. The STM32 reports POWER_READY while PWM remains
   zero. Pi independently checks the acquisition interval and same limits.
6. Only then does the Pi send SET_PWM and START_TEST for the approved duty (50%).
   Firmware applies PWM without cycling the already-closed relay and emits the
   correlated motor-start event/timestamp. The motor-run timer starts here.
7. Normal Stop, cancellation, faults or heartbeat loss disable PWM and release
   the relay HIGH. A fresh explicit re-arm is needed after fault/timeout.

The relay-on, PWM-zero phase has a separate **1500 ms firmware deadline**, which
is not reset by repeated Prepare/ARM requests. Missing sensor, invalid sample,
failed relay/load supply, or failure to reach POWER_READY prevents PWM. The Pi
also has a bounded wait. The motor run remains bounded to 30 seconds; total
relay-on time can include up to 1.5 seconds before that run. No timer automatically
starts motor PWM. The firmware timer checks operate independently of the Pi.

Read-only Check hardware NEVER closes a relay. Its passing result means the
off-state checks passed; the powered voltage check is deliberately performed
only after the existing operator Start action. Software still rejects current
at/above 1.5 A and voltage above 14 V before the power check. An off-state bus
already at or above 10 V is rejected as POWER_PRESENT_WHILE_STOPPED (possible
stuck relay, external power or retained charge); it is not assumed safely off.

## Preserved wiring and behavior

| Function | Assignment |
|---|---|
| Motor relay | D4/PB5 -> IN1 -> COM1/NO1, S1 COM–LOW |
| Circuit relay | D5/PB4 -> IN2 -> COM2/NO2, S2 COM–LOW |
| PWM / direction | D6/PB10 TIM2 CH3 / D7/PA8 |
| Encoder A / B | D12/PA6 rising edges / D9/PC7 direction |
| Motor INA219 | 0x40, unbridged; after motor relay |
| Circuit INA219 | 0x41, A0 bridged; after circuit relay |
| Serial | ST-LINK USART2, 115200 8-N-1, ADS v1 CRC32 |

Both relay channels use LOW=ON, HIGH=OFF. Source profiles keep outputs disabled
by default. CubeIDE Debug/Release still choose the output-disabled protected
profile. Circuit supply switching and its sensor remain independent; motor and
circuit operations cannot overlap. Motor protection never substitutes circuit
readings. Circuit supply readings are not calibrated circuit test-point probe
voltages. Existing guided circuit capture/reference diagnostics remain available;
probe scaling and actual fault-classifier operation still need hardware validation.
Simulation, recordings, baselines, history, dashboard layout and touch CSS are
preserved. No baseline data or private configuration was overwritten/retrained.

## Electrical limits and limitations

10–14 V and 1.5 A protections remain enabled throughout the motor run. Zero
voltage is accepted only for the initial relay-off check or while waiting for
an eligible post-relay conversion; it never authorizes motor PWM. Invalid/failed
readings are not converted to valid zeroes. Both prepower and running paths
fail closed if a required acquisition callback is missing.

Without upstream sensing this sequence cannot check the supply before energizing
the driver. It powers the driver at zero commanded PWM, then verifies voltage;
it does not provide upstream pre-energization overvoltage protection. The 50 ms
settling allowance and physical relay response still need bench testing. Sensor
polling is approximately every 100 ms; software monitoring is not instantaneous
short-circuit protection. Preserve the fuse and operator power cutoff.

A relay-off acknowledgment is a firmware command state, not auxiliary-contact
feedback. A zero/downstream voltage check catches missing load supply but cannot
uniquely diagnose a failed relay versus wiring/supply loss. A retained charge may
block a new start until the bus falls. Actual relay release at 3.3 V HIGH,
reset/power-loss biasing, trip latency and motor rotation require bench checks.
Firmware cannot control GPIO while the STM32 is held in reset or unpowered.

## Current files and control messages

- ADS/Core/Src/ads_motor.c: bounded zero-PWM power phase, explicit re-arm,
  independent timer/heartbeat shutdown and transfer to PWM without a relay cycle.
- ADS/Core/Src/ads_protection.c and ads_sensors.c: fresh post-settle sample checks,
  electrical cutoffs and separate idle/running rules.
- ADS/Core/Src/ads_test.c and ads_protocol.c: PREPARE_TEST_POWER, POWER_CHECK /
  POWER_READY states, correlated replies and relay command state.
- ADS/Core/Src/main.c: connects those callbacks to the existing controller.
- diagnostic_platform/protocol.py / stm32.py: new command and read-only control gate.
- diagnostic_platform/hardware_runtime.py / automated_engine.py: downstream
  contract and phased acquisition validation; hardware-only power preparation.
- diagnostic_platform/circuit_power.py: rejects motor power-check ownership.
- deploy/pi/*profile*.json: matching version/topology metadata; protected defaults.
- frontend/src/HardwareMotorControls.tsx: explains the zero-PWM check.
- C harnesses/Python tests: sequence, sample eligibility, timeout/cancellation,
  duplicate Prepare, zero PWM, numeric trips, relay-off confirmation and read-only denial.

ADS payload examples (the serial adapter supplies envelope, sequence and CRC):

```json
{"command":"ARM_TEST","arguments":{"supervised_confirmed":true}}
{"command":"PREPARE_TEST_POWER","arguments":{}}
{"command":"GET_STATUS","arguments":{}}
{"command":"SET_PWM","arguments":{"pwm_percent":50}}
{"command":"START_TEST","arguments":{"pwm_percent":50,"duration_ms":30000,"direction":"FORWARD"}}
{"command":"STOP_TEST","arguments":{}}
```

Capabilities must advertise electrical_limits_enabled=true,
supply_sensing=DOWNSTREAM_POWER_CHECK, power_check_required=true,
power_check_timeout_ms=1500 and power_check_settle_ms=50. PREPARE ack reports
POWER_CHECK, applied_pwm_percent=0, motor_relay_requested_on=true and
power_started_ms. START is rejected until POWER_READY. The existing requested
PWM and actually applied PWM remain separate. Start/stop events bound motor
analysis samples; prepower raw data are retained separately in the run journal.

## Flash the exact current image

On the Mac:

```sh
cd /Users/markussanford/Documents/ChatGPT/Capstone
make -C ADS OUT=../build/stm32-downstream-disabled BENCH_PROFILE=bench/protected.example.h -j4
```

The current default image is `build/stm32-downstream-disabled/ADS.elf`.
In CubeIDE refresh ADS, choose **ADS Downstream Protected** from
`ADS/ADS Downstream Protected.launch`, then verify that exact ELF path. Disconnect
external branch power, connect ST-LINK USB, Debug, wait for **Download verified
successfully**, Resume/F8 if paused at main, then terminate the debugger before
moving USB to the Pi. Older launch files can point to older binaries; do not
select them. Do not regenerate .ioc GPIO setup over gated user code.

This delivered default remains blocked, as requested for safe defaults. For a
reviewed enabled build use the existing ignored local commissioning profile,
with PHYSICAL_OUTPUT_ENABLED, supervised approval, relay/kill/communication and
calibration acceptance, and PROTECTION_LIMITS_VERIFIED set only from existing
operator acceptance. No UPSTREAM sensing flag or new power-check approval flag
is required. Build that explicit profile into a separate directory, then select
its ELF manually; the disabled launch deliberately does not substitute it:

```sh
make -C ADS OUT=../build/stm32-downstream-commissioned BENCH_PROFILE=bench/commissioned.local.h -j4
```

## Pi deployment

Both firmware and backend must be updated; the older backend has no Prepare
phase. Transfer `deliverables/Trace-X-downstream-update.zip` to
`/home/amirzoom8/Trace-X-downstream-update.zip` on the Pi. Then:

```sh
cd /home/amirzoom8/Trace-X
systemctl --user stop trace-x.service
.venv-pi/bin/python deploy/pi/backup_database.py
mkdir -p /home/amirzoom8/trace-x-downstream-update
unzip -o /home/amirzoom8/Trace-X-downstream-update.zip -d /home/amirzoom8/trace-x-downstream-update
rsync -a --exclude='.git/' --exclude='.env*' --exclude='*.local.h' --exclude='data/' --exclude='recordings/' --exclude='baselines/' --exclude='experiments/' /home/amirzoom8/trace-x-downstream-update/Trace-X/ /home/amirzoom8/Trace-X/
.venv-pi/bin/python -m pip install -r requirements-backend.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

Preserve existing source customizations separately before copying. The archive
excludes databases, recordings, baselines, private env files, local commissioning
headers and CubeIDE workspaces. No rsync --delete is used.

Create a new configuration copy, preserving the old private file, USB identity
and acceptance records. This does not mark unresolved protections verified or
enable hardware automatically:

```sh
.venv-pi/bin/python - <<'PY'
import json
from pathlib import Path
base=Path.home()/'.config/trace-x'
v=json.loads((base/'motor-hardware.json').read_text())
v.update(firmware_version='0.7.0-downstream-protected',electrical_limits_enabled=True,
         limits={'min_voltage':10.,'max_voltage':14.,'max_current':1.5},
         supply_sensing={'location':'DOWNSTREAM_MOTOR_RELAY','verified':True,
                         'basis':'operator-confirmed sensors after relays'})
v['relay'].update(active_level=0,inactive_level=1)
v.setdefault('protection_limits_verified',False)
with (base/'motor-hardware.downstream.pending.json').open('x') as f:
    json.dump(v,f,indent=2);f.write('\n')
PY
nano ~/.config/trace-x/runtime.env
```

Select the NEW absolute profile path in ADS_AUTOMATION_HARDWARE_PROFILE. Retain
ADS_MODE=simulation for the separate demos, ADS_LIVE_PROTOCOL=ads_json and
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0. Hardware runtime remains an explicit existing
operator setting (ADS_HARDWARE_CONTROL_ENABLED); no new prompt or auto-enable
is introduced. The profile's protection_limits_verified/calibration/relay/cutoff
acceptance must correspond to real checks. With the delivered disabled firmware,
expect hardware control blocked; configuration cannot override firmware permission.

```sh
systemctl --user restart trace-x.service
curl --fail http://127.0.0.1:13115/api/motor/hardware/status
journalctl --user -u trace-x.service -n 40 --no-pager
```

Open http://127.0.0.1:13115/ -> Motor -> Check hardware. This check should accept
fresh near-zero voltage with the relay OFF. Once matching enabled firmware and
existing acceptance settings are deliberately installed, Start Motor performs
the power check automatically. For the first actual test use a short duration,
observe that PWM stays zero during POWER_CHECK, verify transition to POWER_READY
then RUNNING, and verify Stop and the physical cutoff. Actual operation was not
performed here. RPM scaling is still provisional; temperature remains retired.

## Final verification

- 223 tests passed in 28.077 seconds, using only fake GPIO/serial devices.
- Protected downstream-disabled ARM build passed: text 32800 / data 92 / BSS 19684 bytes.
- Generic default-disabled ARM build passed: text 32732 / data 92 / BSS 19684 bytes.
- Production frontend build and ESLint passed; existing bundle-size advisory remains.
- Tests cover power-check-before-PWM, sample age/settling, negative/missing samples,
  voltage/current trips, repeated Prepare/Start, timeouts, cancellation, read-only
  denial, relay-off acknowledgments, heartbeat/fault shutdown and default-disabled outputs.
- No physical relay/sensor/LCD/motor operation or flashing was performed.
