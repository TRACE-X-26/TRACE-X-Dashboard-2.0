"""Motor commissioning regressions. All connections here are software fixtures."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from diagnostic_platform.automated_engine import AutomatedTestEngine, RunRejected, load_hardware_profile
from diagnostic_platform.motor_csv import render_motor_csv
from diagnostic_platform.test_registry import REGISTRY
from diagnostic_platform.stm32 import STM32SerialConnection
from diagnostic_platform.device_simulator import STM32Simulator

ROOT=Path(__file__).resolve().parents[1]

class MotorDashboardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=AutomatedTestEngine(Path(self.temp.name)/'runs.db')
    def tearDown(self):
        self.engine.close();self.temp.cleanup()
    def profile(self):
        profile=json.loads((ROOT/'deploy/pi/hardware-profile.example.json').read_text())
        for name in ('wiring_verified','relay_verified','interlock_verified','kill_switch_verified',
                     'communication_stop_verified','calibration_verified','operator_enable','protection_limits_verified',
                     'power_feedback_installed','power_feedback_wiring_verified'):
            profile[name]=True # Synthetic test input, never a real approval.
        profile['supply_sensing']['verified']=True
        profile.update(evidence_id='FAKE',calibration_id='FAKE',fixture_id='FAKE',serial_identity='FAKE')
        return profile
    def write_profile(self,profile):
        p=Path(self.temp.name)/'profile.json';p.write_text(json.dumps(profile));return p
    def test_temperature_remains_retired_and_electrical_cutoffs_are_not_required(self):
        profile=self.profile()
        loaded=load_hardware_profile(self.write_profile(profile))
        self.assertFalse(loaded['temperature_enabled']);self.assertTrue(loaded['electrical_limits_enabled'])
        self.assertEqual(loaded['limits']['max_current'],1.5)
        profile['temperature_enabled']=True
        with self.assertRaisesRegex(RunRejected,'Temperature has been retired'):
            load_hardware_profile(self.write_profile(profile))
    def test_template_does_not_claim_assumed_operating_current_is_a_protection_limit(self):
        p=ROOT/'deploy/pi/hardware-profile.example.json'
        profile=json.loads(p.read_text())
        self.assertEqual(profile['motor']['operating_current_reference'],.5)
        self.assertEqual(profile['limits']['max_current'],1.5)
        self.assertTrue(profile['electrical_limits_enabled'])
        self.assertFalse(profile['encoder']['calibrated'])
        with self.assertRaises(RunRejected):load_hardware_profile(p)
    def test_provisional_rpm_and_disabled_temperature_are_usable_without_health_claim(self):
        device=STM32Simulator()
        connection=STM32SerialConnection(port="SIMULATION",transport_factory=lambda *_:device,device_id=device.device_id,
                                         require_crc=True,allow_motor_control=True)
        connection.connect()
        # Modify only decoded test telemetry, never physical STM32 data.
        execute=connection.execute
        def read(command,*args,**kwargs):
            result=execute(command,*args,**kwargs)
            if command=='READ_MEASUREMENTS':
                result=copy.deepcopy(result);result['encoder_calibrated']=False
                result['temperature_calibrated']=False
                result['measurements']['temperature'].update(value=None,valid=False)
                result.pop('temperature_started_ms');result.pop('temperature_completed_ms')
            return result
        connection.execute=read
        run=dict(id='fixture',created_at='fixture',source='SIMULATION',state='PRECHECK',mode='simulation',
                 commissioning={**self.profile(),'limits':{'min_voltage':9.,'max_voltage':15.,'max_current':10.}},steps=[])
        self.engine.store.create(run)
        step={'samples':[],'device_session_id':'fixture'}
        self.engine._measure(connection,run,REGISTRY['pwm_10'],step,None)
        self.assertEqual(step['samples'][0]['quality'],['RPM_UNCALIBRATED'])
        self.assertIsNone(run['latest_measurement']['temperature'])
        self.assertFalse(run['latest_measurement']['rpm_calibrated'])
        self.assertEqual(run['latest_measurement']['rpm'],0)
        connection.disconnect();self.engine.store.release(run['id'])
    def test_csv_retains_zero_values_invalid_nulls_and_shutdown_event_time(self):
        run=dict(id='fixture',source='SIMULATION',state='CANCELLED',outcome='TEST_INCOMPLETE',
            reason='Operator cancelled',stop_confirmed=True,device_state='STOPPED',applied_pwm_percent=0,
            samples=[dict(received_at='now',quality=['RPM_UNCALIBRATED'],raw=dict(
                measurements={'voltage':dict(value=12,valid=True),'current':dict(value=0,valid=True),
                'rpm':dict(value=0,valid=True),'power':dict(value=999,valid=False)},
                applied_pwm_percent=10,requested_pwm_percent=10,motor_state='RUNNING',encoder_calibrated=False))],
            events=[dict(timestamp_ms=1200,payload=dict(event='MOTOR_STOP',reason='CANCELLED'))])
        import csv,io
        rows=list(csv.DictReader(io.StringIO(render_motor_csv(run))))
        self.assertEqual(rows[0]['current_A'],'0');self.assertEqual(rows[0]['rpm'],'0')
        self.assertEqual(rows[0]['power_W'],'')
        self.assertEqual(rows[1]['stm32_timestamp_ms'],'1200')
        self.assertEqual(rows[-1]['applied_pwm_percent'],'0')
