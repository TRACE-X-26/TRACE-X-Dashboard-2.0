# Dual INA219 integration — November 6, 2026

November 9 operating-mode update: [normal PC8 feedback and explicit supervised testing](SUPERVISED_MOTOR_TESTING.md), firmware 0.5.0-supervised-motor. Earlier hashes and mode requirements below are historical.

Current firmware: `0.4.2-dual-ina219`. This extends the existing ADS project and
ADS v1 framing; the older standalone main.c was not substituted. No board was
flashed, connected for programming, or physically operated during this work.
Motor output remains disabled by the existing unresolved protection gates.

## Wiring and independent acquisition

Both modules share existing I2C1 PB8/SCL and PB9/SDA. MOTOR uses 7-bit 0x40;
CIRCUIT uses 7-bit 0x41 with A0 bridged, as supplied by the operator. Both shunts
are R100 / 0.1 ohm (100 milliohms). The HAL adapter shifts the address once:
0x40 -> 0x80, 0x41 -> 0x82. No Raspberry Pi I2C connection is used; the STM32
owns these devices and the Pi receives USB serial telemetry.

The new reusable ads_ina219 driver has a separate instance per address, including
presence, configuration, pending conversion, sequence, timestamps, calibration,
status and cache. Each instance probes its own address and writes its own
triggered shunt+bus configuration (0x399B) at nominal 100 ms intervals. CNVR,
overflow and a bounded conversion/read interval are checked before accepting a
held bus/shunt pair. Voltage is V, current is A, and power is V * A, calculated
from that sensor's own held pair. The INA219 conversions are sequential, not
truly simultaneous across channels or across the two modules. Existing fixed
point telemetry has 1 mA current reporting resolution; bench calibration remains
unverified for both modules despite the confirmed nominal shunt markings.

A missing address, failed configuration/read, overflow or timeout invalidates
only that instance. Status distinguishes NOT_INITIALIZED, CONNECTED,
NOT_CONNECTED, CONFIG_ERROR, READ_ERROR, CONVERSION_TIMEOUT, OVERFLOW and STALE.
Connected means the address acknowledged; it does not imply a good conversion.
Failed values serialize as null with valid=false. A successful zero measurement
remains valid zero. Re-probing permits independent recovery. Stale cached values
are never promoted to fresh valid samples. Because the physical bus is shared,
a module holding SDA/SCL low can electrically block both; software cannot isolate
such a bus fault and will invalidate both if neither can be read.

The original motor measurements and acquisition metadata are populated exclusively
from the MOTOR instance. Circuit state does not feed ADS_Sensors_Ready, motor
current/voltage limits, or health inputs. The PB4 circuit relay is not actuated.
Circuit supply measurements are NOT test-point probe measurements and are not
automatically assigned to a circuit asset or used as TP0–TP4 captures.

The larger response uses foreground-owned static buffers within the MCU RAM
budget. USART transmission services acquisition and motor polling between
24-byte chunks, so full telemetry transmission does not monopolize the foreground
longer than the conversion-polling deadline. SysTick motor shutdown and the
independent watchdog remain in place. UART errors still latch motor shutdown.
No nested command processing occurs during transmission.

## ADS v1 response

The existing result.measurements voltage/current/power/temperature/rpm fields
remain unchanged. An additive result.ina219 object contains MOTOR and CIRCUIT:

```json
{
  "ina219": {
    "MOTOR": {
      "address": 64,
      "connected": true,
      "configured": true,
      "status": "CONNECTED",
      "valid": true,
      "calibrated": false,
      "sequence": 12,
      "started_ms": 1200,
      "timestamp_ms": 1203,
      "measurements": {
        "voltage": {"value": 12.0, "unit": "V", "valid": true, "timestamp_ms": 1203},
        "current": {"value": 0.1, "unit": "A", "valid": true, "timestamp_ms": 1203},
        "power": {"value": 1.2, "unit": "W", "valid": true, "timestamp_ms": 1203}
      }
    },
    "CIRCUIT": {
      "address": 65,
      "connected": false,
      "configured": false,
      "status": "NOT_CONNECTED",
      "valid": false,
      "calibrated": false,
      "sequence": 12,
      "started_ms": 1204,
      "timestamp_ms": 1207,
      "measurements": {
        "voltage": {"value": null, "unit": "V", "valid": false, "timestamp_ms": 1207},
        "current": {"value": null, "unit": "A", "valid": false, "timestamp_ms": 1207},
        "power": {"value": null, "unit": "W", "valid": false, "timestamp_ms": 1207}
      }
    }
  }
}
```

