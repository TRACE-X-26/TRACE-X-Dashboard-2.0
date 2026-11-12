import csv
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from diagnostic_platform.protocol import CommandName,command_message,encode_message,decode_message
from diagnostic_platform.ina219 import normalize_branches
from diagnostic_platform.live import LiveMonitor
from diagnostic_platform.collector import ExperimentRecorder
from diagnostic_platform.motor_csv import render_motor_csv
from diagnostic_platform.automated_engine import AutomatedTestEngine

ROOT=Path(__file__).resolve().parents[1]
class DualINA219Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('cc')
        if not compiler:raise unittest.SkipTest('Host C compiler unavailable')
        cls.temp=tempfile.TemporaryDirectory();cls.exe=str(Path(cls.temp.name)/'dual')
        subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'ADS/Core/Inc'),
            *(str(ROOT/'ADS/Core/Src'/p) for p in ('ads_ina219.c','ads_acquisition.c','ads_protocol.c','ads_test.c')),
            str(ROOT/'tests/dual_ina219_harness.c'),'-o',cls.exe],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def result(self,mode='normal'):
        frame=encode_message(command_message(CommandName.READ_MEASUREMENTS,42),checksum=True)
        output=subprocess.check_output([self.exe,mode],input=frame)
        self.assertLess(len(output),4096)
        message=decode_message(output)
        self.assertEqual(message.payload['reply_to'],42)
        return message.payload['result']
    def test_driver_addresses_independent_configuration_failure_and_recovery(self):
        subprocess.run([self.exe],check=True)
    def test_production_c_protocol_preserves_motor_fields_and_separate_circuit(self):
        result=self.result();branches=normalize_branches(result)
        self.assertEqual(result['measurements']['voltage']['value'],12)
        self.assertEqual(branches['MOTOR']['address'],64);self.assertEqual(branches['CIRCUIT']['address'],65)
        self.assertEqual(branches['CIRCUIT']['measurements']['voltage']['value'],5)
        self.assertEqual(branches['MOTOR']['measurements']['current']['value'],.1)
        self.assertEqual(branches['CIRCUIT']['measurements']['current']['value'],-.2)
        self.assertFalse(branches['CIRCUIT']['calibrated'])
    def test_missing_motor_does_not_invalidate_circuit(self):
        result=self.result('motor_missing');branches=normalize_branches(result)
        self.assertFalse(result['measurements']['voltage']['valid'])
        self.assertFalse(branches['MOTOR']['connected']);self.assertTrue(branches['CIRCUIT']['valid'])
    def test_circuit_errors_do_not_change_motor(self):
        for mode,status in [('circuit_missing','NOT_CONNECTED'),('timeout','CONVERSION_TIMEOUT'),
                            ('overflow','OVERFLOW'),('read_error','READ_ERROR')]:
            with self.subTest(mode=mode):
                result=self.result(mode);b=normalize_branches(result)
                self.assertTrue(result['measurements']['current']['valid'])
                self.assertTrue(b['MOTOR']['valid']);self.assertFalse(b['CIRCUIT']['valid'])
                self.assertEqual(b['CIRCUIT']['status'],status)
                self.assertIsNone(b['CIRCUIT']['measurements']['current']['value'])
    def test_valid_zero_and_live_dashboard_independent_invalidation(self):
        zero=normalize_branches(self.result('zero'))
        self.assertTrue(zero['CIRCUIT']['valid']);self.assertEqual(zero['CIRCUIT']['measurements']['current']['value'],0)
        monitor=LiveMonitor();monitor.publish_acquisition(self.result())
        self.assertEqual(monitor.snapshot()['ina219']['CIRCUIT']['measurements']['voltage']['value'],5)
        monitor.publish_acquisition(self.result('circuit_missing'))
        state=monitor.snapshot();self.assertTrue(state['ina219']['MOTOR']['valid'])
        self.assertFalse(state['ina219']['CIRCUIT']['valid'])
        self.assertEqual(state['channels']['voltage']['value'],12)
        monitor.publish_acquisition(None);self.assertTrue(monitor.snapshot()['ina219']['CIRCUIT']['stale'])
        self.assertFalse(monitor.snapshot()['ina219']['MOTOR']['valid'])
        self.assertIsNone(monitor.snapshot()['ina219']['MOTOR']['measurements']['current']['value'])
    def test_malformed_circuit_isolated_and_no_address_substitution(self):
        result=self.result();result['ina219']['CIRCUIT']['address']=64
        branches=normalize_branches(result)
        self.assertTrue(branches['MOTOR']['valid']);self.assertEqual(branches['CIRCUIT']['status'],'MALFORMED')
    def test_both_csv_paths_keep_separate_values_and_status(self):
        result=self.result()
        with tempfile.TemporaryDirectory() as directory:
            recorder=ExperimentRecorder(directory,'dual');recorder.record(result);recorder.close()
            with recorder.path.open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),8)
            self.assertEqual(next(r['value'] for r in rows if r['branch']=='CIRCUIT' and r['channel']=='voltage'),'5.0')
        run=dict(id='fixture',source='SIMULATION',state='COMPLETED',samples=[dict(received_at='now',quality=[],raw=result)])
        rows=list(csv.DictReader(io.StringIO(render_motor_csv(run))))
        self.assertEqual(rows[0]['circuit_voltage_V'],'5.0');self.assertEqual(rows[0]['voltage_V'],'12.0')
    def test_read_only_monitor_only_reads_and_yields_to_motor_owner(self):
        class Connection:
            commands=[]
            def connect(self):pass
            def disconnect(self):pass
            def execute(self,command):self.commands.append(command);return {'fixture':True}
        with tempfile.TemporaryDirectory() as directory:
            engine=AutomatedTestEngine(Path(directory)/'runs.db');connection=Connection()
            try:
                self.assertEqual(engine.read_sensors('fixture',lambda:connection),{'fixture':True})
                self.assertEqual(connection.commands,['READ_MEASUREMENTS'])
                engine._mutex.acquire()
                try:self.assertIsNone(engine.read_sensors('fixture',lambda:connection))
                finally:engine._mutex.release()
                self.assertEqual(connection.commands,['READ_MEASUREMENTS'])
            finally:engine.close()

    def test_verifier_reads_both_without_motor_commands(self):
        from diagnostic_platform.verify_ina219 import verify
        payload=self.result()
        class Connection:
            commands=[]
            def connect(self):pass
            def disconnect(self):pass
            def execute(self,command):
                self.commands.append(command)
                return {'firmware_version':'fixture'} if command=='GET_CAPABILITIES' else payload
        connection=Connection();result=verify(connection,samples=2,interval=0)
        self.assertTrue(result['passed'])
        self.assertEqual(connection.commands,['GET_CAPABILITIES','READ_MEASUREMENTS','READ_MEASUREMENTS'])
        self.assertEqual(result['valid_sample_counts'],{'MOTOR':2,'CIRCUIT':2})

    def test_backend_motor_limits_ignore_circuit_current_and_circuit_failure(self):
        from diagnostic_platform.test_registry import REGISTRY
        from diagnostic_platform.stm32 import STM32SerialConnection
        from diagnostic_platform.device_simulator import STM32Simulator
        import copy
        for failure in (False,True):
            with tempfile.TemporaryDirectory() as directory:
                engine=AutomatedTestEngine(Path(directory)/'runs.db')
                device=STM32Simulator();connection=STM32SerialConnection(port='SIMULATION',device_id=device.device_id,
                    require_crc=True,transport_factory=lambda *_:device)
                connection.connect();execute=connection.execute
                branch=self.result('circuit_missing' if failure else 'normal')['ina219']['CIRCUIT']
                if not failure:
                    branch['measurements']['current']['value']=1000
                    branch['measurements']['power']['value']=5000
                def read(command,*args,**kwargs):
                    result=execute(command,*args,**kwargs)
                    if command=='READ_MEASUREMENTS':
                        result=copy.deepcopy(result)
                        motor=normalize_branches(result)['MOTOR']
                        result['ina219']={'MOTOR':motor,'CIRCUIT':branch}
                    return result
                connection.execute=read
                run=dict(id='fixture',created_at='now',mode='simulation',state='PRECHECK',source='SIMULATION',steps=[],
                    commissioning={'limits':{'max_current':1,'min_voltage':9,'max_voltage':15,'max_temperature':80}})
                engine.store.create(run);step={'samples':[],'device_session_id':'fixture'}
                try:
                    engine._measure(connection,run,REGISTRY['pwm_10'],step,None)
                    self.assertEqual(run['latest_measurement']['current'],.1)
                    self.assertEqual(run['latest_measurement']['ina219']['CIRCUIT']['valid'],not failure)
                    self.assertNotIn('confirmed_limit_faults',run)
                finally:connection.disconnect();engine.store.release('fixture');engine.close()

    def test_api_and_live_websocket_expose_both_branches(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import api.main as main
        monitor=LiveMonitor()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main,'DATABASE_PATH',Path(directory)/'test.db'),patch.object(main,'live_monitor',monitor):
                with TestClient(main.app) as client:
                    monitor.publish_acquisition(self.result())
                    result=client.get('/api/live/status')
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(result.json()['ina219']['MOTOR']['address'],64)
                    self.assertEqual(result.json()['ina219']['CIRCUIT']['address'],65)
                    with client.websocket_connect('/ws/live') as socket:
                        self.assertEqual(socket.receive_json()['ina219']['CIRCUIT']['measurements']['voltage']['value'],5)

    def test_read_only_service_publishes_and_records_both_branches(self):
        from diagnostic_platform.sensor_monitor import SensorMonitor
        payload=self.result();published=[]
        class Engine:
            def read_sensors(self,port):
                self.monitor._stop.set();return payload
        engine=Engine()
        with tempfile.TemporaryDirectory() as directory:
            monitor=SensorMonitor(engine,'fixture',published.append,directory);engine.monitor=monitor
            monitor._run() # One deterministic poll, no physical connection/thread.
            self.assertEqual(published,[payload])
            path=next(Path(directory).glob('*.csv'))
            with path.open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual({r['branch'] for r in rows},{'MOTOR','CIRCUIT'})
