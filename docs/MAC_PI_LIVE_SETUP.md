# Mac dashboard and Pi sensor receiver

Update: the current plain-text STM32 format is supported without firmware changes. See [plain-text motor verification and launch commands](STM32_PLAIN_TEXT_MOTOR.md). The live motor tiles now use complete encoder-anchored receive cycles; older per-channel descriptions below remain relevant to the observation table.

The existing dashboard runs on the Mac. Run the FastAPI backend on the Raspberry Pi; it owns the STM32 USB serial connection. The Mac's Vite proxy forwards API/WebSocket traffic to the Pi. Algorithms and SQLite remain on the backend. No browser GPIO or serial access is required.

This increment implements passive motor telemetry reception and data-quality display, not verified motor/circuit health or remote physical control. It is opt-in; simulation defaults remain. The repository communication-only firmware does not publish sensor data. Use the team's existing sensor-reporting firmware only after identifying its source/version. Do not flash the repository image over it expecting live sensors.

## Before connecting

Stop the standalone serial collector and terminal programs. Only one backend worker should own the device. The passive reader uses pyserial exclusive locking plus kernel TIOCEXCL to reject subsequent opens; this cannot evict programs already holding a descriptor or prevent privileged bypass. Opening a USB serial device can toggle modem signals/reset some boards. Review the currently flashed firmware's reset/autostart behavior with motor energy disconnected before enabling the receiver. No serial bytes or motor commands are written by the new monitor.

## Raspberry Pi

Copy the repository to the Pi, install its backend requirements in a virtual environment, and identify the STM32 ST-LINK serial path. Prefer a stable `/dev/serial/by-id/` path over assuming ttyACM0. The current user needs serial access. From the repository root:

```sh
ADS_LIVE_SERIAL_PORT=/dev/ttyACM0 ADS_SERIAL_BAUD=115200 .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 13115 --workers 1
```

This is an example configuration, not a command executed during development. The receiver opens only when `ADS_LIVE_SERIAL_PORT` is nonempty. It does not automatically reconnect after port/open failures; fix the cause and restart the backend. Stop/Start motor buttons elsewhere in the dashboard still control simulation only.

## Mac

With both devices on the same trusted local network, from `frontend/`:

```sh
ADS_BACKEND_URL=http://PI_HOSTNAME_OR_IP:13115 npm run dev
```

Replace the placeholder with the actual Pi hostname/IP. Open the existing dashboard at `http://localhost:5173`, then **STM32 sensors**. `GET /api/live/status` and `/ws/live` supply the same telemetry snapshot. Vite's proxy setting applies to the development server; a production deployment needs an equivalent reverse proxy. The Pi backend/database becomes the source for all dashboard API requests; previously imported Mac-local history must be separately copied/imported into the Pi database if needed. Do not overwrite an active SQLite database or copy only its main file while WAL writes are active.

Keep this prototype on the trusted LAN; no internet exposure or authentication layer is configured in this increment.

## Interpretation and remaining work

Legacy messages and the design's motor JSON field aliases are supported. Each channel retains its own host receipt timestamp; missing values are not filled or combined into invented power. Structured same-frame V/I can calculate electrical power; recorded power stays separately labeled. Channels become stale after three seconds or serial disconnection. Resets clear cached values and sensor failure messages invalidate affected values. Temperature and INA219 connection text is not calibration evidence. Malformed and oversized frames are flagged; no unbounded receive buffer is used.

The live diagnosis currently abstains with INSUFFICIENT_CALIBRATION. Required next steps: verify serial operation on the Pi, identify actual firmware/sample timing, calibrate channels and encoder CPR, select the correct geared-motor baseline/limits, and establish circuit asset/test-point mappings. Generic existing simulation profile values (including 2500 RPM) must not become this geared motor's verified limits. Circuit-mode readings are explicitly excluded from motor analysis; circuit live normalization and topology comparisons remain to implement. No live-data persistence or trained health model is claimed by this monitor.

Once verified, motor rules can compare branch voltage/current, encoder speed, startup behavior and temperature with matching-condition baselines. Circuit rules must compare labeled test-point measurements with the selected circuit's expected values and tolerances. Results should distinguish abnormal, normal within validated coverage, and insufficient data. Neither model may override STM32 safety controls.

Software validation: 71 Python tests pass; production frontend build, lint and `git diff --check` pass. Tests cover passive default, independent legacy channels, structured motor power, circuit exclusion, sensor invalidation, stale data and reset/event handling. Vite retains the bundle-size advisory. No Pi connection, physical serial acquisition or browser visual check was performed during implementation. Changes remain uncommitted.
