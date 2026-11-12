# Dashboard 2.0 — Simple Motor Test (review branch)

This change simplifies only the **Motor Testing** user interface. It does not flash firmware, change relay wiring, relax safety limits, or automatically approve a commissioning profile.

## Screen and workflow
- Four readouts: Voltage, Current, Motor Speed (RPM), Power.
- Fixed PWM from the commissioned profile (normally 50%) and a maximum duration of 30 seconds.
- **Start Motor**: a single explicit supervised confirmation; then the existing `POST /api/automated/runs` endpoint.
- **Stop Motor** and **Emergency Stop** use the existing run-stop endpoint and do not claim confirmed physical cutoff based solely on an HTTP response.
- Read-only `POST /api/motor/hardware/preflight` runs automatically at entry and roughly every 8 seconds while idle (the server's cached readiness expires after 15 seconds).
- No manual Check Hardware button, PWM dropdown, test-condition prompts or list of 13 test procedures in the normal motor screen.
- Existing backend/firmware read-only contract, operator authorizations, 10–14 V / 1.5 A limits, watchdog, startup relay-on power check at zero PWM and 30-second shutdown remain unchanged.

## Conditions for Start Motor to become enabled
1. Raspberry Pi service and dashboard backend respond at the same origin.
2. STM32 connected over USB serial; exact ST-LINK USB serial number entered in **the private Pi commissioning profile**, not guessed.
3. STM32 reports device `STM32-ADS`, firmware `0.7.0-downstream-protected`, ADS v1 CRC32, and the expected command set.
4. Flash a separately commissioned **SUPERVISED_TEST** build when appropriate. Stock `Debug` / `Release` build profiles in `ADS/.cproject` currently select `ADS_USE_PROTECTED_PROFILE=1` and deliberately disable real outputs. Any change to a commissioned profile must reflect genuine bench verification.
5. The Pi's private hardware profile must pass `load_hardware_profile`, including correct `serial_identity`, evidence/calibration identifiers, the correctly recorded verified settings, 50% fixed PWM, <=30000 ms duration, `temperature_enabled=false`, active-low relays and downstream motor INA219 placement. The example profile in `deploy/pi/supervised-operator-profile.json` is **not** ready as shipped (serial identity empty, protection limits not verified in example).
6. Pi runtime permission `ADS_HARDWARE_CONTROL_ENABLED=true` set **only after commissioning**, with a valid `ADS_AUTOMATION_HARDWARE_PROFILE` path in `~/.config/trace-x/runtime.env`. Restart Pi service after env changes. Do not change `ADS_MODE` merely to enable the separate automated engine.
7. On entering Motor Testing, automatic **read-only** preflight checks capability, idle outputs, off-state INA219 and encoder, version, configuration, signal validity, and runtime permission. This reports `hardware_control=true` from `GET /api/motor/hardware/status` only when the profile is ready and a fresh preflight passed.
8. Select **Motor**, not Circuit, and make sure no motor/circuit run is active. Start button then enables. Clicking prompts for one confirmation and initiates one fixed-duty run.
9. STM32 then performs protected ARM → relay-on at zero PWM → voltage validation → SET_PWM → START_TEST. It can still reject an unsafe start. Physical cutoff accessible throughout.

## Verification and deployment
No end-to-end physical motor verification or Pi deployment was done by this change. Before merging:
- Run `cd frontend && npm ci && npm run build && npm run lint` on a development machine/Pi with dependencies installed.
- Run existing Python test suite for API/engine regressions.
- Confirm the real (not generic disabled) firmware capabilities and off-state readings via read-only preflight.
- Verify shutdown and relay behavior on hardware before enabling physical testing.
- Deploy built frontend/backend consistently. Do not replace only frontend files without rebuilding the Vite dist/assets.

## Diagnostic commands on the Pi (read-only)
```bash
curl -s http://127.0.0.1:13115/api/motor/hardware/status | python3 -m json.tool
curl -s -X POST http://127.0.0.1:13115/api/motor/hardware/preflight | python3 -m json.tool
```
The preflight request is read-only to hardware and does not arm a motor. Keep motor supply disconnected during initial serial/contract checks.
