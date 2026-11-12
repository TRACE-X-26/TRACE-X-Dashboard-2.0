# Hardware Capabilities and Verification Matrix

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

This document combines the existing Fritzing inspection with the target platform named in the development brief. It does not certify wiring or hardware behavior.

## Target platform

| Component | Intended role | Evidence | Status |
|---|---|---|---|
| Raspberry Pi 5 | FastAPI, UI hosting, storage, reports | Present in design; no deployment test | **IMPLEMENTED_UNVERIFIED** |
| STM32 Nucleo-F401RE | Real-time control, acquisition, safety | CubeIDE project and communication-only firmware in repository | **IMPLEMENTED_UNVERIFIED** |
| Cytron MD10C R2 | Brushed DC motor PWM/direction | Present in Fritzing; no physical validation | **PLANNED** |
| 3–12 V DC motor | Primary diagnostic device | Present in Fritzing; specifications not recorded | **PLANNED** |
| 12 V / 5 A bench supply | Main power | Present in Fritzing | **PLANNED** |
| INA219 motor channel | Motor-bus voltage/current/power | Present in Fritzing; address/range/calibration unknown | **PLANNED** |
| INA219 circuit channel | Circuit voltage/current/power | Present in Fritzing; address/range/calibration unknown | **PLANNED** |
| DS18B20 | Motor temperature | Present with 4.7 kΩ pull-up | **PLANNED** |
| Voltage-divider probe | External DC voltage | 30 kΩ/10 kΩ divider and protection shown | **PLANNED** |
| Two-channel relay | Test-path switching | Present; active polarity unknown | **PLANNED** |
| Fuses and kill switch | Independent protection | Shown, ratings/behavior unverified | **PLANNED** |
| XL4015 CC/CV | Regulated auxiliary/test supply | Present; settings unverified | **PLANNED** |

No row is **VERIFIED** because no physical test evidence is stored in the repository.

## Existing STM32CubeIDE configuration discovered October 14, 2026

The authoritative project is `ADS/` in this repository. Its current `.ioc`
configures only USART2, board LED/button GPIO, and debug pins. USART2 uses PA2
TX and PA3 RX; generated initialization runs it at 115200 8-N-1 with no flow
control. The firmware now parses the safe subset of the Raspberry Pi protocol,
but it has not been flashed or exercised on a board. ADC, I²C, timers/PWM, RPM
capture, watchdog, motor direction, and sensor acquisition remain unconfigured. See
`STM32_FIRMWARE_AUDIT.md` for exact evidence.

## Supported claims today

- The software can generate and process simulated voltage, current, power, temperature, RPM, resistance, and vibration values.
- The software can simulate PWM/direction commands and safety interlocks.
- The STM32 communication-only source builds and responds to status,
  capabilities, faults, and heartbeat in host tests.
- These are software demonstrations only and must be labeled `SIMULATION`.

## Capabilities that may be enabled after verification

| Capability | Prerequisites |
|---|---|
| Motor voltage/current/power | INA219 range and shunt rating verified; address configured; calibrated against references |
| Motor temperature | Sensor mounting, OneWire pin, pull-up, conversion timing, disconnection behavior verified |
| PWM and direction | Exact Nucleo pins, timer/channel, logic compatibility, MD10C mode, common ground, and safe boot verified |
| Relay control | Channel purpose, active level, isolation, startup state, and load rating verified |
| External DC voltage | ADC pin/reference, divider values/tolerance, clamp behavior, maximum safe input, and calibration verified |
| Hardware emergency stop | Physical circuit interrupts energy independently of Pi/STM32 software |

None of these physical hardware capabilities are exposed by the current
firmware. Only read-only communication metadata is implemented.

## Unsupported capabilities

- **RPM:** no RPM sensor appears in the inspected Fritzing design.
- **Vibration:** no vibration sensor appears in the inspected Fritzing design.
- **Mechanical efficiency:** torque or mechanical output power is not measured.
- **Resistance and continuity:** no verified de-energized excitation/measurement circuit exists.
- **Frequency and input PWM duty:** no verified input-conditioning/capture path exists.
- **Arbitrary circuit diagnosis:** only one simulated, manually defined circuit profile exists.

Unsupported fields must be `null`/`UNAVAILABLE`, not simulated, whenever the application is in hardware mode.

## Required wiring decisions before firmware

1. Physically verify the proposed MD10C PWM mapping: D6 / PB10 / TIM2_CH3.
2. Physically verify the proposed direction mapping: D7 / PA8 and its safe reset state.
3. Confirm MD10C revision, sign-magnitude mode, and 3.3 V input compatibility.
4. Record both INA219 addresses and maximum safe current/shunt power.
5. Verify A4/A5 solder-bridge routing to PB9/PB8 for I2C, pull-ups, bus voltage, and ownership.
6. Verify DS18B20 D2 / PA10 and pull-up placement.
7. Verify relay D4 / PB5 and D5 / PB4 inputs, active polarity, and loads.
8. Verify voltage-probe A0 / PA0, reference, divider tolerance, and maximum input.
9. Record fuse ratings, wire gauges, supply current limit, and motor stall current.
10. Demonstrate that the kill switch removes motor energy independently.

## Safety gates

Real motor output must remain disabled until all gates have evidence:

- Schematic/wiring peer review completed.
- Physical e-stop and fuses tested.
- Supply polarity and current limit checked.
- Firmware boots and resets at PWM 0.
- Watchdog stops output on communication loss.
- Invalid command/state transitions are rejected by firmware.
- Sensors report missing/invalid states rather than plausible defaults.
- Manual low-power test approved and observed.
- Software clearly identifies hardware, simulation, replay, stale, and unavailable data.

## Proposed connection model

```text
Pi 5 ── USB CDC serial ── Nucleo-F401RE
                              ├── PWM + DIR ── MD10C ── motor
                              ├── I2C ── INA219 motor + circuit
                              ├── OneWire ── DS18B20
                              ├── ADC ── protected voltage probe
                              └── GPIO ── relay inputs

12 V supply ── fuse ── physical kill switch ── motor power path
```

The Raspberry Pi is not a safety controller. The STM32 is not a replacement for physical overcurrent protection or emergency power interruption.
