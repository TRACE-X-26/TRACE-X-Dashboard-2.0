> Current sensor placement is downstream of the relays. Use [DOWNSTREAM_SENSOR_INTEGRATION.md](DOWNSTREAM_SENSOR_INTEGRATION.md) and firmware 0.7.0. No upstream relocation is required for the bounded zero-PWM power-check sequence.

> Superseded: use [PROTECTED_HARDWARE_INTEGRATION.md](PROTECTED_HARDWARE_INTEGRATION.md). Version 0.6.0 restores electrical protection and requires verified upstream sensing; default outputs are disabled.

# COM-LOW relay firmware — 0.5.3-active-low-relays

The operator changed both relay trigger jumpers to COM–LOW and requested matching
firmware. This supersedes the COM–HIGH instructions in BRANCH_POWER_UPDATE.md.

| Output | Pin | Start/power ON | Boot/stop/fault OFF |
|---|---|---|---|
| Motor / IN1 | D4 / PB5 | LOW | HIGH |
| Circuit / IN2 | D5 / PB4 | LOW | HIGH |

Motor PWM remains D6/PB10 and direction D7/PA8. Sensor addresses, no voltage/current
cutoff policy, fixed 50% approved duty, 30-second deadline, heartbeat-loss stop,
fault lockout, operator confirmation and mutually exclusive branches are retained.
No automatic start on reset. The circuit status relay_command_high field now
reflects the electrical level: false while powered, true after stopping.
Capabilities advertise both relay active levels separately from power state.

The output latch is set inactive before configuring a relay pin as an output.
Firmware cannot control a pin while the STM32 is unpowered or held in reset.
Compatibility of a 3.3 V inactive HIGH with this 12 V relay module and its actual
reset/contact behavior still require a physical check; neither is established by
software tests or by the relay indicator. No board was flashed or run here.

## Build and flash on the Mac

From /Users/markussanford/Documents/ChatGPT/Capstone:

```sh
make -C ADS OUT=../build/stm32-active-low-enabled BENCH_PROFILE=bench/supervised.operator.h -j4
```

New image: `build/stm32-active-low-enabled/ADS.elf` (HEX/BIN also provided locally).
In STM32CubeIDE refresh ADS, then select **ADS Active Low Relays** from
`ADS/ADS Active Low Relays.launch`. This selects the exact new image without
automatic build substitution. The older Branch Power/Supervised Enabled launch
files can still select older opposite-polarity binaries: do not use them for
COM–LOW wiring. Managed Debug/Release builds use the current operator profile;
clean/rebuild the entire project, including ads_circuit_relay.c.

Keep external motor/circuit power disconnected while flashing. Wait for
Download verified successfully, Resume if halted at main, then terminate the
debug session. With USB only, verify both D4 and D5 are approximately 3.3 V
relative to STM32 ground while stopped. This verifies MCU signal levels only.
For powered commissioning, first keep branch loads disconnected and verify
both relay channels stay released at startup and on Stop; only reconnect loads
with power off. Actual contact release must be confirmed before a motor test.

Generic `make -C ADS` still produces the output-disabled profile.

## Raspberry Pi profile

Updated profile templates contain firmware_version=0.5.3-active-low-relays,
relay.active_level=0 / inactive_level=1 and matching circuit_relay metadata.
The existing Pi backend uses firmware identity to reject an old/mismatched
profile. Preserve USB identity, calibration evidence and other commissioning
settings. With the backend stopped, migrate only the changed fields:

```sh
cd /home/amirzoom8/Trace-X
systemctl --user stop trace-x.service
.venv-pi/bin/python - <<'PY'
import json, shutil
from datetime import datetime
from pathlib import Path
p=Path.home()/'.config/trace-x/motor-hardware.json'
v=json.loads(p.read_text())
shutil.copy2(p,p.with_name('motor-hardware.'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.bak.json'))
v['firmware_version']='0.5.3-active-low-relays'
v['relay'].update(active_level=0,inactive_level=1,trigger_jumper='COM-LOW')
v['circuit_relay']={'pin':'PB4','active_level':0,'inactive_level':1,'trigger_jumper':'COM-LOW'}
p.write_text(json.dumps(v,indent=2)+'\n')
PY
systemctl --user restart trace-x.service
```

This migration assumes the previous 0.5.2 telemetry-only backend/profile is
already installed. It does not enable hardware permission, alter numeric policy,
start a motor, or change the dashboard layout. Use the dashboard's read-only
Check hardware before an explicitly authorized short test. Both relay jumpers
must remain COM–LOW for this image.

## Changed source files

- ADS/Core/Inc/ads_motor.h: motor default polarity LOW/active, HIGH/inactive.
- ADS/Core/Inc/ads_board_config.h: explicit circuit relay polarity constants.
- ADS/Core/Inc/ads_circuit_relay.h and ADS/Core/Src/ads_circuit_relay.c:
  isolated, testable circuit GPIO preload/init/on/off functions.
- ADS/Core/Src/main.c: use the shared circuit driver for boot/start/all stops.
- ADS/Core/Src/ads_protocol.c: firmware identity, capability levels, accurate pin status.
- ADS/bench/supervised.operator.h: updated jumper description.
- ADS/ADS Active Low Relays.launch: select the new image.
- deploy/pi/*profile*.json: matching identity and polarity metadata.
- tests/active_low_relays_harness.c, tests/test_operator_motor_build.py,
  tests/test_bounded_motor.py: actual GPIO and protocol regression coverage.
- tests/test_hardware_runtime.py and tests/test_supervised_mode.py: matching peer identity.


Verification: **214 tests passed** (26.648 s), including both actual relay drivers
against fake GPIO for Makefile/CubeIDE profiles, boot preloads, cancellation,
normal deadline, fault and heartbeat stops, plus protocol pin-state checks.
ARM GCC enabled build passed: text 31676 / data 92 / BSS 19644 bytes.
Disabled build passed: text 31152 / data 92 / BSS 19644 bytes.
Whitespace check passed. Dashboard files were not changed.
