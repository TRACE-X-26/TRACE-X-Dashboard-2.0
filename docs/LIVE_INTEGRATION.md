# Trace X Pi telemetry and bench verification

## Connect and launch

1. Use the updated Dashboard checkout on the Raspberry Pi 5. Keep motor power disconnected for the read-only connection check. Plug a USB data cable from the Pi into the Nucleo-F401RE ST-LINK USB port. The firmware configures USART2 at 115200 baud, 8 data bits, no parity, one stop bit and no hardware flow control.
2. Stop any existing Trace X service, serial terminal or experiment recorder that has the port open. Use `ls -l /dev/serial/by-id/ /dev/ttyACM*` to identify the port. If the device belongs to `dialout`, grant the Pi login user membership and log back in before retrying.
3. From the Dashboard checkout, using Python 3.11+ and Node.js 22.12+:

   ```sh
   python3 -m venv .venv-pi
   .venv-pi/bin/python -m pip install -r requirements-backend.txt
   (cd frontend && npm ci && npm run build)
   ```

4. Select the protocol for the **flashed** build. Use `passive` for the supplied plain-text serial format or `json` for the checked-in ADS v1 firmware. Replace `/dev/ttyACM0` with the stable by-ID path if available.

   ```sh
   port=/dev/ttyACM0
   # For the plain-text build:
   .venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port "$port" --protocol plain-text
   # For the checked-in ADS v1 build, use this verifier instead:
   .venv-pi/bin/python -m diagnostic_platform.verify_stm32 --port "$port" --protocol json
   ```

5. After the verifier exits, launch the sole dashboard process. Set `ADS_LIVE_PROTOCOL=json` for ADS v1.

   ```sh
   ADS_MODE=simulation ADS_SERVE_DASHBOARD=1 ADS_LIVE_SERIAL_PORT="$port" \
     ADS_LIVE_PROTOCOL=passive ADS_SERIAL_BAUD=115200 \
     .venv-pi/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 13115 --workers 1
   ```

   Open `http://127.0.0.1:13115/` on the Pi. **STM32 sensors** uses the live receiver and **Physical circuit** uses live circuit telemetry. Motor Control and Run Diagnostic are separate simulation screens. A silent or disconnected device produces unavailable live readings. Passive USB removal requires restarting the receiver. ADS v1 polling retries the configured port.

## Measurement contract and verification

- ADS v1 uses newline-delimited JSON with correlated sequence replies. The Pi sends only a heartbeat and `READ_MEASUREMENTS` in polling mode. The checked-in firmware registers a null acquisition callback and reports invalid readings. The host C harness injects timestamped measurements to exercise the same response path.
- The Pi multiplies ADS voltage and current when both are valid and share a device acquisition tick. Plain-text frames retain the STM32's reported power because the receive cycle does not establish synchronous V/I acquisition. The Pi applies no divider correction to branch channels. Motor current calibration, encoder CPR/counting mode, gear ratio and direction still need physical confirmation. Temperature and direction are displayed when supplied by the receiver, with explicit zero preserved. A failed or invalid temperature report invalidates the previous observation. The DS18B20 conversion implementation and validity checks must be confirmed against the flashed build.
- The physical capture workflow uses already-corrected `test_point_voltage_V`, keyed by `asset_id` and `test_point_id`. It requires a fresh observation after the operator confirms probe placement. `adc_saturated` or `protection_event` invalidates the probe. INA219 #2 supply voltage/current remain separate, with calculated power when both appear in the same circuit message. The checked-in firmware emits no ADC or circuit telemetry. Confirm reference and resolution on the actual firmware before implementing any raw-count conversion. The intended 30 kΩ / 10 kΩ divider recovery is 4.0× at acquisition, with no additional correction.
- The checked-in firmware polls a 2-second STM32-local watchdog and latches communication timeout. Its stop callback is exercised by host tests. Relay polarity, power isolation, kill switch behavior and real motor stop on loss of USB remain bench requirements. The plain-text build has no verified stop or watchdog contract available here. Neither live mode enables actuation.

## Test coverage and missing bench evidence

The default branch has a generic simulation diagnostic and a simulation PWM ramp. It does not expose the 13 named workflows as executable dashboard controls. The generic simulator's command, ramp cancellation and saved diagnostic paths are covered by the existing API and motor tests. The ADS v1 host tests verify that the actual checked-in protocol rejects motor control requests with `CONTROL_DISABLED`; stop requests invoke the stop callback but return the same rejection.

| Requested test | Existing evidence | Bench verification still required |
| --- | --- | --- |
| Safe Idle 0% | Archived software-only result | Confirm actual PWM zero, relay state and no shaft motion |
| 10%, 25%, 50%, 75%, 100% | Archived logs with PWM targets | Confirm acknowledged duty, device-reported PWM, synchronous measurements and stop for each setting |
| Minimum Starting PWM | Archived motion at a 5% target | Confirm motion from rest, accepted increments and stop between trials |
| Steady-State RPM | Archived start/stop-marked observations | Confirm the encoder calibration and a steady sampling window using device ticks and events |
| Voltage Stability | No archive run | Capture timestamped INA219 #1 samples at confirmed duty |
| Startup Current | No archive run | Verify acquisition cadence and alignment to the STM32 start event |
| Power Consumption | No archive run | Verify same-sample branch voltage × current |
| Weight / Load Testing | No archive run | Record mass, units and fixture, then verify at matched operating conditions |
| Excessive Friction | No archive run | Record the physical condition and compare with a verified matched baseline |

No physical hardware was tested. The 13 tests need compatible firmware and bench verification before their results can be presented as live. The read-only dashboard does not record completed physical motor runs.

## Load the historical archive on the Pi

Copy the supplied replay JSON to `data/archive_replay.json` in the Pi checkout. For example, from the checkout on the Pi with the health ZIP already copied there:

```sh
mkdir -p data
unzip -p /path/to/Trace_X_Motor_Health.zip archive_replay.json > data/archive_replay.json
```

Open **CSV recordings → Motor test archive replay**. The archive is local, ignored by Git, and separate from the saved simulation sessions. All 53 records reproduce from the supplied CSV ZIP with:

```sh
.venv-pi/bin/python -m diagnostic_platform.motor_health replay /path/to/motor_test_results.zip
```

The bundled module includes baseline fitting and scoring for completed verified runs. No baseline was fitted from the archive. The live UI shows **Not assessed** with **Baseline pending** because no verified matching motor, PWM, load, direction and calibration context exists.
