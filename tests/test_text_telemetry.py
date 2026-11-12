import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from diagnostic_platform.live import LiveMonitor
from diagnostic_platform.text_telemetry import PlainTextMotorParser, SerialLineDecoder
from diagnostic_platform.verify_stm32 import verify_telemetry


LINES = ['ENCODER: NO PULSES DETECTED', 'Motor RPM: 0', 'INA219: CONNECTED',
         'Voltage: 0.004 V', 'Current: 0.000 A', 'Power: 0.000 W']
TIMESTAMP = '2026-11-02T12:00:00+00:00'


class TextTelemetryTests(unittest.TestCase):
    def cycle(self, parser, lines=LINES, start=100):
        updates = [parser.feed(line, received=start + i * .01, timestamp=TIMESTAMP) for i, line in enumerate(lines)]
        return updates[-1]

    def test_actual_zero_readings_emit_complete_hardware_cycle(self):
        update = self.cycle(PlainTextMotorParser())
        self.assertEqual(update.sample['motor_rpm'], 0)
        self.assertEqual(update.sample['voltage'], .004)
        self.assertEqual(update.sample['current'], 0)
        self.assertEqual(update.sample['power'], 0)
        self.assertEqual(update.sample['encoder_status'], 'NO PULSES DETECTED')
        self.assertEqual(update.sample['ina219_status'], 'CONNECTED')
        self.assertEqual(update.sample['timestamp'], TIMESTAMP)
        self.assertEqual(update.sample['source'], 'stm32_serial')
        self.assertEqual(update.sample['power_origin'], 'REPORTED_BY_STM32')

    def test_never_invents_power_or_carries_previous_cycle_values(self):
        parser = PlainTextMotorParser()
        self.assertIsNotNone(self.cycle(parser).sample)
        for i, line in enumerate(LINES[:-1]):
            self.assertIsNone(parser.feed(line, received=101 + i * .01).sample)
        self.assertIn('power', parser.missing_fields)

    def test_starts_midcycle_then_waits_for_encoder_boundary(self):
        parser = PlainTextMotorParser()
        for line in LINES[3:]:
            self.assertIsNone(parser.feed(line, received=100).sample)
        self.assertIsNotNone(self.cycle(parser, start=101).sample)

    def test_repeated_fields_and_timeout_do_not_merge_cycles(self):
        parser = PlainTextMotorParser()
        self.cycle(parser, LINES[:-1])
        repeated = parser.feed('Voltage: 12 V', received=101)
        self.assertIn('INCOMPLETE_FRAME_RESTARTED', repeated.warnings)
        self.assertIsNone(parser.feed('Power: 1 W', received=101.1).sample)
        self.cycle(parser, LINES[:-1], start=102)
        expired = parser.feed('Power: 1 W', received=106)
        self.assertIn('INCOMPLETE_FRAME_TIMEOUT', expired.warnings)
        self.assertIsNone(expired.sample)

    def test_malformed_nonfinite_interleaved_and_wrong_units_rejected(self):
        for invalid in ['Voltage: nan V', 'Current: inf A', 'Power: 1e999 W',
                        'Voltage: -1 V', 'Current: 12 mA', 'Motor RPM: nonsense',
                        'Current: 0.057 ENCODER: NO PULSES DETECTED']:
            parser = PlainTextMotorParser()
            self.cycle(parser, LINES[:3])
            update = parser.feed(invalid, received=101)
            self.assertTrue(update.invalidate, invalid)
            self.assertIsNone(update.sample)

    def test_connection_status_and_noise(self):
        parser = PlainTextMotorParser()
        for line in ['INA219: DISCONNECTED', 'INA219: NOT DETECTED', 'INA219: ERROR', 'ENCODER: DISCONNECTED']:
            update = parser.feed(line)
            self.assertTrue(update.invalidate)
        self.assertFalse(parser.feed('unrelated debug output').recognized)
        self.assertIsNotNone(self.cycle(parser).sample)

    def test_signed_rpm_is_preserved(self):
        lines = ['ENCODER: PULSES DETECTED', 'Motor RPM: -78', *LINES[2:]]
        self.assertEqual(self.cycle(PlainTextMotorParser(), lines).sample['motor_rpm'], -78)

    def test_fragmented_crlf_oversized_and_utf8_recovery(self):
        decoder = SerialLineDecoder(limit=50)
        self.assertEqual(decoder.feed(b'Voltage: 0.00'), ([], []))
        self.assertEqual(decoder.feed(b'4 V\r\n'), (['Voltage: 0.004 V'], []))
        self.assertIn('FRAME_TOO_LARGE', decoder.feed(b'x' * 51 + b'\n')[1])
        self.assertIn('INVALID_UTF8', decoder.feed(b'\xff\n')[1])
        self.assertEqual(decoder.feed(b'Power: 0 W\n')[0], ['Power: 0 W'])

    def test_live_monitor_complete_partial_failure_and_stale(self):
        monitor = LiveMonitor(); monitor._connected = True
        with patch('diagnostic_platform.live.time.monotonic', return_value=100):
            for line in LINES:
                monitor.feed(line)
            snapshot = monitor.snapshot()
        self.assertEqual(snapshot['complete_motor_frames'], 1)
        self.assertTrue(snapshot['motor_sample']['hardware_connected'])
        self.assertEqual(snapshot['motor_sample']['current'], 0)
        with patch('diagnostic_platform.live.time.monotonic', return_value=104):
            self.assertTrue(monitor.snapshot()['motor_sample']['stale'])
            monitor.feed('INA219: DISCONNECTED')
        self.assertIsNone(monitor.snapshot()['motor_sample'])
        self.assertNotIn('voltage', monitor.snapshot()['channels'])

    def test_ads_json_measurement_still_exposes_real_complete_sample(self):
        from diagnostic_platform.collector import CHANNELS
        values = {'voltage': .004, 'current': 0, 'power': 0, 'temperature': None, 'rpm': 0}
        frame = {'version': 1, 'type': 'measurement', 'seq': 1, 'device_id': 'STM32-ADS', 'timestamp_ms': 100,
                 'payload': {'result': {'measurements': {name: {'value': values[name], 'unit': unit,
                           'valid': values[name] is not None, 'timestamp_ms': 100} for name, unit in CHANNELS.items()}}}}
        monitor = LiveMonitor(); monitor._connected = True
        monitor.feed(json.dumps(frame))
        sample = monitor.snapshot()['motor_sample']
        self.assertEqual(sample['format'], 'ads_json_v1')
        self.assertEqual(sample['source'], 'stm32_serial')
        self.assertEqual(sample['ina219_status'], 'NOT_REPORTED')
        self.assertEqual(sample['power'], 0)

    def test_bad_flat_json_invalidates_prior_complete_sample_and_avoids_infinite_power(self):
        monitor = LiveMonitor()
        for line in LINES:
            monitor.feed(line)
        self.assertIsNotNone(monitor.snapshot()['motor_sample'])
        monitor.feed('{"mode":"MOTOR","voltage":"bad","current":0,"rpm":0,"power":0}')
        self.assertIsNone(monitor.snapshot()['motor_sample'])
        self.assertNotIn('voltage', monitor.snapshot()['channels'])
        monitor.feed('{"mode":"MOTOR","voltage":1e308,"current":1e308,"rpm":0}')
        self.assertNotIn('input_power', monitor.snapshot()['channels'])
        json.dumps(monitor.snapshot(), allow_nan=False)

    def test_api_and_websocket_publish_hardware_and_keep_simulation_separate(self):
        import api.main as api_main
        from fastapi.testclient import TestClient
        old_database, old_monitor = api_main.DATABASE_PATH, api_main.live_monitor
        monitor = LiveMonitor(); monitor._connected = True
        with tempfile.TemporaryDirectory() as directory:
            api_main.DATABASE_PATH, api_main.live_monitor = Path(directory) / 'test.db', monitor
            try:
                with TestClient(api_main.app) as client:
                    for line in LINES:
                        monitor.feed(line)
                    sample = client.get('/api/live/motor').json()['motor_sample']
                    self.assertEqual(sample['source'], 'stm32_serial')
                    self.assertTrue(sample['hardware_connected'])
                    self.assertEqual(sample['voltage'], .004)
                    with client.websocket_connect('/ws/live') as socket:
                        self.assertEqual(socket.receive_json()['motor_sample']['source'], 'stm32_serial')
                    self.assertEqual(client.get('/api/motor/status').json()['mode'], 'simulation')
            finally:
                api_main.DATABASE_PATH, api_main.live_monitor = old_database, old_monitor

    def test_serial_reader_recovers_fragments_and_records_disconnect_without_writes(self):
        monitor = LiveMonitor('test')
        data = ('\n'.join(LINES) + '\n').encode()

        class Transport:
            chunks = iter([data[:40], data[40:]])
            closed = False
            def read(self, size):
                try:
                    return next(self.chunks)
                except StopIteration:
                    raise OSError('USB removed')
            def close(self):
                self.closed = True

        transport = Transport()
        monitor.transport_factory = lambda *_: transport
        monitor._run()
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot['complete_motor_frames'], 1)
        self.assertFalse(snapshot['hardware_connected'])
        self.assertTrue(snapshot['motor_sample']['stale'])
        self.assertIn('USB removed', snapshot['error'])
        self.assertTrue(transport.closed)


