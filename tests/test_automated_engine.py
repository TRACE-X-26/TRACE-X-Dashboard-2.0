import tempfile
import time
import unittest
from pathlib import Path
from diagnostic_platform.automated_engine import AutomatedTestEngine,RunRejected,TERMINAL
from diagnostic_platform.protocol import ProtocolError,command_message,CommandName,encode_message,decode_message

class AutomatedEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'runs.db'
        self.engine=AutomatedTestEngine(self.path)
    def tearDown(self):self.engine.close();self.temp.cleanup()
    def wait(self):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            snap=self.engine.snapshot()
            if snap and snap['ended_at']:return self.engine.store.get(snap['id'])
            time.sleep(.02)
        self.fail('Run did not terminate')
    def test_complete_sequence_is_protocol_backed_persisted_and_not_hardware(self):
        run=self.engine.start({'run_all':True,'duration_ms':300})
        result=self.wait()
        self.assertEqual(result['state'],'COMPLETED',result.get('reason'))
        self.assertEqual(len(result['steps']),6)
        self.assertTrue(result['stop_confirmed'])
        self.assertEqual(result['source'],'SIMULATION')
        self.assertIsNone(result['health_score'])
        self.assertGreater(len(result['samples']),5)
        self.assertTrue(any(e.get('type')=='event' for e in result['events']))
        self.assertEqual(self.engine.store.get(run['id'])['state'],'COMPLETED')
    def test_hardware_fails_closed_and_registry_explains_unsupported(self):
        with self.assertRaises(RunRejected):self.engine.start({'mode':'hardware','tests':['pwm_10']})
        self.assertTrue(all(not p['available'] for p in self.engine.available('hardware')))
        with self.assertRaises(RunRejected):self.engine.start({'tests':['continuity']})
    def test_cancel_and_concurrent_start(self):
        self.engine.start({'tests':['pwm_10'],'duration_ms':2000})
        with self.assertRaises(RunRejected):self.engine.start({'tests':['idle']})
        self.engine.stop();result=self.wait()
        self.assertEqual(result['state'],'CANCELLED')
        self.assertIsNone(result['health_score'])
    def test_emergency_stop(self):
        self.engine.start({'tests':['pwm_10'],'duration_ms':2000})
        time.sleep(.1);self.engine.stop(True);result=self.wait()
        self.assertEqual(result['state'],'EMERGENCY_STOP')
        self.assertTrue(result['stop_confirmed'])
    def test_invalid_sensor_is_acquisition_failure_not_motor_health(self):
        self.engine.start({'tests':['pwm_10'],'scenario':'sensor_failure','duration_ms':300})
        result=self.wait();self.assertEqual(result['state'],'FAILED')
        self.assertIsNone(result['health_score'])
        self.assertTrue(any('INVALID_SENSOR_DATA' in s['quality'] for s in result['samples']))
    def test_disconnect_does_not_fallback(self):
        self.engine.start({'tests':['pwm_10'],'scenario':'communication_loss','duration_ms':1000})
        result=self.wait();self.assertEqual(result['state'],'DISCONNECTED')
        self.assertEqual(result['source'],'SIMULATION')
        self.assertFalse(result['stop_confirmed'])
    def test_transition_rejection_and_persistence_recovery(self):
        with self.assertRaises(RuntimeError):self.engine._transition({'state':'IDLE'},'COMPLETED')
        from diagnostic_platform.automated_storage import utcnow
        run=dict(id='interrupted',state='RUNNING',mode='hardware',created_at=utcnow(),stop_confirmed=True)
        self.engine.store.create(run);self.engine.store.recover()
        recovered=self.engine.store.get('interrupted')
        self.assertEqual(recovered['state'],'DISCONNECTED')
        self.assertEqual(recovered['outcome'],'TEST_INCOMPLETE')
        self.assertFalse(recovered['stop_confirmed'])
    def test_single_backend_owner(self):
        with self.assertRaises(RuntimeError):AutomatedTestEngine(self.path)
    def test_crc_detects_corruption(self):
        frame=encode_message(command_message(CommandName.GET_STATUS,1),checksum=True)
        self.assertEqual(decode_message(frame).sequence,1)
        with self.assertRaises(ProtocolError):decode_message(frame.replace(b'GET_STATUS',b'GET_FAULTS'))

    def test_guided_load_requires_documented_setup_and_saves_condition(self):
        with self.assertRaises(RunRejected):
            self.engine.start({'tests':['load_response'],'duration_ms':5000})
        with self.assertRaises(RunRejected):
            self.engine.start({'tests':['load_response'],'duration_ms':300,
                               'load_id':'fixture-85g','condition':'operator-positioned'})
        self.engine.start({'tests':['load_response'],'duration_ms':5000,
                           'load_id':'fixture-85g','condition':'operator-positioned','attached_mass_g':85})
        result=self.wait()
        self.assertEqual(result['state'],'COMPLETED',result.get('reason'))
        self.assertEqual(result['configuration']['attached_mass_g'],85)
        report=result['steps'][0]['result']
        self.assertEqual(report['analysis_window_ms'],[3000,5000])
        self.assertEqual(report['operating_context']['load_id'],'fixture-85g')

    def test_supervised_sequences_require_separate_authorizations(self):
        from unittest.mock import patch
        profile=dict(asset_id='MOTOR-001',operating_mode='SUPERVISED_TEST',
                     fixed_pwm_percent=50,max_duration_ms=30000)
        with patch('diagnostic_platform.automated_engine.load_hardware_profile',return_value=profile), \
             patch.object(self.engine.hardware_runtime,'enabled',True):
            with self.assertRaisesRegex(RunRejected,'fresh authorization for each'):
                self.engine.start(dict(mode='hardware',device_id='MOTOR-001',tests=['idle','pwm_50'],
                                       operator_authorized=True,supervised_confirmed=True))

    def test_full_historical_catalog_and_approval_gates(self):
        from diagnostic_platform.test_registry import experiment_catalog,registry
        self.assertEqual([entry['test_number'] for entry in experiment_catalog()],list(range(1,14)))
        physical={entry['id']:entry for entry in registry('hardware',50,True)}
        self.assertFalse(physical['load_response']['available'])
        self.assertFalse(physical['power_consumption']['available'])
        self.assertFalse(physical['pwm_100']['available'])
        approved={entry['id']:entry for entry in registry('hardware',50,True,['load_response'])}
        self.assertTrue(approved['load_response']['available'])
