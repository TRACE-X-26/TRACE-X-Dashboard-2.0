# Actual STM32 motor readings without changing firmware

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

Implemented November 2, 2026 against the operator-supplied serial format. No files under `ADS/` were changed and no board was flashed or operated. The current firmware can keep sending human-readable text; Python normalizes it for React.

## Data flow

```text
STM32 existing UART text, 115200 8-N-1
    → Pi's exclusive, read-only serial reader
    → bounded line decoder and motor-cycle parser
    → structured sample with source=stm32_serial
    → GET /api/live/motor, GET /api/live/status, WebSocket /ws/live
    → existing STM32 sensors page, actual motor measurement tiles
```

Required cycle fields are:

```text
ENCODER: NO PULSES DETECTED
Motor RPM: 0
INA219: CONNECTED
Voltage: 0.004 V
Current: 0.000 A
Power: 0.000 W
```

`ENCODER: PULSES DETECTED` is also recognized. Each cycle starts at an encoder-status line and must contain each required field once within three seconds. A repeated field restarts incomplete assembly; values before the encoder boundary or from a previous cycle are never used to fill gaps. Missing fields are not invented and power is the firmware's reported W value, not V×I from different text lines. Zero is a valid observation; zero RPM does not imply a stall when commanded motor state is unknown. Signed RPM/current are preserved.

Malformed numbers, wrong units, non-finite values, disconnected sensor status, resets, incomplete cycles, oversized lines and invalid UTF-8 are handled explicitly. Corrupt byte chunks are discarded conservatively. Fragmented reads and CRLF lines are supported. A failed sensor invalidates the complete motor sample. Previously completed readings are marked stale after three seconds or serial disconnection; main tiles show a dash when unavailable/stale, while the observation table retains separately timestamped partial data where available.

Host receipt time and receive-cycle association do **not** prove simultaneous acquisition or calibrated sensor accuracy. Samples retain UTC receipt timestamp, first receive time, receive span, status strings, format, `source=stm32_serial`, connection and quality metadata. Firmware calibration/encoder CPR are still unverified. Temperature is optional and not part of the six-field motor cycle.

Existing ADS JSON measurement envelopes and flat motor JSON fields remain supported; request/response JSON verification is still available explicitly. Circuit messages remain in a separate namespace. Simulation APIs are unchanged and never feed this live receiver.

## Install/update on the Raspberry Pi

First copy the updated project files to the Pi. These commands assume the updated source is at the operator-provided path below. Changes are local to the Mac until transferred or explicitly committed/pushed; pulling the old GitHub commit will not obtain this new receiver. Preserve the Pi's existing database and `~/.config/trace-x/runtime.env` when updating. A full transfer ZIP should be extracted to a new folder first, not over active data.

```sh
cd /home/amirzoom8/intelligent-diagnostic-system/dashboard/Dashboard-trace-x-integration-2026-10-30
python3 -m venv .venv-pi
.venv-pi/bin/python -m pip install -r requirements-backend.txt
cd frontend
npm ci
npm run build
cd ..
```

Python 3 with venv and Node.js compatible with the current Vite version are needed. If missing on Debian 13:

```sh
sudo apt update
sudo apt install python3-venv python3-pip nodejs npm chromium curl
```

Do not copy a Mac virtual environment or Mac node_modules. Initial dependency installation needs internet; the built local dashboard does not.

## Verify the actual text connection

Connect the STM32 ST-LINK USB interface to the Pi. Stop terminal programs/collectors and the backend before checking the port. If the Trace-X user service is installed:

```sh
systemctl --user stop trace-x.service
```

Also stop a manually launched backend with Ctrl+C in its terminal. Prefer the verified `/dev/serial/by-id/…` path if available. The following uses the reported `/dev/ttyACM0`:

```sh
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port /dev/ttyACM0 --baud 115200 --timeout 8
```

Expected: `STM32 CONNECTION TEST: PASSED`, `format: plain_text`, `commands_sent: false`, and the real `motor_sample` with source `stm32_serial`. The example 0.004 V / 0 A / 0 W / 0 RPM must remain exactly those observed values; they do not establish that the motor is running or healthy. No commands are transmitted in default auto/passive mode. Verification reports hardware safety as unverified; it does not infer a safe motor state from receiving data.

For explicit plain-text-only checking, add `--protocol plain-text`. If using the other JSON request/response firmware instead, run:

```sh
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port /dev/ttyACM0 --protocol json
```

Only this explicit JSON option sends the existing status/capability/fault/heartbeat checks. It does not send motor commands. Passive auto can also recognize unsolicited ADS JSON. Silent request/response firmware will time out in passive mode, with instructions to select JSON mode.

If opening the device is denied, check serial-group membership and existing readers. Grant access through the OS rather than running the whole dashboard as root. For a ttyACM device owned by `dialout`, an administrator can add the desktop user to that group, followed by logout/login. Exclusive opening rejects subsequent readers but cannot evict an already-open non-cooperating collector. The reader/verifier must never run simultaneously.

