import unittest

from diagnostic_platform.protocol import (
    MessageType,
    ProtocolMessage,
    decode_message,
    encode_message,
)
from diagnostic_platform.stm32 import (
    CommunicationTimeout,
    DeviceResponseError,
    HardwareControlDisabled,
    SafeDisconnectError,
    STM32SerialConnection,
    SimulatedSTM32Connection,
)


class FakeSerialTransport:
    def __init__(self, responses=None) -> None:
        self.responses = list(responses or [])
        self.writes = []
        self.closed = False
        self.error_commands = set()
        self.drop_commands = set()

    def write(self, data: bytes) -> int:
        request = decode_message(data)
        self.writes.append(request)
        command = (
            request.payload["command"]
            if request.message_type is MessageType.COMMAND
            else "HEARTBEAT"
        )
        if command in self.drop_commands:
            return len(data)
        if command in self.error_commands:
            response = ProtocolMessage(
                MessageType.ERROR,
                request.sequence + 100,
                "STM32-ADS",
                {"reply_to": request.sequence, "code": "INVALID_STATE", "message": "not ready"},
                request.timestamp_ms,
            )
        else:
            results = {
                "GET_STATUS": {"state": "READY", "faults": []},
                "GET_CAPABILITIES": {
                    "device_id": "STM32-ADS",
                    "measurement_types": ["motor_voltage", "motor_current"],
                    "commands": ["GET_STATUS", "STOP_MOTOR"],
                    "firmware_version": "test-1.0",
                },
                "READ_MEASUREMENTS": {"motor_voltage_v": 12.0, "motor_current_a": 1.0},
                "STOP_MOTOR": {"accepted": True, "state": "READY"},
                "HEARTBEAT": {"alive": True},
            }
            response = ProtocolMessage(
                MessageType.ACK,
                request.sequence + 100,
                "STM32-ADS",
                {"reply_to": request.sequence, "result": results.get(command, {"accepted": True})},
                request.timestamp_ms,
            )
        self.responses.append(encode_message(response))
        return len(data)

    def readline(self) -> bytes:
        return self.responses.pop(0) if self.responses else b""

    def close(self) -> None:
        self.closed = True


class STM32SerialConnectionTests(unittest.TestCase):
    def connection(self, transport, **kwargs):
        return STM32SerialConnection(
            port="/dev/test",
            command_timeout=0.01,
            transport_factory=lambda *_: transport,
            **kwargs,
        )

    def test_status_capabilities_and_measurements(self) -> None:
        transport = FakeSerialTransport()
        connection = self.connection(transport)
        connection.connect()
        self.assertEqual(connection.status()["state"], "READY")
        self.assertEqual(connection.capabilities().firmware_version, "test-1.0")
        self.assertEqual(connection.read_measurements()["motor_voltage_v"], 12.0)
        self.assertTrue(connection.heartbeat()["alive"])
        connection.disconnect()
        self.assertTrue(transport.closed)

    def test_existing_firmware_banner_can_be_probed_without_writing(self) -> None:
        transport = FakeSerialTransport([b"STM32 CONNECTED TO PI\r\n"])
        connection = self.connection(transport)
        connection.connect()
        self.assertEqual(connection.probe_legacy_banner(), "STM32 CONNECTED TO PI")
        self.assertEqual(transport.writes, [])

    def test_motor_commands_are_disabled_by_default(self) -> None:
        transport = FakeSerialTransport()
        connection = self.connection(transport)
        connection.connect()
        with self.assertRaises(HardwareControlDisabled):
            connection.execute("SET_PWM", {"pwm_percent": 50})
        self.assertEqual(transport.writes, [])

    def test_device_error_is_exposed(self) -> None:
        transport = FakeSerialTransport()
        transport.error_commands.add("GET_STATUS")
        connection = self.connection(transport)
        connection.connect()
        with self.assertRaisesRegex(DeviceResponseError, "INVALID_STATE"):
            connection.status()

    def test_command_timeout_is_bounded(self) -> None:
        transport = FakeSerialTransport()
        transport.drop_commands.add("GET_STATUS")
        connection = self.connection(transport)
        connection.connect()
        with self.assertRaises(CommunicationTimeout):
            connection.status()

    def test_control_enabled_disconnect_requires_stop_ack(self) -> None:
        transport = FakeSerialTransport()
        connection = self.connection(transport, allow_motor_control=True)
        connection.connect()
        connection.disconnect()
        self.assertEqual(transport.writes[-1].payload["command"], "STOP_MOTOR")
        self.assertTrue(transport.closed)

    def test_failed_stop_still_closes_transport_and_reports_unsafe_disconnect(self) -> None:
        transport = FakeSerialTransport()
        transport.drop_commands.add("STOP_MOTOR")
        connection = self.connection(transport, allow_motor_control=True)
        connection.connect()
        with self.assertRaises(SafeDisconnectError):
            connection.disconnect()
        self.assertTrue(transport.closed)


class SimulatedSTM32ConnectionTests(unittest.TestCase):
    def test_simulation_adapter_supports_status_measurements_and_commands(self) -> None:
        connection = SimulatedSTM32Connection()
        connection.connect()
        self.assertEqual(connection.status()["source"], "SIMULATION")
        self.assertIsNone(connection.read_measurements()["rpm"])
        self.assertTrue(connection.heartbeat()["alive"])
        connection.execute("START_TEST")
        connection.execute("SET_PWM", {"pwm_percent": 30})
        self.assertEqual(connection.status()["pwm_percent"], 30)
        connection.disconnect()
        self.assertFalse(connection.controller.snapshot().enabled)


if __name__ == "__main__":
    unittest.main()

class BoundedProtocolAdapterTests(unittest.TestCase):
    def test_command_arguments_are_preserved_and_events_do_not_steal_reply(self):
        event=ProtocolMessage(MessageType.EVENT,99,'STM32-ADS',
            {'event':'MOTOR_STOP','run_id':5,'reason':'COMPLETED'},1000)
        transport=FakeSerialTransport([encode_message(event)])
        connection=STM32SerialConnection(port='/dev/test',allow_motor_control=True,
            command_timeout=.01,transport_factory=lambda *_:transport)
        connection.connect()
        args={'pwm_percent':10,'duration_ms':1000,'direction':'FORWARD'}
        connection.execute('START_TEST',args)
        self.assertEqual(transport.writes[-1].payload['arguments'],args)
        self.assertEqual(connection.drain_events(),[event])
        self.assertEqual(connection.drain_events(),[])
        connection.disconnect()

    def test_arm_command_remains_gated(self):
        transport=FakeSerialTransport()
        connection=STM32SerialConnection(port='/dev/test',transport_factory=lambda *_:transport)
        connection.connect()
        with self.assertRaises(HardwareControlDisabled):
            connection.execute('ARM_TEST')
        self.assertEqual(transport.writes,[])
        connection.disconnect()
