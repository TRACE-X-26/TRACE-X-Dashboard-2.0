"""Hardware-mode integration against in-memory STM32s; never opens a device."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from diagnostic_platform.automated_engine import AutomatedTestEngine, RunRejected
from diagnostic_platform.config import Settings
from diagnostic_platform.device_simulator import STM32Simulator
from diagnostic_platform.hardware_runtime import HardwareRuntime
from diagnostic_platform.protocol import decode_message
from diagnostic_platform.stm32 import STM32SerialConnection

ROOT = Path(__file__).resolve().parents[1]


class BenchFixture(STM32Simulator):
    """Test-only protocol peer impersonation, restricted to temporary DBs."""
    device_id = 'STM32-ADS'

    def __init__(self, fault='healthy'):
        super().__init__(50)
        self.fault = fault
        self.power_stage=False;self.power_tick=0

    def status(self):
        return {**super().status(), 'operating_mode': 'SUPERVISED_TEST',
                'power_feedback_installed': False, 'power_feedback_state': 'NOT_INSTALLED','power_check_required':True,
                'motor_relay_requested_on':self.power_stage,'power_started_ms':self.power_tick}

    def event(self, event, reason):
        if self.fault == 'missing_start_event' and event == 'MOTOR_START':
            return
        super().event(event, reason)

    def write(self, frame):
        request = decode_message(frame)
        cmd = request.payload.get('command')
        if cmd=='PREPARE_TEST_POWER' and self.fault=='power_check_rejected':
            self.frames.append(request)
            self.emit('ack',{'reply_to':request.sequence,'result':{**self.status(),'accepted':False,'reason':'POWER_CHECK_START_FAILED'}})
            return len(frame)
        if cmd=='PREPARE_TEST_POWER':
            self.frames.append(request);self.power_stage=True;self.power_tick=(self.tick()-100)&0xffffffff
            self.state='POWER_CHECK' if self.fault=='power_check_timeout' else 'POWER_READY'
            self.emit('ack',{'reply_to':request.sequence,'result':{**self.status(),'accepted':True,'state':'POWER_CHECK'}})
            return len(frame)
        if cmd=='SET_PWM' and self.state=='POWER_READY':
            self.frames.append(request);self.requested=request.payload['arguments']['pwm_percent']
            self.emit('ack',{'reply_to':request.sequence,'result':{**self.status(),'accepted':True}})
            return len(frame)
        if cmd=='START_TEST' and self.state=='POWER_READY':self.state='ARMED'
        if cmd in ('STOP_TEST','STOP_MOTOR','EMERGENCY_STOP'):self.power_stage=False

        if self.fault in ('rejected_start','relay_failure') and cmd == 'START_TEST':
            self.frames.append(request)
            self.emit('ack', {'reply_to': request.sequence, 'result': {
                **self.status(), 'accepted': False, 'reason': 'RELAY_ACTUATION_FAILED' if self.fault=='relay_failure' else 'INTERLOCK_OR_SENSOR_FAULT'}})
            return len(frame)
        if self.fault == 'stop_failure' and cmd in {'STOP_TEST', 'STOP_MOTOR', 'EMERGENCY_STOP'}:
            self.frames.append(request)
            self.emit('ack', {'reply_to': request.sequence, 'result': {
                **self.status(), 'accepted': True, 'applied_pwm_percent': 50, 'state': 'RUNNING'}})
            return len(frame)
        if self.fault == 'heartbeat_loss' and cmd == 'READ_MEASUREMENTS' and self.state == 'RUNNING':
            self.last_heartbeat = self.tick() - 2000
        return super().write(frame)

    def emit(self, kind, payload, stamp=None):
        payload = copy.deepcopy(payload)
        result = payload.get('result', {})
        if kind == 'capabilities':
            result['commands']=result.get('commands',[])+['PREPARE_TEST_POWER']
            result.update(firmware_version='0.7.0-downstream-protected', operating_mode='SUPERVISED_TEST',
                          power_feedback_installed=False, electrical_limits_enabled=True, protection_limits_verified=True,
                          supply_sensing="DOWNSTREAM_POWER_CHECK",supply_sensing_verified=True,power_check_required=True,power_check_timeout_ms=1500,power_check_settle_ms=50,
                          min_voltage_mv=10000,max_voltage_mv=14000,max_current_ma=1500,
                          motor_relay_active_level=0,circuit_relay_active_level=0,
                          temperature_enabled=False)
            if self.fault == 'disabled':
                result.update(hardware_control=False, hardware_block_reason='CONTROL_DISABLED')
            if self.fault == 'policy_mismatch':
                result['electrical_limits_enabled'] = False
        if kind == 'measurement':
            if self.fault=='power_check_timeout' and self.power_stage:
                result['electrical_started_ms']=self.power_tick
                result['electrical_completed_ms']=self.power_tick
            if not self.power_stage:
                for key in ('voltage','current','power'):result['measurements'][key]['value']=0.
            result['measurements']['temperature'].update(valid=False, value=None)
            result['temperature_calibrated'] = False
            if self.fault == 'invalid_sensor' and self.state == 'RUNNING':
                result['measurements']['current'].update(value=None,valid=False)
            if self.fault == 'valid_zero':
                for key in ('voltage','current','power'):
                    result['measurements'][key]['value']=0.
            if self.state == 'RUNNING':
                if self.fault == 'stale':
                    result['measurements']['current']['timestamp_ms'] = (self.tick() - 2000) & 0xffffffff
                if self.fault == 'overcurrent':
                    result['measurements']['current']['value'] = 1.5
                if self.fault == 'undervoltage':
                    result['measurements']['voltage']['value'] = 9.9
                if self.fault == 'overvoltage':
                    result['measurements']['voltage']['value'] = 14.1
        if kind == 'ack' and result.get('state') == 'RUNNING' and self.fault == 'bad_start_ack':
            result['applied_pwm_percent'] = 25
        if kind == 'ack' and result.get('state') == 'RUNNING' and self.fault == 'wrong_reply_to':
            payload['reply_to'] += 1000
        super().emit(kind, payload, stamp)


class HardwareRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = json.loads((ROOT / 'deploy/pi/supervised-operator-profile.json').read_text())
        self.profile['serial_identity'] = 'IN_MEMORY_TEST_ONLY'
        self.profile['protection_limits_verified']=True
        self.profile['supply_sensing']['verified']=True
        self.path = self.root / 'profile.json'
        self.path.write_text(json.dumps(self.profile))
        self.fixtures = []
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            engine.close()
        self.temp.cleanup()

    def engine(self, fault='healthy', enabled=True):
        def factory(*_):
            fixture = BenchFixture(fault)
            self.fixtures.append(fixture)
            return STM32SerialConnection(port='IN_MEMORY_ONLY', device_id=fixture.device_id,
                                         command_timeout=.05, require_crc=True, allow_motor_control=True,
                                         transport_factory=lambda *_: fixture)
        engine = AutomatedTestEngine(self.root / f'{len(self.engines)}.db', hardware_profile_path=self.path,
                                     hardware_control_enabled=enabled, connection_factory=factory)
        self.engines.append(engine)
        return engine

    def request(self):
        return dict(mode='hardware', device_id='MOTOR-001', tests=['pwm_50'], duration_ms=300,
                    operator_authorized=True, supervised_confirmed=True)

    def finish(self, engine):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = engine.snapshot()
            if run and run['ended_at']:
                return engine.store.get(run['id'])
            time.sleep(.01)
        self.fail('Run did not terminate')

    def commands(self):
        return [r.payload.get('command', 'HEARTBEAT') for f in self.fixtures for r in f.frames]

    def test_permission_is_off_by_default_and_operator_confirmation_is_separate(self):
        engine = self.engine(enabled=False)
        with self.assertRaisesRegex(RunRejected, 'runtime disabled'):
            engine.start(self.request())
        self.assertFalse(self.fixtures)
        engine = self.engine()
        for name in ('supervised_confirmed', 'operator_authorized'):
            request = self.request()
            request[name] = False
            with self.assertRaises(RunRejected):
                engine.start(request)
        self.assertFalse(self.fixtures)

    def test_read_only_preflight_reports_actual_firmware_blocker_without_motor_writes(self):
        engine = self.engine('disabled')
        report = engine.preflight()
        self.assertFalse(report['ready'])
        self.assertIs(report['firmware_hardware_control'], False)
        self.assertIn('Firmware output blocked: CONTROL_DISABLED', report['reason'])
        self.assertEqual(self.commands(), ['GET_CAPABILITIES', 'GET_STATUS'])

    def test_successful_preflight_then_supervised_run_and_saved_events(self):
        engine = self.engine()
        report = engine.preflight()
        self.assertTrue(report['ready'], report)
        self.assertTrue(any(p['available'] for p in engine.available('hardware')))
        self.assertEqual(self.commands(), ['GET_CAPABILITIES', 'GET_STATUS', 'READ_MEASUREMENTS', 'GET_STATUS'])
        engine.start(self.request())
        run = self.finish(engine)
        self.assertEqual(run['state'], 'COMPLETED', run.get('reason'))
        self.assertIsNone(run['configuration']['scenario'])
        self.assertTrue(run['stop_confirmed'])
        self.assertTrue(any(e.get('payload', {}).get('event') == 'MOTOR_START' for e in run['events']))
        self.assertTrue(any(e.get('payload', {}).get('event') == 'MOTOR_STOP' for e in run['events']))
        self.assertIsNone(run['health_score'])  # No baseline is invented.
        engine.hardware_runtime.checked_at -= 16
        self.assertFalse(engine.hardware_runtime.snapshot()['ready'])

    def test_rejected_start_stale_current_voltage_heartbeat_and_stop_failures(self):
        cases = {'relay_failure':'RELAY_ACTUATION_FAILED','invalid_sensor':'invalid or stale','rejected_start': 'INTERLOCK_OR_SENSOR_FAULT', 'stale': 'invalid or stale',
                 'heartbeat_loss': 'lockout',
                 'stop_failure': 'Stopped state', 'bad_start_ack': 'acknowledgment',
                 'missing_start_event': 'start event missing'}
        for fault, reason in cases.items():
            with self.subTest(fault=fault):
                engine = self.engine(fault)
                engine.start(self.request())
                run = self.finish(engine)
                self.assertEqual(run['state'], 'FAILED', run)
                self.assertIn(reason, run['reason'])
                self.assertIsNone(run['health_score'])
                self.assertEqual(run['stop_confirmed'], fault != 'stop_failure')

    def test_wrong_request_correlation_is_a_disconnect_without_actuation_retry(self):
        engine = self.engine('wrong_reply_to')
        engine.start(self.request())
        run = self.finish(engine)
        self.assertEqual(run['state'], 'DISCONNECTED')
        self.assertEqual(self.commands().count('START_TEST'), 1)
        self.assertTrue(run['stop_confirmed'])

    def test_electrical_policy_mismatch_rejects_before_arm(self):
        engine = self.engine('policy_mismatch')
        engine.start(self.request())
        run = self.finish(engine)
        self.assertIn('electrical-limit policy mismatch', run['reason'])
        self.assertNotIn('ARM_TEST', self.commands())
        self.profile['electrical_limits_enabled'] = False
        self.path.write_text(json.dumps(self.profile))
        with self.assertRaisesRegex(RunRejected, 'electrical_limits_enabled=true'):
            engine.start(self.request())

    def test_voltage_and_current_faults_reject_or_stop_and_confirm_shutdown(self):
        for fault in ('overcurrent','undervoltage','overvoltage','valid_zero'):
            with self.subTest(fault=fault):
                engine=self.engine(fault)
                report=engine.preflight()
                self.assertTrue(report['ready'],report)
                engine.start(self.request());run=self.finish(engine)
                self.assertEqual(run['state'],'FAILED',run)
                self.assertTrue(run['stop_confirmed'])
                self.assertIn('OVERCURRENT' if fault=='overcurrent' else 'SUPPLY_OUT_OF_RANGE',run['reason'])
                if fault=='valid_zero':self.assertNotIn('START_TEST',[r.payload.get('command') for f in self.fixtures[-2:] for r in f.frames])

    def test_contract_rejects_every_mismatched_protection_mode_and_feedback(self):
        report = self.engine().preflight()
        caps, status = report['capabilities'], report['status']
        changes = [('electrical_limits_enabled', False),('protection_limits_verified',False),
                   ('supply_sensing_verified',False),('supply_sensing','UPSTREAM_REQUIRED'),
                   ('min_voltage_mv',9999),('max_voltage_mv',14001),('max_current_ma',2000),
                   ('motor_relay_active_level',1),('circuit_relay_active_level',1),
                   ('fixed_pwm_percent', 100), ('max_duration_ms', 31000),
                   ('operating_mode', 'NORMAL'), ('power_feedback_installed', True),
                   ('heartbeat_timeout_ms', 5000), ('fixed_direction', 'REVERSE'),
                   ('commands', ['READ_MEASUREMENTS']), ('temperature_enabled', True)]
        for field, value in changes:
            with self.subTest(field=field):
                changed = {**caps, field: value}
                with self.assertRaises(RunRejected):
                    HardwareRuntime.validate_contract(self.profile, changed, status, 300)
        wired_profile = {**self.profile, 'power_feedback_installed': True}
        with self.assertRaisesRegex(RunRejected, 'not HIGH'):
            HardwareRuntime.validate_contract(wired_profile, {**caps, 'power_feedback_installed': True}, status, 300)

    def test_valid_firmware_does_not_override_disabled_pi_runtime(self):
        engine = self.engine(enabled=False)
        report = engine.preflight()
        self.assertTrue(report['firmware_hardware_control'])
        self.assertFalse(report['ready'])
        self.assertIn('runtime disabled', report['reason'])
        self.assertFalse(any(p['available'] for p in engine.available('hardware')))
        self.assertTrue(set(self.commands()) <= {'GET_CAPABILITIES', 'GET_STATUS', 'READ_MEASUREMENTS'})

    def test_electrical_endpoints_zero_current_and_outside_range(self):
        raw = dict(sample_sequence=1, electrical_sequence=1, voltage_current_calibrated=True,
                   electrical_started_ms=100, electrical_completed_ms=100,
                   encoder_started_ms=100, encoder_completed_ms=100,
                   measurements={name: dict(value=value, valid=True, unit=unit, timestamp_ms=100)
                                 for name, value, unit in [('voltage', 12., 'V'), ('current', 0., 'A'),
                                                           ('power', 0., 'W'), ('rpm', 0., 'rpm'),
                                                           ('temperature', 0., 'degC')]})
        raw['measurements']['temperature'].update(value=None, valid=False)
        for voltage,current in [(10.,0.),(14.,1.499),(11.9,-1.499)]:
            raw['measurements']['voltage']['value']=voltage
            raw['measurements']['current']['value']=current
            HardwareRuntime.validate_sensors(self.profile,raw,100)
        for voltage,current,reason in [(0.,0.,'SUPPLY_OUT_OF_RANGE'),(.036,0.,'SUPPLY_OUT_OF_RANGE'),
            (9.999,0.,'SUPPLY_OUT_OF_RANGE'),(14.001,0.,'SUPPLY_OUT_OF_RANGE'),(11.9,1.5,'OVERCURRENT'),(11.9,-1.5,'OVERCURRENT')]:
            raw['measurements']['voltage']['value']=voltage
            raw['measurements']['current']['value']=current
            with self.assertRaisesRegex(RunRejected,reason):HardwareRuntime.validate_sensors(self.profile,raw,100)

    def test_guided_procedure_approval_survives_runtime_preflight_gating(self):
        engine = self.engine()
        self.assertTrue(engine.preflight()['ready'])
        available = {p['id']: p['available'] for p in engine.available('hardware')}
        self.assertFalse(available['steady_state'])
        request = {**self.request(), 'tests': ['steady_state'], 'duration_ms': 5000,
                   'load_id': 'FIXTURE_ONLY', 'condition': 'TEST_ONLY'}
        with self.assertRaisesRegex(RunRejected, 'Unavailable procedure'):
            engine.start(request)
        self.profile['additional_procedures_approved'] = ['steady_state']
        self.path.write_text(json.dumps(self.profile))
        available = {p['id']: p['available'] for p in engine.available('hardware')}
        self.assertTrue(available['steady_state'])
        request['duration_ms'] = 300
        with self.assertRaisesRegex(RunRejected, 'at least five seconds'):
            engine.start(request)
        self.assertNotIn('ARM_TEST', self.commands())

    def test_emergency_stop_latches_and_never_restarts(self):
        engine = self.engine()
        request = self.request()
        request['duration_ms'] = 1000
        engine.start(request)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and engine.snapshot().get('state') != 'RUNNING':
            time.sleep(.01)
        engine.stop(True)
        run = self.finish(engine)
        self.assertEqual(run['state'], 'EMERGENCY_STOP')
        self.assertTrue(run['stop_confirmed'])
        self.assertIn('EMERGENCY_STOP', self.commands())
        self.assertEqual(self.fixtures[-1].applied, 0)

    def test_settings_require_explicit_opt_in_and_valid_profile_without_opening_serial(self):
        with patch.dict(os.environ, {'ADS_MODE': 'hardware', 'ADS_HARDWARE_CONTROL_ENABLED': 'true',
                                    'ADS_AUTOMATION_HARDWARE_PROFILE': str(self.path)}, clear=True):
            settings = Settings.from_environment(self.root)
        self.assertTrue(settings.hardware_control_enabled)
        self.assertEqual(settings.mode, 'hardware')
        with patch.dict(os.environ, {'ADS_HARDWARE_CONTROL_ENABLED': 'yes'}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment(self.root)
        self.assertFalse(self.fixtures)

    def test_api_exposes_read_only_preflight_and_keeps_legacy_control_simulated(self):
        import api.main as main
        from fastapi.testclient import TestClient
        with patch.object(main, 'DATABASE_PATH', self.root / 'api.db'), patch.object(
                main, 'settings', replace(main.settings, mode='hardware', hardware_control_enabled=True,
                                         hardware_profile_path=str(self.path))):
            with TestClient(main.app) as client:
                engine = self.engine()
                main.automated_engine.connection_factory = engine.connection_factory
                initial = client.get('/api/motor/hardware/status').json()
                self.assertTrue(initial['profile_ready'])
                self.assertFalse(initial['hardware_control'])
                self.assertIsNone(initial['firmware_hardware_control'])
                report = client.post('/api/motor/hardware/preflight').json()
                self.assertTrue(report['ready'], report)
                self.assertTrue(client.get('/api/motor/hardware/status').json()['hardware_control'])
                health = client.get('/api/health').json()
                self.assertEqual(health['mode'], 'hardware')
                self.assertEqual(health['legacy_control_source'], 'SIMULATION')
                self.assertEqual(client.get('/api/motor/status').json()['source'], 'SIMULATION')

    def test_power_check_rejection_timeout_and_read_only_gate(self):
        from diagnostic_platform.stm32 import HardwareControlDisabled
        readonly=STM32SerialConnection(port='NOT_A_DEVICE',require_crc=True,allow_motor_control=False)
        with self.assertRaises(HardwareControlDisabled):readonly.execute('PREPARE_TEST_POWER')
        for fault in ('power_check_rejected','power_check_timeout'):
            e=self.engine(fault);e.start(self.request());run=self.finish(e)
            self.assertEqual(run['state'],'FAILED',run)
            self.assertTrue(run['stop_confirmed'])
            requests=[f.payload.get('command') for f in self.fixtures[-1].frames]
            self.assertIn('PREPARE_TEST_POWER',requests);self.assertNotIn('START_TEST',requests)
            self.assertEqual(requests.count('PREPARE_TEST_POWER'),1)

    def test_cancel_during_power_check_and_relay_stop_confirmation(self):
        e=self.engine('power_check_timeout');e.start(self.request())
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            if self.fixtures and self.fixtures[-1].power_stage:break
            time.sleep(.005)
        e.stop(True);run=self.finish(e)
        self.assertEqual(run['state'],'EMERGENCY_STOP',run)
        self.assertTrue(run['stop_confirmed'])
        self.assertNotIn('START_TEST',[f.payload.get('command') for f in self.fixtures[-1].frames])
        self.assertFalse(e._stopped(dict(accepted=True,state='STOPPED',applied_pwm_percent=0,
                                       power_check_required=True,motor_relay_requested_on=True)))
