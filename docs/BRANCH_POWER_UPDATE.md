> Current sensor placement is downstream of the relays. Use [DOWNSTREAM_SENSOR_INTEGRATION.md](DOWNSTREAM_SENSOR_INTEGRATION.md) and firmware 0.7.0. No upstream relocation is required for the bounded zero-PWM power-check sequence.

> Superseded: use [PROTECTED_HARDWARE_INTEGRATION.md](PROTECTED_HARDWARE_INTEGRATION.md). Version 0.6.0 restores electrical protection and requires verified upstream sensing; default outputs are disabled.

> Both jumpers are now COM–LOW. Use [ACTIVE_LOW_RELAY_UPDATE.md](ACTIVE_LOW_RELAY_UPDATE.md) and firmware 0.5.3. HIGH-trigger statements below describe the preceding build.

# Motor/circuit selection and electrical telemetry update

Current firmware identity: **0.5.2-electrical-telemetry**.
This document supersedes older 10–14 V / 1.5 A motor-start instructions.

## Behavior

The Test station is the dashboard home page. Select Motor or Circuit, then
press Start Motor or Circuit Power On. Selection sends no serial/GPIO command.
Existing overview, simulation, recordings, baselines, diagnostics and history
remain under Advanced tools. The existing responsive/touch CSS remains in use.

One two-channel relay board has independent outputs:

| Branch | STM32 control | Relay channel | Sensor |
|---|---|---|---|
| Motor | D4 / PB5 | IN1, motor switched branch | unbridged INA219 0x40 |
| Circuit | D5 / PB4 | IN2, COM2–NO2 circuit supply | A0-bridged INA219 0x41 |

The operator confirmed active HIGH / inactive LOW and a physical cutoff covering
both branches. Direction D7/PA8, PWM D6/PB10 TIM2 CH3, encoder A D12/PA6 and
encoder B D9/PC7 remain unchanged. Separate relay channels do not select which
sensor is read: both INA219s remain independent on the I2C bus.

At the operator's request, motor voltage/current values are **telemetry only**.
There is no numeric software undervoltage, overvoltage or overcurrent cutoff
in the motor firmware or hardware backend. Zero voltage/current are accepted
when the acquisition is valid and fresh. Connected-but-invalid, stale, overflow
or failed conversions still block/stop a run. The physical motor still needs
adequate power; acknowledged relay/PWM settings are not evidence of rotation.

Firmware capabilities and the Pi profile must both report
`electrical_limits_enabled: false`. The old protection-limits verification flag
and numeric limits are removed from the shipped physical profiles. Simulation
fault examples and baseline/health comparisons retain their separate behavior.
Old firmware/profile mismatches reject a start rather than silently mixing
policies. Existing calibration, relay/cutoff acceptance, explicit per-run
supervision, normal-mode feedback, fixed approved PWM, 30-second deadline,
heartbeat loss shutdown, cancellation and fault lockout remain enforced.
Generic Makefile defaults disable both physical outputs. The explicitly
selected supervised operator build permits outputs, but boots stopped.

Motor and circuit operations share backend serial ownership. Firmware readiness
also rejects arming one branch while the other is armed/running. Circuit power
uses its own bounded controller and never applies motor PWM. Circuit power is
manual supervised supply switching, not an automatic circuit fault diagnosis or
calibrated health score. No circuit current cutoff has been invented.

## Serial and API

USART2/ST-LINK, 115200 baud 8-N-1, ADS v1 with CRC32 and reply_to correlation.
The motor ARM_TEST / SET_PWM / START_TEST / STOP_TEST / EMERGENCY_STOP path is
retained. Circuit commands use the same request/ack envelope:

```json
{"command":"ARM_CIRCUIT","arguments":{"supervised_confirmed":true}}
{"command":"START_CIRCUIT","arguments":{"duration_ms":30000}}
{"command":"GET_CIRCUIT_STATUS","arguments":{}}
{"command":"STOP_CIRCUIT","arguments":{}}
```

These are payload examples, not complete CRC-framed USB messages. The serial
adapter supplies device identity, request sequence and framing. A circuit ack
reports accepted/reason, branch, state, power_on (commanded), last_control_seq,
run_id, started_ms, stopped_ms and stop_reason. physical_power_verified is false.
Repeated START cannot restart/extend an operation; repeated STOP is safe.
A fresh heartbeat and explicit supervised ARM are required after a fault.
Both branch acquisition statuses, validity, units, timestamps and calibration
metadata remain separate. Circuit power sessions and samples use additive SQLite
tables and downloadable CSVs; existing motor logs/recordings/baselines are kept.

- GET `/api/station/status`: selected branch and current sessions; no actuation.
- POST `/api/station/select` with `{"branch":"CIRCUIT"}`: software selection only.
- POST `/api/station/circuit/power` with `{"on":true,"duration_ms":1000,"supervised_confirmed":true}`: explicit power request.
- POST same route with `{"on":false}`: request stop, followed by ack verification.
- GET `/api/station/circuit/{session_id}/csv`: separate circuit acquisition log.

