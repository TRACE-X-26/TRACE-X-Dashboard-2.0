import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

import api.main as api_main
from diagnostic_platform.circuit4 import ASSET_ID, REFERENCES, circuit4_asset, classify_circuit4
from diagnostic_platform.live import LiveMonitor


def readings(values):
    return [{'point_id': key, 'channel': 'test_point_voltage', 'measured': value} for key, value in values.items()]


class Circuit4Tests(unittest.TestCase):
    def test_supplied_multimeter_examples_match_without_label_input(self):
        for label, expected in [('NORMAL', 'NORMAL_SIGNATURE'), ('S1_OPEN', 'S1_OPEN_SIGNATURE'), ('S2_SHUNT', 'S2_SHUNT_SIGNATURE')]:
            result = classify_circuit4(readings(REFERENCES[label]))
            self.assertEqual(result['classification'], expected)
            self.assertEqual(len(result['normal_deviations']), 5)
            self.assertIsNone(result['health_score'])

    def test_proposed_resistor_deviation_is_not_an_invented_class(self):
        values = {**REFERENCES['NORMAL'], 'TP1': 3.0, 'TP4': 3.0}
        self.assertEqual(classify_circuit4(readings(values))['classification'], 'INCONCLUSIVE')

    def test_supply_reference_missing_and_nonfinite_gates(self):
        for values, expected in [({**REFERENCES['S1_OPEN'], 'TP0': 3}, 'SUPPLY_OUT_OF_RANGE'),
                                 ({**REFERENCES['S2_SHUNT'], 'TP2': 3}, 'REFERENCE_OUT_OF_RANGE'),
                                 ({'TP1': 0}, 'INSUFFICIENT_DATA'),
                                 ({**REFERENCES['NORMAL'], 'TP4': float('nan')}, 'INSUFFICIENT_DATA')]:
            self.assertEqual(classify_circuit4(readings(values))['classification'], expected)

    def test_low_output_alone_cannot_distinguish_open_from_shunt(self):
        values = {**REFERENCES['S1_OPEN'], 'TP4': .4}
        self.assertEqual(classify_circuit4(readings(values))['classification'], 'INCONCLUSIVE')

    def test_normal_deviation_is_signed_and_relative_to_normal(self):
        result = classify_circuit4(readings(REFERENCES['S2_SHUNT']))
        point = next(p for p in result['normal_deviations'] if p['point_id'] == 'TP1')
        self.assertAlmostEqual(point['difference_V'], .40643 - 2.4744)
        self.assertAlmostEqual(point['deviation_percent'], (.40643 / 2.4744 - 1) * 100)

    def test_end_to_end_software_capture_persists_classification(self):
        with tempfile.TemporaryDirectory() as temporary:
            old_database, old_monitor = api_main.DATABASE_PATH, api_main.live_monitor
            monitor = LiveMonitor(); monitor._connected = True
            api_main.DATABASE_PATH, api_main.live_monitor = Path(temporary) / 'test.db', monitor
            try:
                with TestClient(api_main.app) as client:
                    asset = next(a for a in client.get('/api/circuits/assets').json() if a['asset_id'] == ASSET_ID)
                    self.assertEqual(len(asset['test_points']), 5)
                    self.assertEqual(client.post('/api/circuits/captures', json={'asset_id': ASSET_ID}).status_code, 409)
                    session = client.post('/api/circuits/captures', json={'asset_id': ASSET_ID, 'conditions_confirmed': True}).json()
                    url = f"/api/circuits/captures/{session['id']}"
                    for point, value in REFERENCES['S1_OPEN'].items():
                        self.assertEqual(client.post(url + '/arm', json={'point_id': point, 'probe_confirmed': True}).status_code, 200)
                        monitor.feed(json.dumps({'mode': 'CIRCUIT', 'asset_id': ASSET_ID, 'test_point_id': point,
                                                 'test_point_voltage_V': value}))
                        result = client.post(url + '/capture')
                        self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()['condition'], 'S1_OPEN_SIGNATURE')
                    saved = client.get('/api/circuits/captures').json()[0]
                    self.assertEqual(saved['diagnostic']['classification'], 'S1_OPEN_SIGNATURE')
                    self.assertEqual(saved['asset']['diagnostic_model'], 'circuit4-lm324-v1')
                    evidence = client.get('/api/circuits/circuit4/reference-analysis').json()
                    self.assertEqual(evidence['source'], 'USER_REPORTED_MULTIMETER_REFERENCE')
                    self.assertFalse(evidence['hardware_control'])
            finally:
                api_main.DATABASE_PATH, api_main.live_monitor = old_database, old_monitor
