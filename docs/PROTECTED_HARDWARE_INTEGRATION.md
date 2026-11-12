> Current sensor placement is downstream of the relays. Use [DOWNSTREAM_SENSOR_INTEGRATION.md](DOWNSTREAM_SENSOR_INTEGRATION.md) and firmware 0.7.0. No upstream relocation is required for the bounded zero-PWM power-check sequence.

# Protected STM32/Pi integration — 0.6.0-protected-relays

This version supersedes the telemetry-only 0.5.2/0.5.3 instructions. Both
firmware and Pi enforce motor voltage **10.0–14.0 V inclusive** and absolute
current **strictly below 1.5 A** (1.5 A trips). No electrical-limit-disable
runtime fallback is supported. Software verification is not electrical
commissioning. Outputs remain disabled in the delivered default image.

## Wiring prerequisite and known mappings

| Signal | Existing assignment |
|---|---|
| Motor relay IN1 | D4 / PB5, active LOW (S1 COM–LOW) |
| Circuit relay IN2 | D5 / PB4, active LOW (S2 COM–LOW) |
| Motor power | relay COM1–NO1 |
| Circuit power | relay COM2–NO2 |
| Motor PWM | D6 / PB10 / TIM2 CH3, 1 kHz |
| Direction | D7 / PA8, fixed configured forward level |
| Encoder | A D12/PA6 rising-edge x1; B D9/PC7 direction |
| INA219 motor / circuit | I2C1 PB8/PB9, 0x40 / 0x41, each R100/0.1 ohm |
| Serial | USART2 PA2/PA3 through ST-LINK USB, 115200 8-N-1 |

These are source mappings and operator-reported connections, not an inspection
of the physical board. No pins were reassigned. Both relays command HIGH for
OFF and LOW for ON. The protected CubeIDE default preloads inactive levels
before output configuration. STM32 pins are not firmware-controlled during
power loss/reset, so bench verification of fail-safe external bias/interface is
still necessary. In particular, confirm that 3.3 V HIGH releases this 12 V relay
module and that no 12 V signal can reach a GPIO. The green/red indicators are
not contact feedback.

**Do not fix zero-voltage preflight by closing the relay blindly.** If the motor
INA219 is downstream of NO1, this implementation requires moving its motor
branch measurement point upstream of the relay (power OFF while rewiring):

```text
12 V supply -> fuse -> physical cutoff -> motor INA219 VIN+
motor INA219 VIN- -> relay COM1 -> relay NO1 -> MD10C supply +
supply return --------------------------------> MD10C supply -
```

The INA219 bus-voltage measurement is then before the open relay, while its
shunt remains in series with motor-branch current. Relay-coil/circuit loads must
not be included in that shunt path. Keep the circuit branch independent. A
qualified bench check must confirm the exact connector markings, common
measurement reference, polarity and reference-meter agreement before setting
`supply_sensing.verified=true`. With relay open, expected motor voltage is about
11.9 V and current approximately zero. Zero current is valid; zero supply
voltage is not a motor-start pass. A supply voltage reading alone cannot prove
that the relay closes or opens.

If this relocation is not possible, an additional calibrated upstream voltage
channel is required and must be integrated separately. A staged relay-power
sequence using only the downstream sensor has NOT been implemented. The current
firmware rejects unverified sensing rather than treating that topology as safe.
PC8 remains the previously reserved, uninstalled 3.3 V supply feedback input;
no new connection or relay feedback is assumed.

## Implemented control and protection

Motor requests go from React HardwareMotorControls through the existing
`/api/automated/runs` hardware mode, HardwareRuntime, exclusive serial owner,
ADS CRC32 request/reply envelopes and the bounded STM32 controller. The legacy
simulation controller never receives a hardware motor-start request. Simulation
still has its own labelled results; baseline records are not changed/retrained.

Before ARM: exact USB identity and firmware version, protected capability flags,
10–14 V / 1500 mA matching limits, verified upstream sensing, relay polarity,
operating mode/feedback agreement, approved PWM/duration, fresh/calibrated
measurements and stopped output must pass. ARM requires fresh supervision and
heartbeat. SET_PWM stages the approved value only; it does not energize output.
START_TEST must acknowledge the request sequence, requested/applied PWM, run ID,
state and MCU start timestamp, with a matching MOTOR_START event. Replayed or
repeated starts do not extend/restart a run. STOP is idempotent.