No CLI shown below automatically sends a physical START or switches hardware
runtime permission on.

## Update an existing Raspberry Pi installation

With physical branch power off, stop the backend before changing code. Do not
replace the database, recordings, baseline directories or the entire private
hardware profile with an example.

```sh
cd /home/amirzoom8/Trace-X
systemctl --user stop trace-x.service
git status --short
git switch trace-x-integration-2026-10-30
git pull --ff-only origin trace-x-integration-2026-10-30
.venv-pi/bin/python -m pip install -r requirements-backend.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

If Git reports local changes or a divergent branch, resolve those before
continuing; do not reset away local data/configuration. Keep the serial identity
and existing commissioning evidence in `~/.config/trace-x/motor-hardware.json`.
After reviewing the new telemetry-only policy, migrate just these fields (backs
up the original profile, and deliberately does not enable hardware runtime):

```sh
.venv-pi/bin/python - <<'PY'
import json, shutil
from pathlib import Path
from datetime import datetime
p=Path.home()/'.config/trace-x/motor-hardware.json'
v=json.loads(p.read_text())
shutil.copy2(p,p.with_name('motor-hardware.'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.bak.json'))
v['firmware_version']='0.5.2-electrical-telemetry'
v['electrical_limits_enabled']=False
v['circuit_power_approved']=True # operator confirmed D5/IN2, HIGH on/LOW off, common cutoff
for key in ('limits','protection_limits_verified','protection_limits_verification'):
    v.pop(key,None)
p.write_text(json.dumps(v,indent=2)+'\n')
PY
```

Review `~/.config/trace-x/runtime.env`: keep `ADS_MODE=simulation` for the legacy
simulation controls, `ADS_LIVE_PROTOCOL=ads_json`, `ADS_LIVE_SERIAL_PORT=/dev/ttyACM0`
and the existing absolute `ADS_AUTOMATION_HARDWARE_PROFILE` path. The separate
hardware runtime remains opt-in via `ADS_HARDWARE_CONTROL_ENABLED=true`; enable
that only as the operator's deliberate configuration step. This update does not
set it automatically. Then:

```sh
systemctl --user restart trace-x.service
curl --fail http://127.0.0.1:13115/api/station/status
curl --fail http://127.0.0.1:13115/api/motor/hardware/status
journalctl --user -u trace-x.service -n 30 --no-pager
```

Open **http://127.0.0.1:13115/** on the Pi. Motor -> Check hardware is read-only.
Neither checking hardware nor choosing a branch should energize a relay.
A previous 0.036 V acquisition no longer fails a numeric voltage check, provided
it is valid/fresh and the other explicit requirements pass. An older flashed
firmware can still enforce its former limits until reflashed.

## Firmware build and flash

On the development Mac, from the repository root:

```sh
make -C ADS -j4
make -C ADS OUT=../build/stm32-branch-enabled BENCH_PROFILE=bench/supervised.operator.h -j4
```

First command is the disabled build; second is the explicitly supervised build.
Open/import `ADS/.project` in STM32CubeIDE, refresh from disk, then use
**ADS Branch Power** (`ADS/ADS Branch Power.launch`) for the exact prebuilt
`build/stm32-branch-enabled/ADS.elf`. Automatic build substitution is disabled.
A clean managed CubeIDE Debug/Release build also uses ADS_USE_OPERATOR_PROFILE=1.
The old ADS Supervised Enabled launch references a separate earlier image:
use the new launch to avoid accidentally flashing that stale file.

The operator performs flashing, with motor/circuit power disconnected. Wait for
Download verified successfully, resume if halted at main, then terminate the
debug session before moving the USB connection to the Pi. A green/red LED alone
is not proof of matching firmware identity.

## Acceptance

Begin USB-only, external motor/circuit supply disconnected. Confirm the returned
firmware identity and electrical_limits_enabled=false with a read-only motor
hardware check. Confirm selecting either branch causes no relay command/output.
Check both independent INA219 connection/validity fields (calibration remains
explicit; circuit calibration is unverified). Do not press Start/Power On during
this USB-only stage: these controls are now allowed to accept valid zero values.

For the operator's subsequent powered bench test, begin with a short bounded
run, verify the chosen relay channel only, motor PWM/direction, sensor readings,
Stop, automatic deadline and physical cutoff. Test communication loss and fault
lockout under controlled conditions. Circuit sessions should also stop at the
deadline or on sensor failure and leave motor output off. A software relay-off
ack is not relay-contact feedback. Temperature is retired; RPM scaling remains
provisional. LCD touch and real relay timing require testing on the Pi/setup.

Software tests use only fake outputs/in-memory serial transports; no board was
flashed, reset or run by this update. Final checks: **212 tests passed** (25.138 s); TypeScript/Vite production
build and ESLint passed. ARM GCC builds passed for both disabled and explicit
supervised profiles. Enabled image: text 31556 / data 92 / BSS 19644 bytes;
disabled image: text 31052 / data 92 / BSS 19644 bytes. The existing frontend
large-chunk advisory remains non-fatal. Existing datasets are not retrained or overwritten.
