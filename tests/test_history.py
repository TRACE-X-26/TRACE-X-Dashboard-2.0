import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import api.main as api_main
from diagnostic_platform.history import parse_csv
from diagnostic_platform.storage import DiagnosticStore
from diagnostic_platform.import_history import import_archive
from zipfile import ZipFile


class HistoricalTests(unittest.TestCase):
    def test_archive_import_preserves_source_deduplicates_and_skips_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, database = Path(tmp) / 'source.zip', Path(tmp) / 'history.db'
            content = 'received_at,raw_message\n2026-10-28T16:36:00-04:00,Voltage: 12 V\n'
            with ZipFile(archive, 'w') as z:
                z.writestr('test_12/run_56p7g.csv', content)
                z.writestr('old_tests/copy.csv', content)
                z.writestr('motor_test_results.csv', 'timestamp,state\nnow,PASS\n')
                z.writestr('collector.py', 'raise RuntimeError("must not execute")')
            original = archive.read_bytes()
            result = import_archive(archive, database)
            self.assertEqual(result['csv_files'], 3)
            self.assertEqual(result['imported_unique_recordings'], 1)
            self.assertEqual(archive.read_bytes(), original)
            with DiagnosticStore(database) as store:
                metadata = store.recording(1)['metadata']
                self.assertEqual(metadata['filename_mass_label_g'], 56.7)
                self.assertIsNone(metadata['attached_mass_g'])
                self.assertEqual(store.list_sessions(), [])

    def test_actual_collector_headers_bursts_and_sensor_failure(self):
        result = parse_csv('received_at,test,target_pwm_percent,voltage_v,current_a,rpm,raw_message\n'
            '2026-10-28T16:36:00.490222-04:00,12,50,,,,Voltage: 12.284 V\n'
            '2026-10-28T16:36:00.490337-04:00,12,50,,,,Current: 0.055 A\n'
            '2026-10-28T16:36:00.490439-04:00,12,50,,,,TEMPERATURE SENSOR: NOT DETECTED\n', {})
        self.assertEqual(result['timestamp_basis'], 'HOST_RECEIVE_TIME')
        self.assertEqual(result['samples'][0]['timestamp'], '2026-10-28T16:36:00.490222-04:00')
        self.assertEqual(result['recorded_features']['current']['mean'], .055)
        self.assertIsNone(result['samples'][0]['input_power'])
        codes = {w['code'] for w in result['warnings']}
        self.assertTrue({'SUB_MILLISECOND_RECEIVE_BURST', 'SENSOR_OR_COMMUNICATION_MESSAGE'} <= codes)

    def test_early_collector_alias_and_interleaving(self):
        result = parse_csv('timestamp,serial_message\n'
            '2026-10-28T12:00:00Z,Current: 0.057 ENCODER: NO PULSES DETECTED\n'
            '2026-10-28T12:00:01Z,Motor RPM: -1\n'
            '2026-10-28T12:00:02Z,Encoder Counts: -10\n', {})
        self.assertEqual(result['samples'][0]['rpm'], -1)
        self.assertEqual(result['samples'][1]['encoder_counts'], -10)
        self.assertIn('MALFORMED_CURRENT_MESSAGE', [w['code'] for w in result['warnings']])

    def test_design_spec_fields_preserve_units_and_direction(self):
        result = parse_csv('timestamp,mode,motor_voltage_V,motor_current_A,motor_power_W,motor_rpm,motor_temperature_C,motor_direction\n'
            '2026-10-30T12:00:00Z,MOTOR,12,0.5,6,78,31.4,FORWARD\n', {})
        sample = result['samples'][0]
        self.assertEqual(sample['voltage'], 12)  # No circuit ADC divider correction.
        self.assertEqual(sample['input_power'], 6)
        self.assertEqual(sample['recorded_power'], 6)
        self.assertEqual(sample['temperature'], 31.4)
        self.assertEqual(sample['direction'], 'FORWARD')
        self.assertEqual(sample['phase'], 'BEFORE_START')

    def test_circuit_rows_do_not_become_motor_measurements(self):
        result = parse_csv('mode,voltage,current\nCIRCUIT,5,0.01\n', {})
        self.assertEqual(result['samples'], [])
        self.assertIn('NON_MOTOR_ROW_EXCLUDED', [w['code'] for w in result['warnings']])

    def parse(self, rows):
        return parse_csv('timestamp,raw_message\n' + rows, {"filename": "fixture.csv"})

    def test_phases_and_no_cross_row_fabrication(self):
        result = self.parse('2026-10-30T12:00:00Z,Voltage: 12 V\n'
            '2026-10-30T12:00:01Z,MOTOR_START\n'
            '2026-10-30T12:00:02Z,Current: 0.2 A\n'
            '2026-10-30T12:00:03Z,Motor RPM: 78\n'
            '2026-10-30T12:00:04Z,MOTOR_STOP\n'
            '2026-10-30T12:00:05Z,Current: 0 A\n')
        self.assertEqual([s['phase'] for s in result['samples']],
                         ['BEFORE_START', 'RUNNING', 'RUNNING', 'AFTER_STOP'])
        self.assertEqual(result['features']['current']['mean'], .2)
        self.assertTrue(all(s['input_power'] is None for s in result['samples']))

    def test_structured_power_and_optional_temperature(self):
        result = parse_csv('timestamp,raw_message,voltage,current,rpm\n'
            '2026-10-30T12:00:00Z,MOTOR_START,,,\n'
            '2026-10-30T12:00:01Z,,12,0.2,78\n', {})
        self.assertAlmostEqual(result['features']['input_power']['mean'], 2.4)
        self.assertIsNone(result['samples'][0]['temperature'])

    def test_duplicate_start_does_not_create_new_segment(self):
        row = '2026-10-30T12:00:00Z,MOTOR_START\n'
        result = self.parse(row + row + '2026-10-30T12:00:01Z,Motor RPM: 78\n')
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['samples'][0]['segment'], 1)
        self.assertIn('DUPLICATE_ROW', [w['code'] for w in result['warnings']])

    def test_gap_and_reset_remove_running_assumption(self):
        result = self.parse('2026-10-30T12:00:00Z,MOTOR_START\n'
            '2026-10-30T12:00:10Z,Current: 0.2 A\n'
            '2026-10-30T12:00:11Z,reboot\n'
            '2026-10-30T12:00:12Z,Motor RPM: 78\n')
        self.assertTrue(all(s['phase'] == 'UNKNOWN' for s in result['samples']))

    def test_conflicts_nonfinite_and_corruption(self):
        result = parse_csv('timestamp,raw_message,current,voltage\n'
            'bad,Current: 0.3 A,0.2,nan\n'
            'bad,Current: 0.3 A Current: 0.4 A,,\n', {})
        codes = {w['code'] for w in result['warnings']}
        self.assertTrue({'AMBIGUOUS_CURRENT', 'INVALID_VOLTAGE', 'TIMESTAMP_UNPARSED'} <= codes)
        self.assertFalse(result['samples'])

    def test_malformed_row_and_unknown_headers(self):
        self.parse('bad,Voltage: 12 V,unexpected\n')
        with self.assertRaises(ValueError):
            parse_csv('unrelated\n1\n', {})

    def test_original_text_and_idempotence(self):
        content = 'timestamp,raw_message\nbad,Voltage: 12 V\n'
        result = parse_csv(content, {})
        with tempfile.TemporaryDirectory() as tmp:
            with DiagnosticStore(Path(tmp) / 'history.db') as store:
                first = store.save_recording(content, result, 'now')
                self.assertEqual(first, store.save_recording(content, result, 'later'))
                self.assertEqual(len(store.list_recordings()), 1)
                self.assertEqual(store.recording(first)['samples'][0]['voltage'], 12)
                self.assertEqual(store.connection.execute('SELECT original_csv FROM historical_recordings').fetchone()[0], content)
                self.assertEqual(store.list_sessions(), [])

    def test_power_counts_and_zero_values_are_retained(self):
        result = self.parse('bad,Power: 1.643 W\nbad,Encoder Counts: 0\n')
        self.assertEqual(result['samples'][0]['recorded_power'], 1.643)
        self.assertEqual(result['samples'][1]['encoder_counts'], 0)

    def test_identical_untimed_readings_are_only_possible_duplicates(self):
        result = parse_csv('current\n0.2\n0.2\n', {})
        self.assertEqual(len(result['samples']), 2)
        self.assertIn('POSSIBLE_DUPLICATE_WITHOUT_TIMESTAMP', result['samples'][1]['warnings'])

    def test_api_import_list_and_detail_without_motor_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = api_main.DATABASE_PATH
            api_main.DATABASE_PATH = Path(tmp) / 'api.db'
            try:
                with TestClient(api_main.app) as client:
                    before = client.get('/api/motor/status').json()['state']
                    response = client.post('/api/recordings', json={
                        'filename': 'synthetic.csv', 'device_id': 'MOTOR-001',
                        'content': 'timestamp,raw_message\nbad,Voltage: 12 V\n'})
                    self.assertEqual(response.status_code, 201)
                    recording_id = response.json()['id']
                    self.assertEqual(len(client.get('/api/recordings').json()), 1)
                    self.assertEqual(client.get(f'/api/recordings/{recording_id}').json()['source'], 'HISTORICAL_CSV')
                    self.assertEqual(client.get('/api/recordings/999').status_code, 404)
                    self.assertEqual(client.post('/api/recordings', json={
                        'filename': 'bad.csv', 'device_id': 'MOTOR-001',
                        'content': 'raw_message\n"unclosed'}).status_code, 422)
                    self.assertEqual(client.get('/api/motor/status').json()['state'], before)
                    self.assertEqual(client.get('/api/sessions').json(), [])
            finally:
                api_main.DATABASE_PATH = previous