This is an illustrative result fragment, not a hardware capture. The existing
version/type/seq/device_id/timestamp_ms/payload.reply_to envelope and CRC32 trailer
are preserved. GET_CAPABILITIES advertises the two 7-bit addresses. Historical
JSON and plain-text monitoring remain supported; absent circuit data is explicitly
NOT_REPORTED rather than copied from the motor.

## Backend, dashboard and logging

normalize_branches independently validates each branch's address, flags, units,
finite values and timestamps. A malformed circuit branch is displayed as
MALFORMED with null/invalid values while motor processing remains separate.
Actual serial measurements are published to /api/live/status and /ws/live under
ina219.MOTOR and ina219.CIRCUIT. The STM32 sensors page displays both labeled
branches with status, values, calibration, acquisition time and stale handling.
The hardware motor panel also displays both during a run. Existing graphs,
simulation controls and circuit capture workflows are retained.

An opt-in read-only SensorMonitor sends READ_MEASUREMENTS only. It neither arms
nor starts the motor nor sends heartbeats to keep an unknown run alive. It shares
the automated engine's serial ownership mutex and skips polling while a motor
run owns the device. The device's exclusive serial open remains enforced. An
operator start racing a short read may receive a busy rejection and can retry
with a fresh action; actuation is never retried automatically. Passive mode is
still the default for old plain-text firmware.

Read-only monitoring automatically writes long-form CSVs under <database
folder>/sensor_csv/. They retain MOTOR/CIRCUIT labels, addresses, connection/status,
validity, calibration and STM32 timestamps, including invalid/null sensor rows.
The existing collector produces the same labeled CSV schema. Automated motor
runs retain raw dual-sensor frames in SQLite and add circuit-prefixed columns
and both statuses/validity/timestamps to the existing run CSV. Existing
voltage_V/current_A/power_W columns remain MOTOR for compatibility. A circuit
failure or high circuit current never causes a motor current fault.

## Build, flash and verify on the hardware

On the development Mac:

```sh
cd "/Users/markussanford/Documents/ChatGPT/Capstone"
make -C ADS -j4
```

Flash the complete build/stm32-default-disabled/ADS.elf using the operator-owned
CubeIDE/CubeProgrammer procedure in DASHBOARD_MOTOR_CONTROL.md, with external
motor energy disconnected. The updated image does not enable motor operation.
Use only this repository's project and newly built image, not the older ADS/Debug
ELF. If using CubeIDE's managed build, include the new ads_ina219.c source.

On the Raspberry Pi after installing the updated package:

```sh
cd "$HOME/Trace-X"
bash deploy/pi/install.sh
systemctl --user stop trace-x.service
ls -l /dev/serial/by-id/
.venv-pi/bin/python -m diagnostic_platform.verify_ina219 --port /dev/ttyACM0 --samples 5
```

Use the actual serial path. With both sensor logic supplies present, the verifier
must report address 64 for MOTOR, address 65 for CIRCUIT, connected=true and valid
samples for each. Zero bus voltage/current can be correct with load power off;
that is separate from the I2C address responding. The verifier sends only
GET_CAPABILITIES and READ_MEASUREMENTS. It exits nonzero if either branch fails.
It reports actual returned values but does not certify calibration or protection.

To display both sensors without permitting motor commands, edit the existing
user-service environment:

```sh
nano "$HOME/.config/trace-x/runtime.env"
```

Set (after flashing the matching request/response firmware):

```dotenv
ADS_LIVE_PROTOCOL=ads_json
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0
```

No commissioned motor profile is required for this read-only mode. Leave the
motor profile unset unless separately commissioning motor commands. If a motor
profile is already configured, the read-only poller shares ownership with its
engine. Do not run the verifier or collector alongside the dashboard service.

```sh
systemctl --user restart trace-x.service
curl -s http://127.0.0.1:13115/api/live/status
journalctl --user -u trace-x.service -n 50 --no-pager
```

