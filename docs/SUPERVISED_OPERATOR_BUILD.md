> Superseded: use [PROTECTED_HARDWARE_INTEGRATION.md](PROTECTED_HARDWARE_INTEGRATION.md). Version 0.6.0 restores electrical protection and requires verified upstream sensing; default outputs are disabled.

> Current behavior: motor voltage/current cutoffs were removed at the operator's request. Use [BRANCH_POWER_UPDATE.md](BRANCH_POWER_UPDATE.md) for firmware 0.5.2, matching Pi profile migration, flashing and deployment. Older threshold statements below describe earlier versions.

# Supervised motor-enabled build — November 11, 2026

The operator explicitly confirmed relay/reset behavior, physical cutoff,
updated firmware communication-loss shutdown and motor INA219 reference
measurement checks, then requested an enabled build. Those attestations are
recorded in `ADS/bench/supervised.operator.h` and
`deploy/pi/supervised-operator-profile.json`. They are not independent physical
verification by the coding agent. No board was flashed, reset or run here.

The operator profile enables physical permission, supervised approval, relay
safe output, physical cutoff, communication stop and motor electrical
calibration acceptance. `ADS_BOARD_ACCEPTED` is true for this profile. Generic
Makefile defaults and the supervised example remain output-disabled.

Mode is SUPERVISED_TEST; PC8 feedback is not required or claimed installed.
Current cutoff is 1.5 A, supply window 10–14 V (operator-confirmed).
Fixed PWM is 50%, maximum duration 30 seconds. Boot remains stopped. The
enabled build still requires per-run operator confirmation, valid motor sensor
readings, explicit ARM/START, and the existing deadline/heartbeat protections.
PB4 and circuit measurements remain independent of motor control.

Build without flashing:

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
make -C ADS OUT=../build/stm32-supervised-enabled BENCH_PROFILE=bench/supervised.operator.h -j4
```

The build produces `build/stm32-supervised-enabled/ADS.elf`, with HEX, BIN,
SHA-256 and manifest files. Do not select the previous pending-acceptance image.

CubeIDE project: `ADS/.project`. Both Debug and Release explicitly define
`ADS_USE_OPERATOR_PROFILE=1`; ads_board_config.h then includes the same operator
profile. Reload files from disk/refresh the project and clean/rebuild if using
the managed build. Do not overwrite settings from an old editor buffer. The
CubeIDE managed build was configured but was not executed here; the ARM
Makefile build was executed.

For the exact prebuilt image, choose **ADS Supervised Enabled** from
`ADS/ADS Supervised Enabled.launch`. It selects the enabled ELF with automatic
build substitution disabled. Launching it will flash/reset the board and is an
operator action. Alternatively select the ELF directly in STM32CubeProgrammer.
Keep motor power disconnected while flashing and inspecting initial status.

## Raspberry Pi configuration

In the updated Pi repository:

```sh
cd "$HOME/Trace-X"
systemctl --user stop trace-x.service
.venv-pi/bin/python -m serial.tools.list_ports -v
mkdir -p "$HOME/.config/trace-x"
cp deploy/pi/supervised-operator-profile.json "$HOME/.config/trace-x/motor-hardware.json"
nano "$HOME/.config/trace-x/motor-hardware.json"
```

Set serial_identity to the actual ST-LINK USB serial number from list_ports,
not `/dev/ttyACM0`. This field is deliberately blank; no identity was guessed.
Evidence/calibration labels identify operator-reported checks, not laboratory
certificates. Set these entries in `~/.config/trace-x/runtime.env`, preserving
other settings:

```dotenv
ADS_AUTOMATION_HARDWARE_PROFILE=/home/amirzoom8/.config/trace-x/motor-hardware.json
ADS_LIVE_PROTOCOL=ads_json
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0
```

Validate the completed profile and restart:

```sh
.venv-pi/bin/python -c 'from pathlib import Path; from diagnostic_platform.automated_engine import load_hardware_profile; p=load_hardware_profile(Path.home()/".config/trace-x/motor-hardware.json"); print(p["operating_mode"], p["limits"])'
systemctl --user restart trace-x.service
curl -s http://127.0.0.1:13115/api/motor/hardware/status
```

Expect profile_ready=true and SUPERVISED_TEST. This endpoint validates the Pi
profile; the run precheck also checks actual STM32 identity/capabilities,
matching limits/mode and fresh readings. The generic verify_stm32 utility
expects output-disabled firmware; its output-disable assertion is not a success
criterion for this enabled image.

## First dashboard run

The motor INA219 must read 10–14 V while the relay is off. If placement
downstream of the relay gives zero voltage, precheck still rejects starts;
this build does not energize the relay to bypass that check.

With the cutoff accessible, select hardware motor control, confirm supervision,
choose 50% PWM and a short duration within 30 seconds, then press Start Motor.
Check actual readings and requested/applied PWM. Stop should report stopped and
applied PWM zero. Software checks do not establish actual shaft motion/contact
opening. Encoder scaling remains provisional; temperature remains disabled.

Verification: ARM GCC build passed (text 30048, data 92, BSS 19532 bytes).
All 176 tests passed, including actual operator-profile fake-GPIO shutdown tests
through both Makefile and CubeIDE configuration routes. No layout or simulation
changes were made. No GitHub push or hardware operation was performed.