STM32 protection uses motor channels only, rejects invalid/stale/mixed samples,
and checks voltage/current before output activation. During a run, SysTick
calls the low-level motor protection callback against the cached acquisition;
missing callback fails closed. Electrical cache publication is atomic against
that interrupt. Trip, heartbeat loss or invalid data disables PWM and requests
relay OFF; sensor recovery/heartbeat cannot restart it. The high-level controller
also latches the fault. A fresh explicit ARM is required. Normal completion,
cancellation, emergency stop and UART faults retain shutdown and zero-output
acknowledgments. Firmware bounds every motor run to at most 30 seconds.

INA219 polling attempts are approximately every 100 ms; stale acquisition limit
is 1500 ms. This is software monitoring, not an instantaneous short-circuit
protector. Retain the fuse and physical power cutoff; measure actual trip latency
and reset behavior at the bench. Events/acks confirm firmware commands, not
mechanical contact positions or actual shaft stop.

Circuit power remains a separate bounded controller, sensor 0x41, relay channel
2, independent of motor voltage limits. Motor/circuit arming/running cannot
overlap. Circuit configuration can be validated without claiming motor sensing
commissioned, and circuit samples never substitute for motor samples. Circuit
supply switching is not a validated automatic Circuit 4 diagnostic: test-point
probe scaling/calibration, asset mapping and fault-classifier hardware validation
remain outstanding. Existing operator-guided capture/reference analysis is kept.

## Default build and exact flash steps

On the Mac:

```sh
cd /Users/markussanford/Documents/ChatGPT/Capstone
make -C ADS OUT=../build/stm32-protected-disabled BENCH_PROFILE=bench/protected.example.h -j4
```

The delivered `build/stm32-protected-disabled/ADS.elf` is output-disabled. Both
CubeIDE Debug and Release now select `ADS_USE_PROTECTED_PROFILE=1` and the same
blocked profile. Generic `make -C ADS` also remains blocked. Do not select the
older Active Low Relays/Branch Power/Supervised Enabled launch: they may point
to earlier telemetry-only images. Do not regenerate GPIO from the current .ioc;
PWM/relay/sensor setup is intentionally in gated user code.

1. Disconnect external motor/circuit power, connect ST-LINK USB to the Mac.
2. In CubeIDE import/refresh the existing ADS project from
   `/Users/markussanford/Documents/ChatGPT/Capstone/ADS`.
3. Run > Debug Configurations > STM32 C/C++ Application > **ADS Protected Disabled**.
4. Confirm application `../build/stm32-protected-disabled/ADS.elf`.
5. Debug; wait for **Download verified successfully**. Resume/F8 if paused at main,
   then terminate the debugger before moving USB to the Pi.

Nothing here was flashed/reset/run automatically. The image should identify as
`0.6.0-protected-relays` and report hardware_control=false until commissioning.

## Pi deployment without replacing data or private configuration

The source-only package is `deliverables/Trace-X-protected-update.zip`. Transfer
it to `/home/amirzoom8/Trace-X-protected-update.zip` on the Pi, then:

```sh
cd /home/amirzoom8/Trace-X
systemctl --user stop trace-x.service
.venv-pi/bin/python deploy/pi/backup_database.py
```

The backup command creates a consistent copy of the configured database under
backups/. The update archive contains no database or recordings. Extract
code into a temporary directory and copy without deleting existing files:

