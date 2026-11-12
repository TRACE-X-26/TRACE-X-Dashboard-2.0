import copy
import unittest

from diagnostic_platform.baseline_package import build_package
from diagnostic_platform.health_analysis import analyze
from diagnostic_platform.model_training import train


class BaselinePackageTests(unittest.TestCase):
    def manifest(self):
        context = dict(device_id='fixture',calibration_id='cal-1',fixture_id='fixture-1',pwm_percent=50,
                       direction='FORWARD',load_id='no-load',condition='confirmed-healthy',
                       supply_range=[11,13],duration_ms=30000,firmware_version='fixture-1',
                       sensor_configuration='INA219-MOTOR-0x40-and-encoder',procedure_version='fixed-duty-v1')
        samples = [dict(quality=[],raw=dict(test_id='pwm_50',voltage_current_calibrated=True,
                                           encoder_calibrated=True,
                    measurements={name:dict(value=value,valid=True,timestamp_ms=i)
                                  for name,value in dict(voltage=12,current=.2,power=2.4,rpm=78).items()}))
                   for i in range(10)]
        run = dict(source='stm32_serial',state='COMPLETED',stop_confirmed=True,known_good=True,
                   steps=[dict(test_id='pwm_50',result=dict(operating_context=context))],samples=samples)
        return dict(runs=[dict(copy.deepcopy(run),id=str(i)) for i in range(5)],
                    tolerances=dict(voltage=.1,current=.05,power=.5,rpm=3),
                    max_std=dict(voltage=.1,current=.05,power=.5,rpm=3))

    def test_candidate_is_never_automatically_approved_and_temperature_is_absent(self):
        manifest=self.manifest()
        package=build_package(manifest)
        self.assertFalse(package['validated'])
        self.assertNotIn('temperature',package['ranges'])
        manifest['approval']=dict(reviewer='test-fixture',evidence_id='synthetic-unit-test',approved_at='2026-11-11')
        approved=build_package(manifest)
        sample=manifest['runs'][0]['samples']
        normalized=[dict(values={key:item['value'] for key,item in row['raw']['measurements'].items()},**row) for row in sample]
        result=analyze(normalized,completed=True,source='stm32_serial',test_id='pwm_50',
                       context=approved['operating_context'],baselines={'pwm_50':approved})
        self.assertEqual(result['condition'],'HEALTHY')
        self.assertIsNone(result['health_score'])
        self.assertEqual(len(result['comparisons']),4)
        for row in normalized:
            row['values']['current']=.7
        deviating=analyze(normalized,completed=True,source='stm32_serial',test_id='pwm_50',
                          context=approved['operating_context'],baselines={'pwm_50':approved})
        self.assertEqual(deviating['condition'],'WARNING')
        self.assertTrue(any('current mean' in finding for finding in deviating['findings']))

    def test_context_quality_and_duplicate_run_gates(self):
        for mutate in [
            lambda m:m['runs'][0].update(id='1'),
            lambda m:m['runs'][0].update(known_good=False),
            lambda m:m['runs'][0].update(source='SIMULATION'),
            lambda m:m['runs'][0]['steps'][0]['result']['operating_context'].update(load_id='other'),
            lambda m:m['runs'][0]['samples'][0]['raw'].update(encoder_calibrated=False),
            lambda m:m['runs'][0].update(stop_confirmed=False),
        ]:
            manifest=self.manifest()
            mutate(manifest)
            with self.assertRaises(ValueError):
                build_package(manifest)

    def test_ml_abstains_without_labeled_independent_sessions(self):
        self.assertFalse(train({'runs':[]})['enabled'])
        self.assertNotIn('metrics',train({'runs':[dict(run_id='unverified')]}))

    def test_grouped_experimental_validation_does_not_enable_production(self):
        rows=[dict(run_id=f'{label}-{session}',source='stm32_serial',label_verified=True,
                   label_evidence_id='synthetic-unit-fixture',measurements_verified=True,label=label,recording_session_id=str(session),
                   operating_context=self.manifest()['runs'][0]['steps'][0]['result']['operating_context'],
                   features=dict(voltage=12,current=current,rpm=78,power=12*current))
              for label,current in [('A',.1),('B',1)] for session in range(3)]
        report=train({'runs':rows})
        self.assertFalse(report['enabled'])
        self.assertEqual(report['metrics']['A']['f1'],1)
        self.assertEqual(report['independent_runs'],6)
