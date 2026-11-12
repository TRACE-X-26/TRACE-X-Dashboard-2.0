from __future__ import annotations

import argparse
from pathlib import Path

from .models import MotorProfile
from .sources import SimulatedMotorSource
from .storage import DiagnosticStore
from .workflow import MotorTestRunner


def default_profile() -> MotorProfile:
    return MotorProfile(
        device_id="MOTOR-001",
        rated_voltage=12.0,
        rated_current=2.0,
        rated_rpm=2500,
        winding_resistance=1.2,
        max_current=3.0,
        max_temperature=80.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simulated motor diagnostic")
    parser.add_argument("--scenario", choices=SimulatedMotorSource.SCENARIOS, default="healthy")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--database", type=Path, default=Path("diagnostics.db"))
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")

    profile = default_profile()
    source = SimulatedMotorSource(profile, args.scenario, seed=42)
    store = DiagnosticStore(args.database)
    runner = MotorTestRunner(source, store)

    print(f"Device: {profile.device_id} | Scenario: {args.scenario}")
    try:
        session_id, report = runner.run(profile, args.scenario, args.samples)
        summary = store.session_summary(session_id)
        m = report.measurement
        value = lambda number, suffix: "N/A" if number is None else f"{number:.2f}{suffix}"
        print(
            f"Session {session_id} complete: {summary['sample_count']} samples, "
            f"health {report.health_score}%, condition {report.condition}"
        )
        print(
            f"Final measurement: voltage={value(m.voltage, 'V')} "
            f"current={value(m.current, 'A')} rpm={value(m.rpm, '')} "
            f"temperature={value(m.temperature, 'C')} power={value(m.input_power, 'W')}"
        )
        for finding in report.findings:
            print(f"[{finding.severity.value}] {finding.code}: {finding.message}")
        print(f"Saved to {args.database}")
    except (TimeoutError, RuntimeError) as exc:
        print(f"Test stopped in state {runner.state.value}: {exc}")
        raise SystemExit(2) from exc
    finally:
        store.close()


if __name__ == "__main__":
    main()
