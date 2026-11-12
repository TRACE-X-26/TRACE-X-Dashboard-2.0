import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.main as api_main
from diagnostic_platform.live import LiveMonitor
from diagnostic_platform.physical_circuits import start_capture, arm_capture, capture_reading


# Synthetic unit-test fixture only; never installed as the user's circuit.
ASSET = {'asset_id': 'TEST-DIVIDER', 'name': 'Synthetic divider', 'supply_voltage': 10,
         'components': 'R1=1k, R2=1k', 'connections': 'VCC-R1-TP1-R2-GND',
         'test_points': [{'point_id': 'TP1', 'label': 'Midpoint', 'instruction': 'Probe TP1 to GND',
                          'channel': 'test_point_voltage', 'minimum': 4.8, 'maximum': 5.2}]}


class PhysicalCircuitTests(unittest.TestCase):
    def setUp(self):
        self.monitor = LiveMonitor()
        self.monitor._connected = True

    def reading(self, value=5.01, **extra):
        self.monitor.feed(json.dumps({'mode': 'CIRCUIT', 'asset_id': 'TEST-DIVIDER', 'test_point_id': 'TP1',
                                     'test_point_voltage_V': value, **extra}))

    def test_no_motor_mixing_or_divider_double_correction(self):
        self.monitor.feed('Voltage: 12 V')
        self.reading()
        snapshot = self.monitor.snapshot()
        self.assertEqual(snapshot['channels']['voltage']['value'], 12)
        self.assertEqual(snapshot['circuit_channels'][0]['value'], 5.01)
        self.assertEqual(snapshot['circuit_channels'][0]['quality'], 'UNCALIBRATED')

    def test_probe_gate_new_sample_and_provisional_report(self):
        session = start_capture(ASSET)
        self.reading()
        with self.assertRaisesRegex(ValueError, 'Confirm probe'):
            capture_reading(session, self.monitor.snapshot())
        arm_capture(session, 'TP1')
        with self.assertRaisesRegex(ValueError, 'new reading'):
            capture_reading(session, self.monitor.snapshot())
        self.reading()
        result = capture_reading(session, self.monitor.snapshot())
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['condition'], 'WITHIN_CONFIGURED_RANGES')
        self.assertNotIn('health_score', result)

    def test_wrong_asset_point_invalid_and_disconnected_are_rejected(self):
        for change in ({'asset_id': 'OTHER'}, {'test_point_id': 'TP2'}, {'valid': False}):
            session = arm_capture(start_capture(ASSET), 'TP1')
            monitor = LiveMonitor(); monitor._connected = True
            monitor.feed(json.dumps({'mode': 'CIRCUIT', 'asset_id': 'TEST-DIVIDER', 'test_point_id': 'TP1',
                                     'test_point_voltage_V': 5, **change}))
            with self.assertRaises(ValueError):
                capture_reading(session, monitor.snapshot())
        session = arm_capture(start_capture(ASSET), 'TP1')
        self.reading()
        self.monitor._connected = False
        with self.assertRaisesRegex(ValueError, 'disconnected'):
            capture_reading(session, self.monitor.snapshot())

    def test_stale_and_outside_range(self):
        session = arm_capture(start_capture(ASSET), 'TP1')
        self.reading(2)
        snapshot = self.monitor.snapshot()
        snapshot['circuit_channels'][0]['quality'] = 'STALE'
        with self.assertRaises(ValueError):
            capture_reading(session, snapshot)
        self.assertEqual(capture_reading(session, self.monitor.snapshot())['condition'], 'ABNORMAL_READING')

    def test_api_persists_asset_snapshot_and_capture_without_actuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            database, monitor = api_main.DATABASE_PATH, api_main.live_monitor
            api_main.DATABASE_PATH = Path(tmp) / 'api.db'
            api_main.live_monitor = self.monitor
            try:
                with TestClient(api_main.app) as client:
                    self.assertTrue(any(a['asset_id'] == 'CIRCUIT-4-LM324' for a in client.get('/api/circuits/assets').json()))
                    self.assertEqual(client.post('/api/circuits/assets', json=ASSET).status_code, 201)
                    session = client.post('/api/circuits/captures', json={'asset_id': ASSET['asset_id']}).json()
                    url = f"/api/circuits/captures/{session['id']}"
                    self.assertEqual(client.post(url + '/arm', json={'point_id': 'TP1', 'probe_confirmed': False}).status_code, 422)
                    self.assertEqual(client.post(url + '/arm', json={'point_id': 'TP1', 'probe_confirmed': True}).status_code, 200)
                    self.reading()
                    result = client.post(url + '/capture')
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()['state'], 'COMPLETE')
                    self.assertEqual(client.post(url + '/capture').status_code, 409)
                    self.assertEqual(len(client.get('/api/circuits/captures').json()), 1)
                    self.assertFalse(client.get('/api/motor/status').json()['state']['enabled'])
                    self.assertEqual(client.get('/api/sessions').json(), [])
            finally:
                api_main.DATABASE_PATH, api_main.live_monitor = database, monitor

    def test_invalid_asset_rejected(self):
        from api.schemas import PhysicalCircuitAsset
        for asset in ({**ASSET, 'test_points': ASSET['test_points'] * 2},
                      {**ASSET, 'test_points': [{**ASSET['test_points'][0], 'minimum': 6}]}):
            with self.assertRaises(ValueError):
                PhysicalCircuitAsset.model_validate(asset)