Open http://127.0.0.1:13115/ -> STM32 sensors -> INA219 branch measurements.
Compare the circuit and motor values against independent references at their
own branch. With power off before rewiring, disconnect one sensor at a time,
then reapply sensor logic power and verify that its status/readings invalidate
while the other remains correct. Reconnect and confirm recovery. Do not hot-wire
I2C, change the A0 bridge while powered, or use Pi i2cdetect on this STM32-owned
bus. Repeat with a known current-limited load per branch to check separate
current/power changes and polarity. Those physical checks remain unperformed.

Optional standalone CSV capture (dashboard service stopped):

```sh
.venv-pi/bin/python -m diagnostic_platform.collector --port /dev/ttyACM0 --crc32 --test-id dual-ina219 --directory data/experiments
```

Press Ctrl+C before restarting the dashboard service. The current motor-control
commissioning blockers remain as documented; this sensor update does not bypass
them or turn on the circuit relay.

## Changed files in this increment

- ADS/Core/Inc/ads_ina219.h and ADS/Core/Src/ads_ina219.c (new): reusable independent acquisition.
- ADS/Core/Inc/ads_board_config.h: circuit address/shunt/calibration configuration.
- ADS/Core/Inc/ads_sensors.h and ADS/Core/Src/ads_sensors.c: two driver instances, motor-only protection cache.
- ADS/Core/Inc/ads_protocol.h and ADS/Core/Src/ads_protocol.c: branch callback and additive ADS telemetry.
- ADS/Core/Src/main.c: branch callback registration and responsive serial transmission.
- diagnostic_platform/ina219.py (new): branch normalization.
- diagnostic_platform/sensor_monitor.py (new): opt-in read-only polling/logging.
- diagnostic_platform/verify_ina219.py (new): address/status/reading verifier.
- diagnostic_platform/live.py: independent branch state and stale handling.
- diagnostic_platform/automated_engine.py: shared read ownership and branch publication.
- diagnostic_platform/collector.py and diagnostic_platform/motor_csv.py: dual-branch CSVs.
- api/main.py: monitor lifecycle and circuit acquisition capability description.
- frontend/src/INA219Readings.tsx (new), LiveSensors.tsx, HardwareMotorControls.tsx, types.ts: labeled branch displays.
- .env.example and deploy/pi/hardware-profile.example.json: opt-in polling and firmware identity.
- tests/dual_ina219_harness.c and tests/test_dual_ina219.py (new): driver/protocol/backend regressions.
- README.md, docs/DASHBOARD_MOTOR_CONTROL.md, docs/FULL_INTEGRATION_FILES.md and this guide: current handoff pointers.

Software test/build results and artifact checksums follow after final verification.

Final verification:

- Full Python/protocol/backend/API suite: 163 tests passed (12.362 seconds).
- Includes actual C dual-INA219 driver/protocol harness, each address's independent
  failure/recovery, zero and negative current, conversion timeout/overflow/read
  error, separate CSV values, motor-protection isolation, read-only ownership,
  and live API/WebSocket publication.
- NUCLEO-F401RE ARM GCC target build passed: text 28728, data 92, BSS 19524 bytes.
- Frontend TypeScript/Vite build and ESLint passed. Existing bundle-size advisory
  remains (654.33 kB JavaScript, 194.07 kB gzip).
- CRLF-aware Git whitespace check passed.
- No physical sensor measurements, flashing or powered motor test performed.
- An older open editor copy had restored ads_board_config.h during development.
  The operator identified that editor; final build/tests checked the configuration
  fingerprint remained unchanged. Reload from disk rather than save that old copy.

Firmware SHA-256: `14d324de99c979218c0f3a8d20177287666378425a051c15599430b9cfff80cc`.
The .elf.sha256 and .elf.manifest.json files sit alongside the image. The manifest
records the board configuration fingerprint and disabled output permission.
The refreshed Pi package is deliverables/Trace-X-Pi.zip, with a checksum alongside.
Source publication branch: TRACE-X-26/Dashboard, trace-x-integration-2026-10-30. Generated firmware and Pi ZIP artifacts remain local and Git-ignored.

GitHub reconciliation: the newer archive-replay and live-readout commit was
merged without replacing its features. Passive and legacy json modes remain;
ads_json uses the CRC-protected shared-ownership reader. After resolving the
merge, all 166 tests passed (20.048 seconds), and the frontend build and lint
passed (656.77 kB JavaScript, 194.64 kB gzip; existing size advisory). Firmware
sources and the verified ELF were unchanged by this merge.
