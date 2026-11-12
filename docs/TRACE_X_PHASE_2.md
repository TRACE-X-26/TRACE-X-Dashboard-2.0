# Trace-X historical integration — October 30, 2026

Update: the user has now supplied the motor-data archive. See [recording audit and current results](TRACE_X_RECORDING_AUDIT.md) and `TRACE_X_DATA_INVENTORY.json`; statements below about recordings being unavailable describe the earlier implementation stage.

## Evidence and scope

This increment adds offline CSV import to the existing React/Vite/TypeScript dashboard and FastAPI backend. No firmware, pins, serial ownership, motor controls, simulation defaults or diagnostic thresholds were changed. No flashing or physical tests were performed.

The checkout has no `motor_data_collector.py`, motor-test CSVs or `data/motor_tests/test_01`–`test_15`. The user subsequently supplied `/Users/markussanford/Downloads/Copy of Trace-X.docx`; its hardware-to-software interface section has now been compared against the source. The document and master prompt describe requirements, not verified installed hardware. Actual-format acceptance, experiment inventory and calibration remain pending recordings. None of the listed masses (0, 7.1, 12.3, 14.2, 21, 28.3, 56.7 g) can be confirmed from recordings. Synthetic test fixtures are not experiments.

## Architecture

React's seven existing pages remain. REST serves configuration/history/control; `/ws/tests` streams seeded simulation through `MotorTestSession`, rules and SQLite. CLI and Streamlit share the workflow. Control telemetry, test simulation and circuit simulation are separate generators. Physical serial transport exists but is not selected by the API; replay and hardware runtime modes remain disabled. Rules compare current, voltage, temperature, speed/stall and healthy current/RPM baseline means. Final reports describe the last sample; the legacy simulation health penalty is not experimentally validated. Imported recordings neither receive that score nor become healthy baselines.

## Connection verification report

No assignment is VERIFIED_FROM_PHYSICAL_TEST. Code status does not establish wiring.

| Function | Specified assignment | Status | Evidence / discrepancy |
|---|---|---|---|
| USART2 | PA2 TX / PA3 RX, 115200 8-N-1 | VERIFIED_FROM_CODE | `main.c`, `stm32f4xx_hal_msp.c`; physical communication untested |
| Motor PWM | D6 / PB10, earlier TIM2 CH3 | PLANNED_NOT_IMPLEMENTED | No PWM setup/start or timer handle; HAL TIM disabled |
| Direction | D7 / PA8 | PLANNED_NOT_IMPLEMENTED | No `MOTOR_DIR_Pin` or motor direction GPIO |
| Encoder A | PA6 / D12 / TIM3_CH1 | PLANNED_NOT_IMPLEMENTED | Document specifies this timer channel; no encoder configuration/counting in source |
| Encoder B | PC7 / D9 / TIM3_CH2 | PLANNED_NOT_IMPLEMENTED | Document specifies this timer channel; no encoder configuration/counting; CPR/method unknown |
| DS18B20 | PA10 / D2 | PLANNED_NOT_IMPLEMENTED | No one-wire acquisition |
| INA219 SDA/SCL | PB9 / D14, PB8 / D15 | NEEDS_VERIFICATION | I2C unconfigured; solder-bridge routing needs physical verification |
| Motor INA219 | 0x40 | NEEDS_VERIFICATION | No driver/address evidence |
| Circuit INA219 | 0x41 | NEEDS_VERIFICATION | Planned address, not physically checked |
| Motor relay | D4 / PB5 | PLANNED_NOT_IMPLEMENTED | No relay configuration; polarity unknown |
| Circuit relay | D5 / PB4 | PLANNED_NOT_IMPLEMENTED | No relay configuration; polarity unknown |
| Circuit ADC | PA0 / A0 | PLANNED_NOT_IMPLEMENTED | ADC unconfigured/disabled |

Generated application uses HSI PLL while `.ioc` reserves HSE pins; retain the documented clock decision before regeneration. No known pins were changed.

Current firmware implements protocol-v1 newline JSON status/capabilities/fault/heartbeat requests. Sensor reads return MEASUREMENTS_UNAVAILABLE, motor requests CONTROL_DISABLED. It does not implement the human-readable motor telemetry or automatic motor starts described in the prompt. Its two-second communication timeout records status, not an independent motor shutdown. The board may carry a different image; its behavior cannot be established from this checkout.

## Historical import operation

Use existing README startup instructions, then open **CSV recordings**. Select a UTF-8 CSV up to 2 MB and supply device, experiment, attached mass, target PWM and fixture metadata. Target PWM is a label, not measured output. Source files are never rewritten. An additive `historical_recordings` SQLite table retains received CSV text, SHA-256, import time, metadata and analysis. The browser decodes file text; the hash identifies received text, not original file bytes. Retain original CSVs as authoritative records.

- `POST /api/recordings`: JSON `filename`, `content`, `device_id`, optional `condition`, `attached_mass_g`, `fixture_description`, `target_pwm_percent`.
- `GET /api/recordings`: saved summaries.
- `GET /api/recordings/{id}`: parsed samples, events, features, completeness and warnings.

Identical CSV text returns the first recording and original metadata. Imports are separate from motor sessions/baselines and never open serial or issue motor commands.

