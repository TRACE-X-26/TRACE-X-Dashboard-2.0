# Hardware Verification Procedure

No step in this document has been completed merely because software tests pass. Record evidence, date, operator, hardware revision, firmware hash, instruments, and results for every physical check.

## Gate 1 — preserve and reconcile firmware

- [ ] Commit and push the imported `ADS/` CubeIDE project after Phase 3 review.
- [ ] Confirm the board is NUCLEO-F401RE / STM32F401RET6.
- [x] Investigate and document the `.ioc` HSE reservation versus generated HSI PLL code; do not regenerate until the intended source is selected.
- [x] Build the communication-only firmware in STM32CubeIDE with zero errors and warnings.
- [ ] Flash it with motor power disconnected.
- [ ] Confirm status/capabilities/heartbeat at 115200 8-N-1.
- [ ] Confirm the actual Pi serial device path and stable device identification.

## Gate 2 — electrical design review

- [ ] Record MD10C revision and sign-magnitude mode.
- [ ] Select a timer/PWM-capable STM32 pin without conflicting with USART2 or debug pins.
- [ ] Select a direction GPIO with a defined safe reset level.
- [ ] Verify MD10C logic-level compatibility with 3.3 V outputs.
- [ ] Verify common signal ground while retaining correct motor-power wiring.
- [ ] Record motor rated and stall current.
- [ ] Record supply current limit, fuse rating, wire gauge, and connector ratings.
- [ ] Demonstrate that the physical kill switch removes motor energy independently.

## Gate 3 — sensor design review

- [ ] Record both INA219 addresses and bus wiring.
- [ ] Verify each shunt/current path is safe for expected and stall current.
- [ ] Select and document I²C pins and pull-ups.
- [ ] Select and document ADC/probe pins only if used.
- [ ] Verify divider, clamp, reference, input range, and tolerance.
- [ ] Select and document DS18B20 pin and 4.7 kΩ pull-up.
- [ ] Leave RPM unavailable until a real RPM sensor and input are documented.

## Gate 4 — firmware safety before motor power

- [ ] Configure motor pins in `.ioc`; record generated pin map.
- [ ] Firmware boot/reset leaves PWM at 0 and driver disabled.
- [x] Implement bounded frame parsing without unbounded blocking — **HOST TESTED ONLY**.
- [x] Implement status, capabilities, errors, sequence correlation, and heartbeat — **HOST TESTED ONLY**.
- [ ] Implement a communication watchdog that independently forces PWM to 0.
- [ ] Reject invalid state transitions, PWM values, and direction changes under power.
- [ ] Latch applicable faults and require explicit reset.
- [ ] Confirm STOP_MOTOR behavior using logic analysis with motor power disconnected.
- [ ] Confirm cable removal produces a safe output state.

## Gate 5 — measurement calibration

- [ ] Compare voltage channels against a calibrated/reference multimeter.
- [ ] Compare current channels at multiple known loads.
- [ ] Record offset, scale, uncertainty, valid range, and calibration version.
- [ ] Confirm disconnected sensors report unavailable/error, not realistic defaults.
- [ ] Confirm timestamps and measurement units through the full Pi path.

## Gate 6 — controlled motor test

- [ ] Obtain explicit operator authorization.
- [ ] Position an observer at the physical kill switch.
- [ ] Begin with conservative supply current limit and low PWM.
- [ ] Verify manual start and normal stop.
- [ ] Verify software STOP_MOTOR.
- [ ] Verify communication-watchdog stop.
- [ ] Verify physical emergency stop.
- [ ] Only then consider enabling bounded automatic testing.

## Evidence classification

Until all relevant gates pass, the UI and reports must use `IMPLEMENTED_UNVERIFIED`, `SIMULATED`, `UNAVAILABLE`, or `UNSUPPORTED`. Only measurements and actions demonstrated with retained evidence may be labeled `VERIFIED` or `LIVE`.

