import tempfile
import unittest
from pathlib import Path

from diagnostic_platform.models import MotorProfile
from diagnostic_platform.sources import SimulatedMotorSource
from diagnostic_platform.storage import DiagnosticStore
from diagnostic_platform.workflow import MotorTestRunner, TestState


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = DiagnosticStore(Path(self.tempdir.name) / "test.db")
        self.profile = MotorProfile("M1", 12, 2, 2500, 1.2, 3, 80)

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def test_completed_test_is_persisted(self) -> None:
        source = SimulatedMotorSource(self.profile, "healthy", seed=1)
        runner = MotorTestRunner(source, self.store)
        session_id, report = runner.run(self.profile, "healthy", 5)
        summary = self.store.session_summary(session_id)
        self.assertEqual(runner.state, TestState.COMPLETE)
        self.assertEqual(summary["sample_count"], 5)
        self.assertEqual(summary["condition"], report.condition)

    def test_communication_loss_is_recorded(self) -> None:
        source = SimulatedMotorSource(self.profile, "communication_loss", seed=1)
        runner = MotorTestRunner(source, self.store)
        with self.assertRaises(TimeoutError):
            runner.run(self.profile, "communication_loss", 6)
        self.assertEqual(runner.state, TestState.COMMUNICATION_FAULT)

    def test_sensor_failure_stops_test(self) -> None:
        source = SimulatedMotorSource(self.profile, "sensor_failure", seed=1)
        runner = MotorTestRunner(source, self.store)
        with self.assertRaises(RuntimeError):
            runner.run(self.profile, "sensor_failure", 3)
        self.assertEqual(runner.state, TestState.SENSOR_FAULT)

    def test_completed_test_can_become_adaptive_baseline(self) -> None:
        source = SimulatedMotorSource(self.profile, "healthy", seed=1)
        runner = MotorTestRunner(source, self.store)
        session_id, _ = runner.run(self.profile, "healthy", 5)
        baseline = self.store.create_baseline(session_id, "2026-10-12T00:00:00+00:00")
        self.assertEqual(baseline.device_id, "M1")
        self.assertEqual(baseline.sample_count, 5)
        self.assertIsNotNone(self.store.get_baseline("M1"))

    def test_stalled_motor_triggers_safety_trip(self) -> None:
        source = SimulatedMotorSource(self.profile, "stalled", seed=1)
        runner = MotorTestRunner(source, self.store)
        with self.assertRaisesRegex(RuntimeError, "safety stop"):
            runner.run(self.profile, "stalled", 5)
        self.assertEqual(runner.state, TestState.SAFETY_TRIP)


if __name__ == "__main__":
    unittest.main()
