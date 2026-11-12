# Changelog

All notable project changes should be recorded here. Hardware verification is tracked separately from software implementation.

## Unreleased

### Added — Raspberry Pi STM32 connection test, October 16, 2026

- Added a dedicated communication-only tester that discovers the Nucleo serial
  port and verifies status, capabilities, faults, and heartbeat.
- Kept motor control explicitly disabled throughout the connection test.
- Added clear pass/fail output and port, permission, and port-contention hints.
- Added host-side tests for safe command selection and serial-port discovery.

### Added — Phase 3 communication-only STM32 firmware, October 14, 2026

- Imported the existing NUCLEO-F401RE STM32CubeIDE project without regenerating CubeMX files.
- Added a fixed-buffer protocol module for status, capabilities, faults, heartbeat, acknowledgments, and explicit errors.
- Preserved the existing USART2 PA2/PA3 configuration and integrated only through CubeMX user-code regions.
- Retained the legacy banner behind a disabled compile-time switch.
- Kept measurements and every motor-control command explicitly disabled.
- Added native host compilation tests using frames produced by the production Python encoder and responses validated by its decoder.
- Completed a clean STM32CubeIDE Debug build with zero errors and zero warnings.
- Documented the clock investigation, exact compatibility changes, staged integration plan, and remaining hardware gates.
- Recovered the intended Nucleo header-to-peripheral mapping from the original Fritzing netlist and cross-referenced it with the NUCLEO-F401RE pinout; all mappings remain physically unverified.

### Added — Phase 2 STM32 communication boundary, October 14, 2026

- Audited the existing NUCLEO-F401RE CubeMX configuration and generated HAL firmware without modifying either one.
- Added a versioned newline-delimited JSON protocol for status, capabilities, measurements, commands, acknowledgments, errors, and heartbeat traffic.
- Added a Raspberry Pi STM32 connection with bounded reads, correlated replies, explicit device errors, legacy-banner probing, and safe disconnect behavior.
- Added a matching simulation adapter so the complete backend contract can be developed without hardware.
- Added simulation-only hardware API endpoints with explicit source and verification labels.
- Added `pyserial` as the physical transport dependency while keeping physical hardware selection and motor control disabled.
- Added protocol, timeout, error, disconnect, legacy-firmware, and simulator tests.
- Documented the actual serial settings and pin assignments, the proposed protocol, current capability gaps, and the required hardware verification sequence.

### Added — Phase 1 modular architecture, October 14, 2026

- Added validated, simulation-default runtime configuration.
- Added shared measurement envelopes with source, quality, calibration, device, sensor, session, and sequence metadata.
- Added device/controller interfaces and a finite replay measurement driver.
- Added a shared motor-test session used by API, CLI, and Streamlit paths.
- Moved the simulated PWM ramp from browser timers to a bounded backend sequence service.
- Added persistent SQLite system events for simulated commands and sequences.
- Added architecture, replay, metadata, configuration, and sequence-safety tests.
- Explicitly reject hardware and replay runtime modes until their adapters are configured and verified.

### Documentation — Phase 0 audit, October 14, 2026

- Added repository current-state audit and feature-status classifications.
- Added current and target architecture documentation.
- Added deadline-driven implementation roadmap.
- Added hardware capability and safety-gate matrix.
- Added software, mock-device, and hardware-in-the-loop test plan.
- Added implementation checklist.
- No application behavior, hardware configuration, or firmware was changed.
