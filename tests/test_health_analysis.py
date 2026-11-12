import unittest
from diagnostic_platform.health_analysis import analyze

class HealthAnalysisTests(unittest.TestCase):
    def samples(self):
        return [dict(values=dict(voltage=12.,current=.6,rpm=250.,temperature=25.,power=7.2),quality=[],
                     raw={'measurements':{c:{'timestamp_ms':i} for c in ('voltage','current','rpm','temperature','power')}})
                for i in range(6)]
    def baseline(self):
        return {'pwm_10':dict(validated=True,independent_runs=3,max_std={c:1. for c in ('voltage','current','rpm','temperature','power')},ranges=dict(
            voltage=[11,13],current=[.5,.7],rpm=[240,260],temperature=[20,30],power=[6,8]))}
    def test_no_baseline_abstains_and_bad_acquisition_is_not_motor_failure(self):
        result=analyze(self.samples(),completed=True,source='stm32_serial',test_id='pwm_10')
        self.assertEqual(result['condition'],'INSUFFICIENT_DATA');self.assertIsNone(result['health_score'])
        samples=self.samples()
        for sample in samples:sample['quality']=['INVALID_SENSOR_DATA']
        result=analyze(samples,completed=True,source='stm32_serial',baselines=self.baseline(),test_id='pwm_10')
        self.assertEqual(result['condition'],'INSUFFICIENT_DATA')
    def test_synthetic_approved_baseline_score_is_explainable(self):
        result=analyze(self.samples(),completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertEqual(result['condition'],'HEALTHY');self.assertEqual(result['health_score'],100)
        samples=self.samples()
        for sample in samples:sample['values']['rpm']=200
        result=analyze(samples,completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertEqual(result['condition'],'WARNING');self.assertEqual(result['health_score'],80)
    def test_repeated_channel_acquisitions_do_not_inflate_evidence(self):
        samples=self.samples()
        for sample in samples:sample['raw']['measurements']['current']['timestamp_ms']=0
        result=analyze(samples,completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertIsNone(result['health_score'])
    def test_incomplete_never_has_a_health_score(self):
        result=analyze(self.samples(),completed=False,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertEqual(result['condition'],'TEST_INCOMPLETE');self.assertIsNone(result['health_score'])

    def test_temperature_never_affects_health(self):
        samples=self.samples()
        for sample in samples:
            sample['values']['temperature']=None
        healthy=analyze(samples,completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertEqual(healthy['condition'],'HEALTHY')
        self.assertNotIn('temperature', healthy['features'])
        for sample in samples:
            sample['values']['temperature']=999
        self.assertEqual(analyze(samples,completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')['condition'],'HEALTHY')

    def test_conflicting_values_for_one_acquisition_are_not_independent_evidence(self):
        samples=self.samples()
        import copy
        conflict=copy.deepcopy(samples[0])
        conflict['values']['current']=9
        samples.append(conflict)
        result=analyze(samples,completed=True,source='SIMULATION',baselines=self.baseline(),test_id='pwm_10')
        self.assertIsNone(result['health_score'])
        self.assertIn('Conflicting',result['findings'][0])
