import unittest

from diagnostic_platform.control import SimulatedMotorController
from diagnostic_platform.multimeter import SimulatedMultimeter


class MultimeterTests(unittest.TestCase):
    def test_all_planned_sensor_channels_are_available(self) -> None:
        controller = SimulatedMotorController()
        reading = SimulatedMultimeter().read(controller.snapshot(), controller.telemetry())
        channels = {item["channel"]: item for item in reading["channels"]}
        self.assertIn("motor_voltage", channels)
        self.assertIn("motor_current", channels)
        self.assertIn("circuit_voltage", channels)
        self.assertIn("circuit_current", channels)
        self.assertIn("probe_voltage", channels)
        self.assertIn("resistance", channels)
        self.assertNotIn("temperature", channels)

    def test_motor_channels_follow_control_output(self) -> None:
        controller = SimulatedMotorController()
        meter = SimulatedMultimeter()
        stopped = meter.read(controller.snapshot(), controller.telemetry())
        controller.command("enable", "enable")
        controller.command("speed", "set_pwm", 75)
        running = meter.read(controller.snapshot(), controller.telemetry())
        stopped_values = {item["channel"]: item["value"] for item in stopped["channels"]}
        running_values = {item["channel"]: item["value"] for item in running["channels"]}
        self.assertEqual(stopped_values["motor_voltage"], 0)
        self.assertGreater(running_values["motor_voltage"], 0)
        self.assertGreater(running_values["motor_current"], 0)


if __name__ == "__main__":
    unittest.main()
