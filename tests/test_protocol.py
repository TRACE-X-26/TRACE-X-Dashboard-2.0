import unittest
from datetime import datetime, timezone

from diagnostic_platform.models import MotorMeasurement
from diagnostic_platform.protocol import (
    CommandName,
    MessageType,
    ProtocolError,
    ProtocolMessage,
    command_message,
    decode_measurement,
    decode_message,
    encode_measurement,
    encode_message,
)


class ProtocolTests(unittest.TestCase):
    def test_measurement_round_trip(self) -> None:
        original = MotorMeasurement(12.1, 1.8, None, 35.0, 1.2, None, 7,
                                    datetime(2026, 9, 25, tzinfo=timezone.utc))
        decoded = decode_measurement(encode_measurement(original))
        self.assertEqual(decoded, original)

    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            decode_measurement("not json")

    def test_command_message_round_trip(self) -> None:
        original = command_message(
            CommandName.SET_PWM, 12, arguments={"pwm_percent": 40}
        )
        decoded = decode_message(encode_message(original))
        self.assertEqual(decoded, original)

    def test_unsupported_protocol_version_is_rejected(self) -> None:
        message = ProtocolMessage(
            MessageType.HEARTBEAT, 1, "device", {}, 1, version=99
        )
        with self.assertRaisesRegex(ProtocolError, "version"):
            encode_message(message)

    def test_oversized_protocol_frame_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "maximum size"):
            decode_message(b"{" + b"x" * 5000)


if __name__ == "__main__":
    unittest.main()
