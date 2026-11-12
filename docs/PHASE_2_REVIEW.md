# Phase 2 Communication Review and Manual Test Checklist

> Historical Phase 2 snapshot. Phase 3 subsequently added communication-only
> STM32 protocol source; see `PHASE_3_REVIEW.md` for current firmware status.

**Status:** Raspberry Pi interface and simulation adapter complete; firmware protocol and physical hardware unverified  
**Firmware changed:** No  
**Physical serial port opened automatically:** No

## What to run

Start the backend and frontend exactly as in Phase 1. The application remains in simulation mode.

Backend:

```bash
cd /Users/markussanford/Documents/ChatGPT/Capstone
source .venv/bin/activate
python3 -m pip install -r requirements-backend.txt
python3 -m uvicorn api.main:app --reload --port 13115
```

Frontend:

```bash
cd /Users/markussanford/Documents/ChatGPT/Capstone/frontend
npm run dev
```

## Manual checks

- [ ] Existing dashboard, motor control, multimeter, diagnostics, profiles, and history still load.
- [ ] Open `http://localhost:13115/api/health`; `mode` is `simulation`, `hardware_control` is false, and `stm32_connected` is true for the simulation adapter.
- [ ] Open `http://localhost:13115/api/hardware/status`; source is `SIMULATION`.
- [ ] Open `http://localhost:13115/api/hardware/capabilities`; `hardware_verified` is false.
- [ ] Open `http://localhost:13115/api/hardware/measurements`; RPM is null.
- [ ] Open `http://localhost:13115/docs` and inspect the four `/api/hardware/*` operations.
- [ ] Run the existing automatic PWM ramp and emergency-stop checks again.

## Optional non-control hardware connectivity check

Do not connect motor power. After installing dependencies, the standalone serial adapter can recognize the current firmware's `STM32 CONNECTED TO PI` banner without transmitting data. The application does not perform this probe automatically. Confirm the actual serial device path first; do not assume `/dev/ttyACM0` on every computer.

## Expected limitations

- Current STM32 firmware is transmit-only and incompatible with the structured command protocol.
- No physical status, measurement, command, acknowledgment, error, or heartbeat response exists yet.
- PWM, direction, ADC, I²C, INA219, RPM, and watchdog are unsupported in current firmware.
- The real serial adapter is not selected by the API and motor control remains simulation-only.
- `pyserial` is a declared backend dependency but imported only if the physical adapter is explicitly instantiated.

Do not proceed to firmware implementation or real motor control until these findings and the verification sequence are reviewed.

