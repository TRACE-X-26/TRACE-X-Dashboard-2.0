import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from diagnostic_platform.live import LiveMonitor

from diagnostic_platform.protocol import (
    CommandName,
    MessageType,
    ProtocolMessage,
    command_message,
    decode_message,
    encode_message,
)


ROOT = Path(__file__).resolve().parents[1]


class FirmwareProtocolCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("cc") or shutil.which("clang")
        if compiler is None:
            raise unittest.SkipTest("No host C compiler is installed")
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls.executable = Path(cls._temporary_directory.name) / "firmware_protocol"
        subprocess.run(
            [
                compiler,
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT / "ADS/Core/Inc"),
                str(ROOT / "ADS/Core/Src/ads_protocol.c"),
                str(ROOT / "ADS/Core/Src/ads_test.c"),
                str(ROOT / "tests/firmware_protocol_harness.c"),
                "-o",
                str(cls.executable),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def exchange(self, frames: list[bytes]) -> list[dict]:
        completed = subprocess.run(
            [str(self.executable)],
            input=b"".join(frames),
            check=True,
            capture_output=True,
        )
        responses = []
        for line in completed.stdout.splitlines():
            # Validate every C response with the production Python decoder.
            decode_message(line + b"\n")
            responses.append(json.loads(line))
        return responses

    def test_safe_commands_match_backend_envelope(self) -> None:
        requests = [
            command_message(CommandName.GET_STATUS, 1),
            command_message(CommandName.GET_CAPABILITIES, 2),
            command_message(CommandName.GET_FAULTS, 3),
            ProtocolMessage(MessageType.HEARTBEAT, 4, "raspberry-pi", {}, 1000),
        ]
        responses = self.exchange([encode_message(request) for request in requests])

        self.assertEqual([item["payload"]["reply_to"] for item in responses], [1, 2, 3, 4])
        self.assertEqual(responses[0]["type"], "status")
        self.assertEqual(responses[0]["payload"]["result"]["state"], "SAFE_IDLE")
        self.assertFalse(responses[0]["payload"]["result"]["hardware_control"])
        self.assertEqual(responses[1]["type"], "capabilities")
        self.assertEqual(responses[1]["payload"]["result"]["measurement_types"], [])
        self.assertEqual(responses[2]["type"], "ack")
        self.assertEqual(responses[3]["type"], "ack")
        self.assertTrue(responses[3]["payload"]["result"]["alive"])

    def test_measurement_and_motor_commands_are_explicitly_disabled(self) -> None:
        requests = [
            command_message(CommandName.READ_MEASUREMENTS, 11),
            command_message(CommandName.SET_PWM, 12, arguments={"pwm_percent": 50}),
            command_message(CommandName.SET_DIRECTION, 13, arguments={"direction": "FORWARD"}),
            command_message(CommandName.START_TEST, 14),
            command_message(CommandName.STOP_TEST, 15),
            command_message(CommandName.STOP_MOTOR, 16),
        ]
        responses = self.exchange([encode_message(request) for request in requests])

        self.assertEqual(responses[0]["type"], "measurement")
        for item in responses[0]["payload"]["result"]["measurements"].values():
            self.assertFalse(item["valid"])
            self.assertIsNone(item["value"])
        self.assertEqual(
            [response["payload"]["code"] for response in responses[1:]],
            ["CONTROL_DISABLED"] * 5,
        )
        self.assertTrue(all(response["type"] == "error" for response in responses[1:]))

    def test_safety_callback_at_exact_timeout(self):
        subprocess.run([str(self.executable), '--safety'], check=True)

    def test_normal_and_repeated_shutdown_requests(self):
        subprocess.run([str(self.executable), "--normal-shutdown"], check=True)

    def test_acquisition_fixed_point_units_and_timestamps(self):
        output = subprocess.check_output([str(self.executable), '--samples'],
            input=encode_message(command_message(CommandName.READ_MEASUREMENTS, 1)))
        channels = json.loads(output)['payload']['result']['measurements']
        self.assertEqual(channels['voltage'], dict(value=12.345, unit='V', valid=True, timestamp_ms=42))
        self.assertEqual(channels['current']['value'], -.125)
        self.assertIsNone(channels['temperature']['value'])

    def test_live_polling_normalizes_firmware_measurements_without_motor_commands(self):
        writes = []
        stopped = Event()

        class FirmwareTransport:
            def write(self, request):
                writes.append(decode_message(request))
                self.reply = subprocess.check_output(
                    [str(FirmwareProtocolCompatibilityTests.executable), '--samples'], input=request
                )
                return len(request)

            def readline(self):
                return self.reply

            def close(self):
                stopped.set()

        monitor = LiveMonitor('/dev/test', protocol='json', transport_factory=lambda *_: FirmwareTransport())
        # Stop after observing the first complete read, without sleeping or opening USB.
        snapshots = []
        original_wait = monitor._stop.wait

        def finish_after_poll(delay):
            if delay == .5:
                snapshots.append(monitor.snapshot())
                monitor._stop.set()
            return original_wait(delay)

        with patch.object(monitor._stop, 'wait', side_effect=finish_after_poll):
            monitor._run()

        self.assertTrue(stopped.is_set())
        self.assertEqual([frame.message_type for frame in writes], [MessageType.HEARTBEAT, MessageType.COMMAND])
        self.assertEqual(writes[1].payload['command'], 'READ_MEASUREMENTS')
        snapshot, = snapshots
        self.assertTrue(snapshot['connected'])
        self.assertEqual(snapshot['channels']['current']['value'], -.125)
        self.assertEqual(snapshot['channels']['current']['timestamp_ms'], 43)
        self.assertNotIn('temperature', snapshot['channels'])
        self.assertIn('TEMPERATURE_INVALID', snapshot['warnings'])
        self.assertFalse(monitor.snapshot()['connected'])

    def test_malformed_frames_and_serial_resynchronization(self):
        good = encode_message(command_message(CommandName.GET_STATUS, 2))
        bad = [good[:-2] + b',}\n', good.replace(b'"version":1', b'"version":1,"version":1'),
               good.replace(b'"seq":2', b'"seq":2.5'), b'x' * 513 + b'\n',
               good.replace(b'"arguments":{}', b'"arguments":[]'), b'{}garbage\n']
        for frame in bad:
            responses = self.exchange([frame, good])
            self.assertEqual(responses[0]['type'], 'error')
            self.assertEqual(responses[-1]['type'], 'status')

    def test_invalid_version_returns_correlated_error(self) -> None:
        frame = (
            b'{"version":2,"type":"heartbeat","seq":91,'
            b'"device_id":"raspberry-pi","timestamp_ms":1,"payload":{}}\n'
        )
        response = self.exchange([frame])[0]
        self.assertEqual(response["type"], "error")
        self.assertEqual(response["payload"]["reply_to"], 91)
        self.assertEqual(response["payload"]["code"], "UNSUPPORTED_VERSION")


if __name__ == "__main__":
    unittest.main()
