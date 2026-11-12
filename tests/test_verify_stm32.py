import unittest
from unittest.mock import patch

from diagnostic_platform.drivers import DeviceCapabilities
from diagnostic_platform.verify_stm32 import discover_serial_port, verify_connection


class FakeConnection:
    def __init__(self, **settings) -> None:
        self.settings = settings
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def status(self) -> dict:
        return {
            "state": "SAFE_IDLE",
            "faults": [],
            "hardware_control": False,
        }

    def capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(
            device_id="STM32-ADS",
            measurement_types=(),
            commands=("GET_STATUS", "GET_CAPABILITIES", "GET_FAULTS"),
            firmware_version="0.1.0-communication-only",
        )

    def execute(self, command: str) -> dict:
        self.last_command = command
        return {"faults": [], "state": "SAFE_IDLE"}

    def heartbeat(self) -> dict:
        return {"alive": True, "state": "SAFE_IDLE", "hardware_control": False}


class VerifySTM32Tests(unittest.TestCase):
    def test_prefers_stable_by_id_path(self) -> None:
        with patch(
            "diagnostic_platform.verify_stm32.glob",
            side_effect=[
                ["/dev/serial/by-id/usb-STMicroelectronics_STM32_STLink"],
                [],
                ["/dev/ttyACM0"],
                [],
            ],
        ):
            self.assertEqual(
                discover_serial_port(),
                "/dev/serial/by-id/usb-STMicroelectronics_STM32_STLink",
            )

    def test_runs_only_read_only_connection_checks(self) -> None:
        created = []

        def factory(**settings):
            connection = FakeConnection(**settings)
            created.append(connection)
            return connection

        result = verify_connection("/dev/ttyACM0", connection_factory=factory)

        self.assertEqual(result["state"], "SAFE_IDLE")
        self.assertTrue(result["heartbeat_alive"])
        self.assertFalse(result["hardware_control"])
        self.assertFalse(created[0].settings["allow_motor_control"])
        self.assertEqual(created[0].last_command, "GET_FAULTS")
        self.assertTrue(created[0].disconnected)


if __name__ == "__main__":
    unittest.main()
