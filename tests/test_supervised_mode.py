"""Synthetic GPIO and protocol checks; these do not certify real hardware."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tests import test_bounded_motor as bounded
FAKE_BOARD_DEFINES=bounded.FAKE_BOARD_DEFINES
from diagnostic_platform.automated_engine import AutomatedTestEngine,load_hardware_profile,RunRejected

ROOT=Path(__file__).resolve().parents[1]
class SupervisedProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):bounded.BoundedMotorTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):bounded.BoundedMotorTests.tearDownClass.__func__(cls)
    exchange=bounded.BoundedMotorTests.exchange
    frame=bounded.BoundedMotorTests.frame
    heartbeat=bounded.BoundedMotorTests.heartbeat
    def test_supervised_confirmation_is_fresh_strict_and_cleared_on_stop(self):
        arm=lambda seq,**args:self.frame('ARM_TEST',seq,**args)
        for args in ({},{'supervised_confirmed':False},{'supervised_confirmed':1},
                     {'supervised_confirmed':'true'},{'nested':{'supervised_confirmed':True}}):
            out=self.exchange([self.heartbeat(),arm(2,**args)],'supervised')
            self.assertEqual(out[-1].payload['result']['reason'],'SUPERVISED_OPERATOR_CONFIRMATION_REQUIRED')
        out=self.exchange([self.heartbeat(),arm(2,supervised_confirmed=True),
            self.frame('START_TEST',3,pwm_percent=10,duration_ms=1000,direction='FORWARD'),
            self.frame('STOP_TEST',4),self.heartbeat(5),arm(6),arm(7,supervised_confirmed=True)],'supervised')
        replies=[m.payload['result'] for m in out if m.message_type.value!='event']
        self.assertTrue(replies[1]['accepted']);self.assertTrue(replies[2]['supervised_confirmed'])
        self.assertFalse(replies[3]['supervised_confirmed'])
        self.assertFalse(replies[-2]['accepted']);self.assertTrue(replies[-1]['accepted'])
        self.assertEqual(replies[-1]['power_feedback_state'],'NOT_INSTALLED')
        self.assertEqual(replies[-1]['operating_mode'],'SUPERVISED_TEST')
    def test_supervised_grant_clears_on_heartbeat_fault_and_clear_faults_needs_confirmation(self):
        out=self.exchange([self.heartbeat(),self.frame('ARM_TEST',2,supervised_confirmed=True),
            b'@@',self.frame('GET_STATUS',3),self.heartbeat(4),self.frame('CLEAR_FAULTS',5),
            self.frame('ARM_TEST',6,supervised_confirmed=True)],'supervised')
        replies=[m.payload['result'] for m in out if m.message_type.value!='event']
        status=next(r for r in replies if r.get('state')=='LOCKOUT')
        self.assertFalse(status['supervised_confirmed'])
        self.assertEqual(replies[-2]['reason'],'SUPERVISED_OPERATOR_CONFIRMATION_REQUIRED')
        self.assertTrue(replies[-1]['accepted'])

    def test_capabilities_label_operator_verified_limits_and_no_feedback(self):
        cap=self.exchange([self.frame('GET_CAPABILITIES',1)],'supervised')[0].payload['result']
        self.assertEqual(cap['operating_mode'],'SUPERVISED_TEST')
        self.assertFalse(cap['power_feedback_installed']);self.assertTrue(cap['electrical_limits_enabled'])
        self.assertEqual(cap['min_voltage_mv'],10000);self.assertEqual(cap['max_current_ma'],1500)

class PowerFeedbackTests(unittest.TestCase):
    def test_normal_and_supervised_pin_mapping_shutdown_and_unverified_gates(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            for mode,installed,wiring,approval,limits in [(0,1,1,0,1),(0,0,0,0,1),
                (0,1,0,0,1),(1,0,0,1,1),(1,1,1,1,1),(1,0,0,0,1),(1,0,0,1,0)]:
                flags=[f for f in FAKE_BOARD_DEFINES if not f.startswith('ADS_PROTECTION_LIMITS_VERIFIED=')]
                flags += [f'ADS_PROTECTION_LIMITS_VERIFIED={limits}',f'ADS_MOTOR_OPERATING_MODE={mode}',
                    f'ADS_POWER_FEEDBACK_INSTALLED={installed}',f'ADS_POWER_FEEDBACK_WIRING_VERIFIED={wiring}',
                    f'ADS_SUPERVISED_TESTING_APPROVED={approval}','ADS_RELAY_ACTIVE_LEVEL=1']
                exe=Path(directory)/'feedback'
                with self.subTest(mode=mode,installed=installed,wiring=wiring,approval=approval,limits=limits):
                    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                        '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),*('-D'+f for f in flags),
                        str(ROOT/'ADS/Core/Src/ads_motor.c'),str(ROOT/'tests/power_feedback_harness.c'),'-o',str(exe)],
                        check=True,capture_output=True)
                    subprocess.run([str(exe)],check=True)
    def test_pc8_paths_compile_against_real_f401_headers(self):
        candidates=list(Path('/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins').glob(
            'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gcc'))
        cc=shutil.which('arm-none-eabi-gcc') or (str(candidates[0]) if candidates else None)
        if not cc:self.skipTest('ARM toolchain unavailable')
        includes=['Core/Inc','Drivers/STM32F4xx_HAL_Driver/Inc','Drivers/STM32F4xx_HAL_Driver/Inc/Legacy',
                  'Drivers/CMSIS/Include','Drivers/CMSIS/Device/ST/STM32F4xx/Include']
        for mode in (0,1):
            subprocess.run([cc,'-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard',
                '-std=gnu11','-Wall','-Wextra','-Werror','-fsyntax-only','-DUSE_HAL_DRIVER','-DSTM32F401xE',
                *('-I'+i for i in includes),*('-D'+f for f in FAKE_BOARD_DEFINES),
                '-DADS_RELAY_ACTIVE_LEVEL=1','-DADS_POWER_FEEDBACK_INSTALLED=1','-DADS_POWER_FEEDBACK_WIRING_VERIFIED=1',
                '-DADS_SUPERVISED_TESTING_APPROVED=1',f'-DADS_MOTOR_OPERATING_MODE={mode}',
                'Core/Src/ads_motor.c','Core/Src/main.c'],cwd=ROOT/'ADS',check=True,capture_output=True)

    def test_profile_supervision_does_not_claim_a_normal_interlock(self):
        profile=json.loads((ROOT/'deploy/pi/supervised-hardware-profile.example.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json';path.write_text(json.dumps(profile))
            with self.assertRaises(RunRejected):load_hardware_profile(path)
            for key in ('wiring_verified','relay_verified','kill_switch_verified','communication_stop_verified',
                        'calibration_verified','operator_enable','protection_limits_verified','supervised_testing_approved'):
                profile[key]=True # Test fixture only, not bench approval.
            profile['supply_sensing']['verified']=True
            profile.update(evidence_id='FAKE',calibration_id='FAKE',fixture_id='FAKE',serial_identity='FAKE')
            path.write_text(json.dumps(profile));self.assertEqual(load_hardware_profile(path)['operating_mode'],'SUPERVISED_TEST')
            self.assertFalse(profile['interlock_verified']);self.assertFalse(profile['power_feedback_installed'])
            engine=AutomatedTestEngine(Path(directory)/'runs.db',hardware_profile_path=path,hardware_control_enabled=True)
            try:
                with self.assertRaisesRegex(RunRejected,'Fresh supervised'):
                    engine.start({'mode':'hardware','device_id':'MOTOR-001','tests':['pwm_50'],'operator_authorized':True})
            finally:engine.close()
            profile['operating_mode']='NORMAL';path.write_text(json.dumps(profile))
            with self.assertRaises(RunRejected):load_hardware_profile(path)

class SupervisedEngineTests(unittest.TestCase):
    def test_fake_hardware_sequence_confirms_mode_and_rejects_mismatch(self):
        from diagnostic_platform.device_simulator import STM32Simulator
        from diagnostic_platform.stm32 import STM32SerialConnection
        import time
        from tests.test_hardware_runtime import BenchFixture
        class Fixture(BenchFixture):
            def __init__(self,mode):super().__init__();self.fixture_mode=mode
            def emit(self,kind,payload,stamp=None):
                super().emit(kind,payload,stamp)
                if kind=='capabilities' and self.fixture_mode=='NORMAL':
                    from diagnostic_platform.protocol import decode_message,encode_message
                    message=decode_message(self.responses.pop());message.payload['result']['operating_mode']='NORMAL'
                    self.responses.append(encode_message(message,checksum=True))
        for firmware_mode in ('SUPERVISED_TEST','NORMAL'):
            with self.subTest(firmware_mode=firmware_mode),tempfile.TemporaryDirectory() as directory:
                profile=json.loads((ROOT/'deploy/pi/supervised-hardware-profile.example.json').read_text())
                for key in ('wiring_verified','relay_verified','kill_switch_verified','communication_stop_verified',
                            'calibration_verified','operator_enable','protection_limits_verified','supervised_testing_approved'):
                    profile[key]=True # Synthetic fixture approvals only.
                profile['supply_sensing']['verified']=True
                profile.update(evidence_id='FAKE',calibration_id='FAKE',fixture_id='FAKE',serial_identity='FAKE')
                path=Path(directory)/'profile.json';path.write_text(json.dumps(profile))
                fixtures=[]
                def factory(*_):
                    fixture=Fixture(firmware_mode);fixtures.append(fixture)
                    return STM32SerialConnection(port='IN_MEMORY_ONLY',device_id=fixture.device_id,
                        require_crc=True,allow_motor_control=True,transport_factory=lambda *_:fixture)
                engine=AutomatedTestEngine(Path(directory)/'runs.db',hardware_profile_path=path,connection_factory=factory,hardware_control_enabled=True)
                try:
                    run=engine.start({'mode':'hardware','device_id':'MOTOR-001','tests':['pwm_50'],
                        'duration_ms':300,'operator_authorized':True,'supervised_confirmed':True})
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        result=engine.snapshot()
                        if result['ended_at']:break
                        time.sleep(.02)
                    self.assertTrue(result['ended_at'])
                    requests=[f for fixture in fixtures for f in fixture.frames]
                    arms=[f for f in requests if f.payload.get('command')=='ARM_TEST']
                    if firmware_mode=='SUPERVISED_TEST':
                        self.assertEqual(result['state'],'COMPLETED',result.get('reason'))
                        self.assertTrue(arms[0].payload['arguments']['supervised_confirmed'])
                        self.assertEqual(result['power_feedback_state'],'NOT_INSTALLED')
                        saved=engine.store.get(run['id'])
                        self.assertEqual(saved['configuration']['operating_mode'],'SUPERVISED_TEST')
                        self.assertIn('SUPERVISED_TEST',Path(saved['csv_path']).read_text())
                    else:
                        self.assertEqual(result['state'],'FAILED')
                        self.assertIn('operating mode mismatch',result['reason'])
                        self.assertFalse(arms)
                finally:engine.close()
