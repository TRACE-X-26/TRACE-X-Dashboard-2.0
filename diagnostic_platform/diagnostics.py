from __future__ import annotations

from .models import (
    DiagnosticReport,
    Finding,
    MotorMeasurement,
    MotorBaseline,
    MotorProfile,
    Severity,
)


class MotorDiagnosticEngine:
    """Transparent first-stage rules; ML can be added behind this interface later."""

    def analyze(
        self,
        profile: MotorProfile,
        measurement: MotorMeasurement,
        baseline: MotorBaseline | None = None,
    ) -> DiagnosticReport:
        findings: list[Finding] = []
        missing = [
            name
            for name in ("voltage", "current")
            if getattr(measurement, name) is None
        ]
        if missing:
            findings.append(
                Finding(
                    "SENSOR_DATA_MISSING",
                    Severity.CRITICAL,
                    f"Required sensor data is missing: {', '.join(missing)}.",
                    ("Disconnected sensor", "Sensor initialization failure"),
                )
            )

        voltage_ratio = (
            measurement.voltage / profile.rated_voltage
            if measurement.voltage is not None
            else None
        )
        current_ratio = (
            measurement.current / profile.rated_current
            if measurement.current is not None
            else None
        )
        rpm_ratio = (
            measurement.rpm / profile.rated_rpm
            if measurement.rpm is not None
            else None
        )

        if measurement.current is not None and measurement.current >= profile.max_current:
            findings.append(
                Finding(
                    "OVERCURRENT",
                    Severity.CRITICAL,
                    "Current exceeds the motor's safe limit.",
                    ("Motor stall", "Shorted winding", "Excess mechanical load"),
                )
            )
        elif current_ratio is not None and current_ratio > 1.15:
            findings.append(
                Finding(
                    "HIGH_CURRENT",
                    Severity.WARNING,
                    f"Current is {(current_ratio - 1) * 100:.0f}% above rated current.",
                    ("Increased mechanical load", "Bearing friction"),
                )
            )

        if voltage_ratio is not None and voltage_ratio < 0.90:
            findings.append(
                Finding(
                    "UNDERVOLTAGE",
                    Severity.WARNING,
                    f"Supply voltage is {(1 - voltage_ratio) * 100:.0f}% below rated voltage.",
                    ("Weak supply", "Wiring voltage drop", "Incorrect supply setting"),
                )
            )

        if measurement.rpm == 0 and current_ratio is not None and current_ratio > 0.5:
            findings.append(
                Finding(
                    "STALL",
                    Severity.CRITICAL,
                    "The motor is drawing current but is not rotating.",
                    ("Locked shaft", "Excess load", "Mechanical obstruction"),
                )
            )
        elif rpm_ratio is not None and rpm_ratio < 0.80:
            findings.append(
                Finding(
                    "LOW_RPM",
                    Severity.WARNING,
                    f"Speed is {(1 - rpm_ratio) * 100:.0f}% below rated speed.",
                    ("Mechanical resistance", "Low supply voltage", "Bearing wear"),
                )
            )

        if baseline is not None:
            if (
                measurement.current is not None
                and baseline.current_mean > 0
                and measurement.current > baseline.current_mean * 1.25
            ):
                difference = (measurement.current / baseline.current_mean - 1) * 100
                findings.append(
                    Finding(
                        "ABOVE_BASELINE_CURRENT",
                        Severity.WARNING,
                        f"Current is {difference:.0f}% above the learned healthy baseline.",
                        ("Increased load", "Bearing friction", "Electrical deterioration"),
                    )
                )
            if (
                measurement.rpm is not None
                and baseline.rpm_mean > 0
                and measurement.rpm < baseline.rpm_mean * 0.80
            ):
                difference = (1 - measurement.rpm / baseline.rpm_mean) * 100
                findings.append(
                    Finding(
                        "BELOW_BASELINE_RPM",
                        Severity.WARNING,
                        f"Speed is {difference:.0f}% below the learned healthy baseline.",
                        ("Mechanical drag", "Excess load", "Supply degradation"),
                    )
                )

        if not findings:
            findings.append(
                Finding("NORMAL", Severity.PASS, "All monitored values are in range.")
            )

        penalty = sum(
            35 if finding.severity is Severity.CRITICAL else 15
            if finding.severity is Severity.WARNING
            else 0
            for finding in findings
        )
        health_score = max(0, 100 - penalty)
        condition = (
            "CRITICAL"
            if any(f.severity is Severity.CRITICAL for f in findings)
            else "WARNING"
            if any(f.severity is Severity.WARNING for f in findings)
            else "HEALTHY"
        )
        return DiagnosticReport(
            profile.device_id,
            health_score,
            condition,
            measurement,
            tuple(findings),
        )
