# Phase 1 Review and Manual Test Checklist

**Phase:** Modular software architecture  
**Status:** Software complete; hardware unverified and disabled  
**Version:** API/UI 0.5.0

## What changed

- Runtime configuration is validated from environment variables and defaults to simulation.
- Hardware and replay application modes fail closed until a configured adapter exists.
- Every live motor sample now has a parallel measurement envelope containing device, sensor, unit, quality, source, calibration, session, timestamp, and sequence metadata.
- Simulation, replay, device-connection, and motor-controller boundaries are defined.
- API, CLI, and Streamlit test paths use one motor-test session lifecycle.
- The automated PWM ramp moved from the browser into a bounded backend service.
- Cancelling, emergency stopping, or completing the ramp forces simulated output to 0% and disables the driver.
- Simulated motor commands and sequence actions are persisted in SQLite system events.

## Start the application

Backend terminal:

```bash
cd /Users/markussanford/Documents/ChatGPT/Capstone
source .venv/bin/activate
python3 -m uvicorn api.main:app --reload --port 13115
```

Frontend terminal:

```bash
cd /Users/markussanford/Documents/ChatGPT/Capstone/frontend
npm run dev
```

Open `http://localhost:5173`.

## Manual checks

### 1. Existing application

- [ ] Dashboard loads and says the API is connected.
- [ ] Existing history and profiles still appear.
- [ ] Live Multimeter remains explicitly simulated.
- [ ] Circuit diagnostics still completes a guided scenario.

### 2. Backend-owned motor ramp

- [ ] Open **Motor control** and select **Run automated PWM ramp**.
- [ ] The button shows the backend step number as PWM rises and falls.
- [ ] Select the button again to cancel; driver becomes Disabled and Output becomes 0%.
- [ ] Start again, navigate to another page, wait about eight seconds, and return.
- [ ] The sequence finishes safely even though the Motor control page was not open.
- [ ] Emergency Stop during a ramp cancels it, sets output to 0%, and latches the stop.
- [ ] Resetting the emergency stop does not automatically restart the motor.

### 3. Shared diagnostic workflow

- [ ] Run a five-or-more-sample healthy diagnostic; it completes and saves history.
- [ ] Run the stalled scenario; it ends in `SAFETY_TRIP` after the startup window.
- [ ] Run communication loss; it ends in `COMMUNICATION_FAULT`.

### 4. API evidence, optional

- [ ] Open `http://localhost:13115/api/health`; confirm `mode` is `simulation` and `hardware_control` is `false`.
- [ ] Open `http://localhost:13115/api/events`; confirm recent simulated commands/sequences are recorded.

## Expected limitations

- No STM32 firmware or USB serial adapter exists yet.
- No real hardware commands can be issued.
- Replay is available as a tested driver interface but not as a selectable application mode yet.
- Measurement envelopes are streamed alongside the legacy motor payload; historical table migration comes later.
- Event history is available through the API but does not yet have a dedicated UI screen.
- Frontend component-test infrastructure remains deferred; TypeScript build and lint are enforced.
- The existing Vite bundle-size advisory remains.

## Approval gate

Do not begin Phase 2 until the user has run this checklist and confirmed the application behaves as expected.