class FakeStream:
    """No write method: passive verification must not attempt commands."""
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def read(self, size):
        return next(self.chunks, b'')

    def close(self):
        self.closed = True


class VerifyTextTelemetryTests(unittest.TestCase):
    def test_auto_detects_text_without_any_write_and_closes_port(self):
        data = ('\r\n'.join(LINES) + '\r\n').encode()
        stream = FakeStream([data[:20], data[20:80], data[80:]])
        result = verify_telemetry('/dev/test', transport_factory=lambda *_: stream)
        self.assertEqual(result['format'], 'plain_text')
        self.assertEqual(result['motor_sample']['voltage'], .004)
        self.assertTrue(result['motor_sample']['hardware_connected'])
        self.assertFalse(result['commands_sent'])
        self.assertFalse(result['hardware_safety_verified'])
        self.assertTrue(stream.closed)

    def test_timeout_and_incomplete_frames_close_port(self):
        for chunks in [[], [b'ENCODER: NO PULSES DETECTED\nMotor RPM: 0\n']]:
            stream = FakeStream(chunks)
            with self.assertRaises(TimeoutError):
                verify_telemetry('/dev/test', timeout=.001, transport_factory=lambda *_: stream)
            self.assertTrue(stream.closed)

    def test_bad_data_recovers_then_accepts_real_cycle(self):
        data = ('INA219: NOT DETECTED\nVoltage: bad V\n' + '\n'.join(LINES) + '\n').encode()
        result = verify_telemetry('/dev/test', transport_factory=lambda *_: FakeStream([data]))
        self.assertEqual(result['format'], 'plain_text')
        self.assertIn('INA219_UNAVAILABLE', result['warnings'])

    def test_passive_json_support_is_retained(self):
        frame = {'version': 1, 'type': 'status', 'seq': 1, 'device_id': 'STM32-ADS', 'timestamp_ms': 10,
                 'payload': {'result': {'state': 'SAFE_IDLE', 'hardware_control': False}}}
        stream = FakeStream([(json.dumps(frame) + '\n').encode()])
        result = verify_telemetry('/dev/test', transport_factory=lambda *_: stream)
        self.assertEqual(result['format'], 'ads_json_v1')
        self.assertFalse(result['commands_sent'])
        self.assertTrue(stream.closed)

    def test_serial_exception_closes_port(self):
        stream = FakeStream([])
        stream.read = lambda _: (_ for _ in ()).throw(OSError('USB disconnected'))
        with self.assertRaisesRegex(OSError, 'USB disconnected'):
            verify_telemetry('/dev/test', transport_factory=lambda *_: stream)
        self.assertTrue(stream.closed)

class OptionalTemperatureTests(unittest.TestCase):
    def test_temperature_zero_and_disconnect_are_independent_of_rpm(self):
        from diagnostic_platform.live import LiveMonitor
        monitor=LiveMonitor();monitor._connected=True
        monitor.feed('Motor Temperature: 0.000 C')
        self.assertEqual(monitor.snapshot()['channels']['temperature']['value'],0)
        monitor.feed('TEMPERATURE SENSOR: NOT DETECTED')
        self.assertNotIn('temperature',monitor.snapshot()['channels'])
    def test_invalid_temperature_is_not_a_valid_zero(self):
        from diagnostic_platform.live import LiveMonitor
        monitor=LiveMonitor();monitor._connected=True
        monitor.feed('Motor Temperature: 25.000 C');monitor.feed('Motor Temperature: nan C')
        self.assertNotIn('temperature',monitor.snapshot()['channels'])