Opening USB serial may toggle modem signals/reset some boards. Until the flashed firmware's startup behavior and cutoff are verified, perform the first connection check with motor energy disconnected. The new software does not energize or command a motor.

## Launch the local dashboard on the Pi

After verification closes the serial port, run from the project root:

```sh
ADS_MODE=simulation ADS_SERVE_DASHBOARD=1 ADS_LIVE_SERIAL_PORT=/dev/ttyACM0 ADS_SERIAL_BAUD=115200 \
  .venv-pi/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 13115 --workers 1
```

Leave that terminal running. Open Chromium on the Pi at **http://127.0.0.1:13115/**, or launch in full-screen from a second desktop terminal:

```sh
chromium --kiosk http://127.0.0.1:13115/
```

**ADS_MODE=simulation applies to the retained command/demo services, not the passive receiver.** Setting ADS_LIVE_SERIAL_PORT separately enables actual sensor acquisition. Do not set ADS_MODE=hardware: that legacy runtime mode remains intentionally gated. Physical command endpoints remain simulated/disabled; there is no automatic motor activation.

If using the installed user service, set `ADS_LIVE_SERIAL_PORT=/dev/ttyACM0` in `~/.config/trace-x/runtime.env`, retain `ADS_SERVE_DASHBOARD=1` and `ADS_MODE=simulation`, then use `systemctl --user restart trace-x.service` instead of starting a second backend. The service must point at this updated project path. Diagnose with `journalctl --user -u trace-x.service -n 60 --no-pager`.

## Confirm real data on screen

1. Open **STM32 sensors**, not the simulated multimeter, Motor control or Run diagnostic pages.
2. The page says **ACTUAL STM32 TELEMETRY · READ ONLY**. Protocol is `plain_text` and complete-cycle count increases.
3. Check encoder/INA219 status, receipt time/age and the sample source `stm32_serial`. Zero readings remain zero rather than being replaced by simulation values.
4. From a second Pi terminal, inspect the same structured data: `curl http://127.0.0.1:13115/api/live/motor`.
5. Under safe conditions remove USB or stop telemetry: the connection becomes disconnected/stale and main tiles become dashes. No simulation fallback is used. Reconnect and restart the backend; automatic serial reopen is not implemented. Browser WebSocket reconnect is supported.

Current samples are live/volatile. Continuous experiment recording, calibrated baseline comparison and motor health classification are future work; the monitor still abstains from a health percentage. The imported historical CSVs and simulation workflows remain available separately.

## Before automated motor tests

Verify motor ratings and current limits; calibrated INA219 configuration; encoder CPR, direction and geared-shaft relationship; acquisition timing and baseline at matching voltage/PWM/fixture conditions. Establish guarded durations/PWM limits, readiness checks, explicit acknowledgments, independent STM32 watchdog/fault shutdown and physical emergency power removal. Validate STOP and cable-removal behavior before motor power and supervised testing. Current read-only text telemetry does not provide this command/safety protocol. Load/friction models require independent repeatable labeled runs, run-grouped validation and abstention outside their operating envelope. None of this is enabled by this increment.

## Changed files and validation

Motor-integration changes:

- `diagnostic_platform/text_telemetry.py` (new): bounded line decoder and encoder-anchored six-field cycle assembly.
- `diagnostic_platform/live.py`: passive transport integration, status invalidation, complete samples, stale/disconnected metadata and retained JSON handling.
- `diagnostic_platform/verify_stm32.py`: default passive text/streamed-JSON detection, timeouts and explicit legacy JSON request checks.
- `diagnostic_platform/history.py`: reject non-finite computed power so malformed flat JSON/CSV cannot crash the shared normalization path.
- `api/main.py`: dedicated `/api/live/motor` endpoint; existing live status/WebSocket also include structured motor samples.
- `frontend/src/LiveSensors.tsx`: actual RPM/voltage/current/power tiles, cycle/status/source/age display and no simulation fallback.
- `tests/test_text_telemetry.py` (new): parser, fragmented/corrupt input, disconnected sensors, timeouts, passive verification, JSON regression, API/WebSocket isolation and serial-reader failure tests.
- `.env.example`, `README.md`, `docs/MAC_PI_LIVE_SETUP.md`, and this guide: configuration and Pi operation instructions.
- Rebuilt `deliverables/Trace-X-Pi.zip` and its SHA-256 file. Existing separate Circuit 4 changes remain in the working tree/package; they are not firmware changes.

Observed software validation on the development Mac: **115 tests pass**, frontend production build and ESLint pass, `git diff --check` passes, and no `ADS/` firmware files differ from the current commit. The frontend build retains a bundle-size advisory above 500 kB. The original JSON verifier tests remain passing. Fake transports in tests have no serial write method for passive operation. Real Pi/STM32 acquisition and LCD display were not exercised here; test fixtures are not represented as real hardware measurements. Changes remain local/uncommitted until explicitly published or transferred.