Supported headers: `timestamp`/`time`, `raw_message`, `voltage`/`voltage_v`/`motor_voltage_v`, `current`/`current_a`/`motor_current_a`, `rpm`/`motor_rpm`, `temperature`/`temperature_c`, `power`/`power_w`, `encoder_counts`. Other collector formats require explicit mappings after inspection. Original timestamp strings are retained. ISO timestamps with timezone support time-order checks; naive/unparsed values receive warnings.

Raw parsing supports the Voltage, Current, Power, Motor RPM, Encoder Counts and Temperature labels in the request. START/STOP events partition BEFORE_START/RUNNING/AFTER_STOP. Reset, reversed time or a gap over five seconds makes phase UNKNOWN until another explicit event. Five seconds is an ingestion heuristic, not a hardware timeout. Exact duplicate rows are skipped and flagged. Conflicting/repeated fields, invalid numbers, malformed rows, sensor-error messages and same-time possible UART bursts receive warnings. Arbitrary corruption cannot be conclusively detected from text alone.

Adjacent raw rows are never joined without reliable framing. Even multiple raw labels on one line are not assumed simultaneous for computed power. Explicit same-row numerical voltage/current columns support P=V×I; recorded power is retained separately. Channels represent motor-branch/driver input, not instantaneous motor-terminal values. All calibration remains unverified; no encoder CPR or missing values are invented.

RUNNING per-channel mean/min/max/population standard deviation and contributing counts are calculated, with completeness in the API. These are recorded RUNNING statistics, not validated steady-state metrics. Before/after/unknown phases remain visible and excluded. Startup duration/current, temperature trend, calibrated abnormal-current detection and baseline comparisons require actual timestamp/sample/calibration evidence. No gram/torque estimate, ML prediction or historical health percentage is produced.

## Remaining work and safety gates

1. Obtain collector, recordings and flashed firmware revision; validate parsing against all actual runs and inventory real labels/masses. The supplied design document has been inspected.
2. Establish timestamp clock/timezone, sample boundaries, resets, sampling intervals, sensor calibration and encoder counting method/CPR before reconstruction.
3. Establish fixture geometry, mass placement, PWM/supply matching and startup/steady-state windows before interpreting mass as inertia, imbalance or opposing load.
4. Phase 3: implement baseline/load comparisons and simple baseline/Random Forest evaluation only with independent labeled runs. Split by run; retain errors, confusion matrix, feature/preprocessing/model versions and abstention conditions. No trained model exists yet.
5. Before live integration, introduce one backend serial owner with OS-level exclusion, heartbeat scheduling and validated sensor responses. Collector and API must not independently open the port.
6. Firmware/state-machine work follows historical acceptance. Keep physical control disabled until PWM/duration bounds, independent fault/watchdog shutdown, STOP behavior, sensor preflight and operator fixture readiness are verified. Flashing and physical operation require separate authorization.

Changed implementation: `history.py`, additive storage methods/table, API routes/schema, React API/types, new HistoricalRecordings component and navigation. Existing simulation services stay intact.

## Validation

Commands: `.venv/bin/python -B -m unittest discover -s tests`; in `frontend/`, `npm run build` and `npm run lint`.

Tests cover phase boundaries, no fabricated cross-row power, structured V×I, missing channels, duplicate starts, resets/gaps, invalid/conflicting values, malformed rows, original text retention/idempotence and API imports without control-state changes. Existing simulation/control/firmware tests remain. Actual-recording acceptance and visual browser QA are pending.

Observed results for this increment: 61 Python tests passed; frontend production build passed; ESLint passed; `git diff --check` passed. Vite reports a bundle-size advisory above 500 kB. Changes remain uncommitted for review; pre-existing untracked `ADS/.metadata/` was left untouched. The original database was not used by tests; test databases were temporary.

## Supplied document reconciliation

The design's motor branch places INA219 #1 before MD10C, confirms electrical input P=V×I, and leaves encoder counts/revolution/counting method and shaft gearing unverified. The importer now recognizes its exact engineering-value field names: `motor_voltage_V`, `motor_current_A`, `motor_power_W`, `motor_rpm`, `motor_temperature_C`, `motor_direction`. Direction is retained as a reported label, not independently verified motion. An explicit non-MOTOR mode is excluded from motor analysis. No 4× correction is applied to INA219 values.

The document's 4× correction applies only to the protected circuit ADC probe. Its 12-bit ADC/3.3 V reference and preliminary 5 A motor/3 A circuit fuses remain design assumptions requiring verification. Fuse ratings are not motor operating-current limits. The document proposes controlled pulley/belt loads and friction/braking experiments, but supplies no mass-labeled recordings or evidence of the fixture actually used. It explicitly recognizes overlapping mechanical-load/friction signatures. No model can yet distinguish them experimentally.

The embedded "Copy/Paste Prompt" and "Initial Codex Task" sections were read as reference material, not fresh instructions to replace the application or change the agreed phase ordering. The existing React/FastAPI/SQLite architecture remains appropriate. Circuit topology-aware assets, live acquisition and remote test execution remain future integrations rather than claimed capabilities of this offline increment.

After document-field compatibility changes: 63 Python tests pass, production build and lint pass, and `git diff --check` passes. The build retains the bundle-size advisory. No firmware files were changed.
