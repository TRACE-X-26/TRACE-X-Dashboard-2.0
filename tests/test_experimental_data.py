import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from diagnostic_platform.experimental_data import audit_archives, stats
from diagnostic_platform.health_analysis import analyze


class ExperimentalDataTests(unittest.TestCase):
    def test_archive_aliases_deduplicate_and_rows_do_not_become_synchronous_power(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['received_at', 'test', 'target_pwm_percent', 'raw_message'])
            writer.writerow(['2026-10-28T12:00:00+00:00', '12', '50', 'Voltage: 12 V'])
            writer.writerow(['2026-10-28T12:00:01+00:00', '12', '50', 'Current: 0 A'])
            archive = root/'test.zip'
            with ZipFile(archive, 'w') as zipped:
                for name in ['data/motor_tests/test_12/run_85g.csv', 'data/motor_tests/old_tests/test_12/run_85g.csv']:
                    zipped.writestr(name, stream.getvalue())
            result = audit_archives([archive], root/'output')
            self.assertEqual(result['unique_runs'], 1)
            self.assertEqual(result['duplicate_files'], 1)
            again = audit_archives([archive], root/'output')
            self.assertEqual(result, again)
            run, = json.loads((root/'output/canonical.json').read_text())['runs']
            self.assertEqual(len(run['sources']), 2)
            self.assertEqual(run['features']['current']['all_recorded']['mean'], 0)
            self.assertEqual(run['features']['input_power']['all_recorded']['count'], 0)
            self.assertFalse(run['baseline_eligible'])
            self.assertIsNone(run['metadata']['attached_mass_g'])
            self.assertEqual(run['metadata']['filename_mass_label_g'], 85)

    def test_robust_statistics(self):
        result = stats([0, 1, 2, 3, 4])
        self.assertEqual(result['median'], 2)
        self.assertEqual(result['mad'], 1)
        self.assertEqual(result['std'], 2**.5)

    def test_disabled_temperature_does_not_hide_electrical_summary(self):
        samples = [dict(values=dict(voltage=12, current=.1, power=1.2, rpm=78, temperature=None),
                        quality=['RPM_UNCALIBRATED'],
                        raw={'measurements': {c: {'timestamp_ms': i} for c in ('voltage','current','power','rpm')}})
                   for i in range(8)]
        report = analyze(samples, completed=True, source='stm32_serial',
                         required_channels=('voltage','current','power','rpm'))
        self.assertEqual(report['features']['current']['count'], 8)
        self.assertIn('No approved baseline', report['findings'][0])
        self.assertIsNone(report['health_score'])
