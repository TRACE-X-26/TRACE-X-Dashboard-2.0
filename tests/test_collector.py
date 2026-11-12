import csv
import tempfile
import unittest
from diagnostic_platform.collector import ExperimentRecorder, CHANNELS, validate_measurements
from diagnostic_platform.live import LiveMonitor
import json

class CollectorTests(unittest.TestCase):
    def result(self):
        return {'measurements': {name: dict(value=None, unit=unit, valid=False, timestamp_ms=0) for name, unit in CHANNELS.items()}}

    def test_exclusive_recordings_and_validity(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = ExperimentRecorder(directory, 'test-1'), ExperimentRecorder(directory, 'test-1')
            a.record(self.result()); a.close(); b.close()
            self.assertNotEqual(a.path, b.path)
            with a.path.open() as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0]['test_id'], 'test-1')
            self.assertEqual(rows[0]['value'], '')
            self.assertEqual(rows[0]['valid'], 'False')

    def test_dashboard_invalidates_previous_sample(self):
        result = self.result()
        monitor = LiveMonitor()
        frame = dict(version=1, type='measurement', seq=1, device_id='STM32-ADS', timestamp_ms=100, payload={'result': result})
        result['measurements']['voltage'].update(value=12, valid=True)
        monitor.feed(json.dumps(frame))
        self.assertEqual(monitor.snapshot()['channels']['voltage']['value'], 12)
        result['measurements']['voltage'].update(value=None, valid=False)
        monitor.feed(json.dumps(frame))
        self.assertNotIn('voltage', monitor.snapshot()['channels'])
        result['measurements']['voltage'].update(value=12)
        with self.assertRaises(ValueError): validate_measurements(result)
