import unittest

from diagnostic_platform.control import SimulatedMotorController


class MotorControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = SimulatedMotorController()

    def command(self, action: str, value=None):
        return self.controller.command(f"test-{action}", action, value)

    def test_safe_enable_and_speed_sequence(self) -> None:
        self.assertTrue(self.command("enable").accepted)
        response = self.command("set_pwm", 60)
        self.assertTrue(response.accepted)
        self.assertEqual(response.state.pwm_percent, 60)
        telemetry = self.controller.telemetry()
        self.assertGreater(telemetry.rpm, 0)
        self.assertGreater(telemetry.current, 0)

    def test_pwm_is_rejected_while_disabled(self) -> None:
        response = self.command("set_pwm", 50)
        self.assertFalse(response.accepted)
        self.assertIn("Enable", response.message)

    def test_direction_change_requires_stopped_motor(self) -> None:
        self.command("enable")
        self.command("set_pwm", 40)
        response = self.command("set_direction", "REVERSE")
        self.assertFalse(response.accepted)
        self.assertEqual(response.state.direction.value, "FORWARD")
        self.command("set_pwm", 0)
        self.assertTrue(self.command("set_direction", "REVERSE").accepted)

    def test_emergency_stop_latches_and_blocks_output(self) -> None:
        self.command("enable")
        self.command("set_pwm", 80)
        stopped = self.command("emergency_stop")
        self.assertTrue(stopped.state.emergency_stop)
        self.assertFalse(stopped.state.enabled)
        self.assertEqual(stopped.state.pwm_percent, 0)
        self.assertFalse(self.command("enable").accepted)
        self.assertTrue(self.command("reset_emergency_stop").accepted)
        self.assertTrue(self.command("enable").accepted)


if __name__ == "__main__":
    unittest.main()
