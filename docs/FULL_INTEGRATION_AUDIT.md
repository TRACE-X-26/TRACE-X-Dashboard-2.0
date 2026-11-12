# TRACE-X integration audit — November 6, 2026

Baseline: 69c8575 plus the local, tested bounded-firmware delivery documented in
BOUNDED_STM32_MOTOR_TEST.md. No board is connected to this Mac; Pi-installed files,
flashed identity, reset/interlock/calibration and powered safety remain unverified.

- React/TypeScript pages, styling/navigation, charts, simulation controls, guided
  circuit workflows, CSV import and profiles/history already exist. Preserve them.
- FastAPI /ws/tests runs simulation sessions; it is not a physical test runner.
  Motor ramp owns separate simulation state; there is no central physical owner.
- Passive STM32 live monitor supports text/JSON, source labels and staleness but
  stores only current readings. Temperature text lacks a dedicated live tile.
- ADS v1 request adapter and bounded firmware now exist locally; gates default
  off, a physical interlock hook is deliberately unresolved, and serial frames
  previously had no transport checksum. No output-enabled image is approved.
- Existing motor rule scores use demo profile limits; they cannot be presented
  as calibrated hardware health. Recorded CSVs preserve quality flags; target
  PWM labels/load masses do not constitute validated healthy baselines.
- SQLite already stores legacy sessions/findings/profiles/baselines, imported
  CSV records, events and circuit captures. Add versioned automated-run storage
  without changing/deleting legacy records. Recover interrupted runs as incomplete.
- Circuit 4 voltage reference rules are provisional. Probe ADC scaling/protection,
  range and connection detection are not commissioned; resistance/continuity
  excitation is not documented. Such physical procedures must be unavailable.
- Pi configure.py incorrectly wraps WorkingDirectory in literal quotes, matching
  the reported not-absolute error. Runtime.env/database preservation already
  exists; strengthen service validation, health checks and upgrade documentation.

Implementation acceptance is software/simulator completeness, not physical
commissioning. A procedure with unknown parameters or unsupported firmware must
be listed as unavailable rather than executed or represented as successful.
