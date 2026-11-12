import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from diagnostic_platform.config import Settings
from diagnostic_platform.control import SimulatedMotorController, SimulatedMotorSequenceService
from diagnostic_platform.drivers import ReplayMeasurementSource
from diagnostic_platform.measurements import (
    DataSource,
    MeasurementQuality,
    motor_measurement_envelopes,
)
from diagnostic_platform.models import MotorMeasurement


class SettingsTests(unittest.TestCase):
    def test_defaults_are_local_simulation(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_environment(Path("/project"))
        self.assertEqual(settings.mode, "simulation")
        self.assertEqual(settings.database_path, Path("/project/diagnostics.db"))

    def test_hardware_mode_is_safely_disabled(self) -> None:
        with patch.dict(os.environ, {"ADS_MODE": "hardware"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Hardware mode is disabled"):
                Settings.from_environment(Path("/project"))


class MeasurementEnvelopeTests(unittest.TestCase):
    def test_simulated_motor_values_include_traceability_metadata(self) -> None:
        measurement = MotorMeasurement(
            12.0, 1.2, None, 30.0, 1.1, None, 7,
            datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
        envelopes = motor_measurement_envelopes(
            measurement,
            device_id="MOTOR-1",
            source=DataSource.SIMULATION,
            session_id=12,
        )
        by_type = {item.measurement_type: item for item in envelopes}
        self.assertEqual(by_type["voltage"].quality, MeasurementQuality.GOOD)
        self.assertEqual(by_type["rpm"].quality, MeasurementQuality.MISSING)
        self.assertEqual(by_type["current"].source, DataSource.SIMULATION)
        self.assertEqual(by_type["current"].session_id, 12)

    def test_uncalibrated_hardware_value_is_not_marked_good(self) -> None:
        measurement = MotorMeasurement(12, 1, 1000, 30, 1, sequence=1)
        envelopes = motor_measurement_envelopes(
            measurement,
            device_id="MOTOR-1",
            source=DataSource.HARDWARE,
            session_id=1,
        )
        by_type = {item.measurement_type: item for item in envelopes}
        self.assertEqual(by_type["voltage"].quality, MeasurementQuality.UNCALIBRATED)
        self.assertEqual(by_type["current"].quality, MeasurementQuality.UNCALIBRATED)
        self.assertEqual(by_type["vibration_rms"].quality, MeasurementQuality.MISSING)


class ReplayDriverTests(unittest.TestCase):
    def test_replay_is_finite_and_requires_connection(self) -> None:
        source = ReplayMeasurementSource([MotorMeasurement(12, 1, 1000, 30, 1)])
        with self.assertRaises(ConnectionError):
            source.read()
        source.connect()
        self.assertEqual(source.read().voltage, 12)
        with self.assertRaises(EOFError):
            source.read()


class BackendSequenceTests(unittest.TestCase):
    def test_sequence_finishes_with_output_disabled(self) -> None:
        controller = SimulatedMotorController()
        sequence = SimulatedMotorSequenceService(controller, interval_seconds=0.001)
        accepted, _ = sequence.start()
        self.assertTrue(accepted)
        deadline = time.monotonic() + 1
        while sequence.status().running and time.monotonic() < deadline:
            time.sleep(0.002)
        self.assertFalse(sequence.status().running)
        self.assertFalse(controller.snapshot().enabled)
        self.assertEqual(controller.snapshot().pwm_percent, 0)

    def test_cancel_immediately_disables_output(self) -> None:
        controller = SimulatedMotorController()
        sequence = SimulatedMotorSequenceService(controller, interval_seconds=0.5)
        sequence.start()
        sequence.cancel()
        self.assertFalse(controller.snapshot().enabled)
        self.assertEqual(controller.snapshot().pwm_percent, 0)


if __name__ == "__main__":
    unittest.main()