```sh
mkdir -p /home/amirzoom8/trace-x-protected-update
unzip -o /home/amirzoom8/Trace-X-protected-update.zip -d /home/amirzoom8/trace-x-protected-update
rsync -a --exclude='.git/' --exclude='.env*' --exclude='*.local.h' --exclude='data/' --exclude='recordings/' --exclude='baselines/' --exclude='experiments/' /home/amirzoom8/trace-x-protected-update/Trace-X/ /home/amirzoom8/Trace-X/
.venv-pi/bin/python -m pip install -r requirements-backend.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

The archive excludes private env files, SQLite databases, baselines/recordings,
CubeIDE workspaces, editor settings and local commissioning headers. No rsync
--delete is used. Retain prior source modifications separately before copying.

Create a NEW pending profile from existing private configuration, rather than
overwriting it or claiming unresolved checks are verified:

```sh
.venv-pi/bin/python - <<'PY'
import json
from pathlib import Path
base=Path.home()/'.config/trace-x'
v=json.loads((base/'motor-hardware.json').read_text())
v.update(firmware_version='0.6.0-protected-relays',electrical_limits_enabled=True,
         protection_limits_verified=False,operator_enable=False,
         supply_sensing={'location':'UPSTREAM_MOTOR_RELAY','verified':False},
         limits={'min_voltage':10.,'max_voltage':14.,'max_current':1.5})
v['relay'].update(active_level=0,inactive_level=1)
out=base/'motor-hardware.protected.pending.json'
with out.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
print(out)
PY
nano ~/.config/trace-x/runtime.env
```

In runtime.env choose the NEW absolute profile path, keep ADS_MODE=simulation
for legacy demos, set ADS_LIVE_PROTOCOL=ads_json and
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0. Keep ADS_HARDWARE_CONTROL_ENABLED=false during
commissioning. Restart and inspect:

```sh
systemctl --user restart trace-x.service
curl --fail http://127.0.0.1:13115/api/motor/hardware/status
journalctl --user -u trace-x.service -n 40 --no-pager
```

Open http://127.0.0.1:13115/ on the Pi LCD. Expect explicit blocked readiness
until real wiring/acceptance is complete. Selecting Motor/Circuit alone must
not switch power. This release does not enable runtime automatically.

For a raw READ-ONLY board inspection, stop the service to release serial, then:

```sh
systemctl --user stop trace-x.service
.venv-pi/bin/python - <<'PY'
import json
from diagnostic_platform.stm32 import STM32SerialConnection
c=STM32SerialConnection(port='/dev/ttyACM0',baud=115200,require_crc=True,allow_motor_control=False,command_timeout=1.)
try:
    c.connect()
    for command in ('GET_CAPABILITIES','GET_STATUS','READ_MEASUREMENTS'):
        print(command,json.dumps(c.execute(command),indent=2))
