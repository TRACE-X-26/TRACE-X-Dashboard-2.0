# Incremental STM32 Firmware Integration Plan

November 6 update: see [bounded firmware delivery](BOUNDED_STM32_MOTOR_TEST.md)
for the new default-disabled command state machine, acquisition adapters and
remaining physical acceptance gates. Earlier implementation-stage descriptions
below are historical and do not establish current bench verification.

This plan deliberately separates protocol compatibility from physical output.
Each gate must be reviewed and tested before the next one begins.

## Stage 1 — communication-only firmware (implemented, not flashed)

- Preserve USART2 PA2/PA3 at 115200 8-N-1.
- Assemble newline-delimited frames with a fixed receive limit.
- Parse protocol version, message type, sequence, device identity, timestamp,
  payload, and command name without dynamic allocation.
- Correlate every response using `payload.reply_to`.
- Respond to status, capability, fault, and heartbeat requests.
- Return explicit errors for malformed, oversized, unsupported, measurement,
  and motor-control requests.
- Report `SAFE_IDLE`, zero PWM, unconfigured direction, no measurement types,
  and `hardware_control:false`.
- Move to `COMMUNICATION_TIMEOUT` after 2000 ms without a valid request. Since
  no motor outputs exist in this stage, this is a reported software state only.

Exit evidence: host C protocol tests pass; production Python decoder accepts all
responses; CubeIDE clean build passes. No board flash or motor power is needed.

## Stage 2 — board-level serial verification, motor power disconnected

- Resolve and record the Mac and Raspberry Pi virtual-COM device names.
- Flash communication-only firmware with motor supply physically disconnected.
- Verify repeated status/capability/heartbeat exchanges and sequence matching.
- Send malformed, oversized, unknown-version, duplicate, and delayed frames.
- Unplug USB and confirm the software timeout state after reconnect/reset.
- Measure actual USART2 baud and verify the selected clock source.

Exit evidence: captured serial logs and repeatable timeout/reconnect results.

## Stage 3 — safety state machine, still no PWM pin

- Define explicit `BOOT_SAFE`, `SAFE_IDLE`, `ARMED`, `RUNNING`, `FAULT_LATCHED`,
  `COMMUNICATION_TIMEOUT`, and `EMERGENCY_STOP` transitions.
- Require a fresh heartbeat/session before arming.
- Reject stale/duplicate commands and invalid transitions.
- Make reset, timeout, parser failure, and disconnect converge on disabled state.
- Add an independent hardware watchdog only after its reset behavior is reviewed.

Exit evidence: transition-table tests and fault-injection tests with no motor
output configured.

## Stage 4 — pin and electrical design approval

- Select MD10C PWM and direction pins using the Nucleo schematics and actual
  shield/wiring constraints; update `.ioc` only after review.
- Confirm MD10C input thresholds are compatible with 3.3 V STM32 outputs.
- Confirm grounds, supply separation, fuse/current limit, emergency disconnect,
  pull-down/default states, and direction polarity.
- Decide whether any relay/enable signal is required and determine its safe
  inactive polarity.
- Reconcile the `.ioc` clock representation before regeneration and review the
  entire generated diff.

Exit evidence: signed pin map and electrical safety checklist.

## Stage 5 — PWM and direction with motor power disconnected

- Configure a timer PWM channel with output forced inactive at boot.
- Configure direction with a defined safe default.
- Keep application-level motor commands compile-time disabled initially.
- Implement bounded PWM range/ramp, direction-change interlock, command expiry,
  and stop behavior.
- Verify pins using a scope or logic analyzer only.

Exit evidence: measured frequency, duty cycle, polarity, boot state, timeout
state, and emergency-stop behavior with no motor supply.

## Stage 6 — ADC/sensor acquisition

- Finalize voltage/current sensor circuits and prove maximum STM32 ADC input
  remains within absolute ratings under faults.
- Choose ADC channels, reference assumptions, sample time, filtering, and source
  impedance from the STM32F401 datasheet.
- Add raw counts first; then versioned calibration coefficients and engineering
  units with validity/quality flags.
- Compare against calibrated reference instruments across the intended range.
- Keep RPM absent unless a physical RPM sensor and capture path are added and
  validated.

Exit evidence: calibration records, uncertainty, saturation/open-sensor tests,
and cross-checks against reference instruments.

## Stage 7 — controlled motor bring-up

- Complete emergency-stop and current-limit tests first.
- Begin with low current limit and low duty cycle under direct supervision.
- Enable only capabilities proven in earlier stages.
- Verify STOP, USB loss, Pi crash, STM32 reset, sensor fault, and watchdog paths.
- Only then consider enabling the backend physical-control flag in reviewed code.

## Requirements still unverified

- MD10C PWM pin, direction pin, frequency, direction polarity, and 3.3 V logic.
- Motor supply, grounding, fuse, current limit, flyback/regeneration behavior,
  and physical emergency disconnect.
- Voltage/current sensor part numbers, ranges, scaling, isolation, ADC pins, and
  calibration.
- Whether RPM hardware exists.
- Hardware watchdog and independent output-disable mechanism.
- Real USB serial path, permissions, cable/disconnect behavior, and latency on
  the Raspberry Pi 5.
