import unittest

from diagnostic_platform.diagnostics import MotorDiagnosticEngine
from diagnostic_platform.models import MotorMeasurement, MotorProfile


class MotorDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = MotorProfile("M1", 12, 2, 2500, 1.2, 3, 80)
        self.engine = MotorDiagnosticEngine()

    def codes(self, measurement: MotorMeasurement) -> set[str]:
        report = self.engine.analyze(self.profile, measurement)
        return {finding.code for finding in report.findings}

    def test_healthy_motor(self) -> None:
        measurement = MotorMeasurement(12, 1.9, 2450, 40, 1.2)
        report = self.engine.analyze(self.profile, measurement)
        self.assertEqual(report.condition, "HEALTHY")
        self.assertEqual(report.health_score, 100)

    def test_stall_uses_current_and_rpm(self) -> None:
        measurement = MotorMeasurement(12, 3.2, 0, 55, 1.2)
        codes = self.codes(measurement)
        self.assertIn("STALL", codes)
        self.assertIn("OVERCURRENT", codes)

    def test_undervoltage_and_low_rpm(self) -> None:
        measurement = MotorMeasurement(8.5, 1.7, 1600, 40, 1.2)
        codes = self.codes(measurement)
        self.assertIn("UNDERVOLTAGE", codes)
        self.assertIn("LOW_RPM", codes)

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MotorProfile("M1", 0, 2, 2500, 1.2, 3, 80)


if __name__ == "__main__":
    unittest.main()