finally:c.disconnect()
PY
systemctl --user start trace-x.service
```

This sends no ARM, START, STOP or heartbeat. Check the firmware identity, both
sensor branches separately, voltage with relay open, output-disabled state,
active relay levels 0, electrical_limits_enabled=true, configured limits, and
unverified sensing/protection flags. A configuration flag is not physical proof.

## After physical commissioning (explicit operator work)

Record meter/calibration checks, relay reset/contact tests, physical cutoff and
communication-loss/timeout tests. Only then mark the NEW private Pi profile's
protection_limits_verified, supply_sensing.verified and operator_enable true.
Keep fixed_pwm_percent=50, max_duration_ms=30000 and the existing actual USB
identity/evidence. Existing flags must correspond to real checks, not assumed
approval. Do not alter the current private profile automatically.

Firmware enablement is a separate deliberate step: create ignored
`ADS/bench/commissioned.local.h` with the reviewed board profile and the existing
relay/kill/communication/calibration acceptance flags, plus:

```c
#define ADS_MOTOR_OPERATING_MODE 1
#define ADS_PHYSICAL_OUTPUT_ENABLED 1
#define ADS_SUPERVISED_TESTING_APPROVED 1
#define ADS_PROTECTION_LIMITS_VERIFIED 1
#define ADS_MOTOR_SUPPLY_SENSING_UPSTREAM_VERIFIED 1
```

Set the remaining acceptance flags only from bench evidence. To permit circuit
power separately, its CIRCUIT_OUTPUT_ENABLED and CIRCUIT_RELAY_VERIFIED gates
also need explicit approval. Build via:

```sh
make -C ADS OUT=../build/stm32-commissioned-protected BENCH_PROFILE=bench/commissioned.local.h -j4
```

Select that exact ELF manually in a separate CubeIDE debug configuration; the
Protected Disabled launch deliberately never substitutes it. Reflash manually
with branch power disconnected. Only after matching firmware/profile acceptance
should the operator set ADS_HARDWARE_CONTROL_ENABLED=true in runtime.env and
restart. Motor > Check hardware is read-only. Start at the approved duty with a
short duration and verify Stop/timeout/cutoff before a full 30-second run.

## Unresolved physical requirements

- Confirm/move motor INA219 upstream of the relay; calibrate against a reference.
- Physically verify COM–LOW relay release/startup/reset and the 3.3 V interface.
- No relay auxiliary-contact/load-bus feedback is installed/verified. Firmware
  cannot detect a welded contact or a failed coil from a GPIO acknowledgment.
  Add suitable isolated/scaled feedback with separately reviewed pin mapping if
  positive contact-state verification is required. Never connect 12 V to GPIO.
- Verify 1.5 A cutoff response and 10/14 V boundaries with controlled equipment;
  no trip curve or hardware protection rating was measured here.
- Validate encoder scaling and circuit probe/calibration workflow. Temperature
  remains retired. Physical motor/circuit operation and LCD touch are untested here.

Automated relay-failure checks inject rejected starts/unconfirmed stops. They
prove fail-closed software handling, not detection of an uninstrumented contact.

## Final software verification

- 218 tests passed in 26.728 seconds; no physical transport used.
- ARM GCC protected-disabled build passed: text 31448 / data 92 / BSS 19644 bytes.
- Generic default-disabled build passed: text 31380 / data 92 / BSS 19644 bytes.
- Production TypeScript/Vite build and ESLint passed; existing large-chunk advisory remains.
- Whitespace check passed with firmware CRLF accounted for.
- Source-only upgrade test confirms baseline/database/recording/env/workspace/local-header exclusion and original files unchanged.
- Physical sensor calibration, relay contacts/reset, trip latency, actual flashed image and Pi/LCD operation remain unverified.

## Modified or created implementation files

This aggregate list includes the previously pending active-LOW relay work retained
in this update. Local IDE preferences, old launch editor state, the main.h comment
and workspace contents were preserved and are excluded from this list.

- `.env.example`
- `.gitignore`
- `ADS/.cproject`
- `ADS/ADS Active Low Relays.launch`
- `ADS/ADS Protected Disabled.launch`
- `ADS/Core/Inc/ads_board_config.h`
- `ADS/Core/Inc/ads_circuit_relay.h`
- `ADS/Core/Inc/ads_motor.h`
- `ADS/Core/Inc/ads_protection.h`
- `ADS/Core/Src/ads_circuit_relay.c`
- `ADS/Core/Src/ads_motor.c`
- `ADS/Core/Src/ads_protection.c`
- `ADS/Core/Src/ads_protocol.c`
- `ADS/Core/Src/ads_sensors.c`
- `ADS/Core/Src/main.c`
- `ADS/bench/protected.example.h`
- `ADS/bench/supervised.operator.h`
- `README.md`
- `api/main.py`
- `deploy/pi/build_bundle.py`
- `deploy/pi/hardware-profile.example.json`
- `deploy/pi/supervised-hardware-profile.example.json`
- `deploy/pi/supervised-operator-profile.json`
- `diagnostic_platform/automated_engine.py`
- `diagnostic_platform/circuit_power.py`
- `diagnostic_platform/config.py`
- `diagnostic_platform/hardware_runtime.py`
- `docs/ACTIVE_LOW_RELAY_UPDATE.md`
- `docs/BRANCH_POWER_UPDATE.md`
- `docs/MOTOR_PROTECTION_LIMITS.md`
- `docs/PROTECTED_HARDWARE_INTEGRATION.md`
- `docs/STM32_PI_AUTOMATED_RUNTIME.md`
- `docs/SUPERVISED_OPERATOR_BUILD.md`
- `frontend/src/HardwareMotorControls.tsx`
- `frontend/src/api.ts`
- `tests/active_low_relays_harness.c`
- `tests/bounded_output_harness.c`
- `tests/power_feedback_harness.c`
- `tests/protection_harness.c`
- `tests/test_bounded_motor.py`
- `tests/test_branch_power.py`
- `tests/test_deployment.py`
- `tests/test_hardware_runtime.py`
- `tests/test_motor_dashboard_integration.py`
- `tests/test_operator_motor_build.py`
- `tests/test_protection.py`
- `tests/test_supervised_mode.py`
