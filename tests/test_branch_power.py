"""Branch selection and bounded circuit power over an in-memory ADS peer only."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import api.main as main
from diagnostic_platform.automated_engine import AutomatedTestEngine, RunRejected
from diagnostic_platform.ina219 import normalize_branches
from diagnostic_platform.protocol import decode_message
from diagnostic_platform.stm32 import STM32SerialConnection
from tests.test_hardware_runtime import BenchFixture, ROOT


class CircuitPeer(BenchFixture):
    def __init__(self, fault='healthy'):
        super().__init__(fault)
        self.cstate='DISARMED'; self.cseq=0; self.cstarted=0; self.cduration=0; self.creason='NONE'

    def cstatus(self):
        if self.cstate in ('ARMED','RUNNING') and self.tick()-self.last_heartbeat>=2000:
            self.cstate='LOCKOUT'; self.creason='HEARTBEAT_LOSS'
        elif self.cstate=='RUNNING' and self.fault!='circuit_stop_failure' and self.tick()-self.cstarted>=self.cduration:
            self.cstate='STOPPED'; self.creason='COMPLETED'
        return dict(state=self.cstate,power_on=self.cstate=='RUNNING',last_control_seq=self.cseq,
                    started_ms=self.cstarted,stop_reason=self.creason)

    def write(self, frame):
        r=decode_message(frame); cmd=r.payload.get('command'); args=r.payload.get('arguments',{})
        self.cstatus()
        if cmd in ('GET_CIRCUIT_STATUS','ARM_CIRCUIT','START_CIRCUIT','STOP_CIRCUIT'):
            self.frames.append(r); accepted=True; reason='NONE'
            if cmd=='ARM_CIRCUIT':
                self.cseq=r.sequence; self.cstate='ARMED'
            elif cmd=='START_CIRCUIT':
                self.cseq=r.sequence
                if self.fault=='reject_circuit':accepted=False;reason='INTERLOCK_OR_SENSOR_FAULT'
                else:self.cstate='RUNNING';self.cstarted=self.tick();self.cduration=args['duration_ms']
            elif cmd=='STOP_CIRCUIT':
                if self.fault!='circuit_stop_failure':self.cstate='STOPPED'
            self.emit('ack',{'reply_to':r.sequence,'result':{**self.cstatus(),'accepted':accepted,'reason':reason}})
            return len(frame)
        return super().write(frame)

    def emit(self, kind, payload, stamp=None):
        payload=copy.deepcopy(payload); result=payload.get('result',{})
        if kind=='capabilities':
            result.update(circuit_power_control=self.fault!='old_firmware',circuit_max_duration_ms=30000,
                          circuit_relay='D5/PB4/IN2')
            result['commands']=result.get('commands',[])+['GET_CIRCUIT_STATUS','ARM_CIRCUIT','START_CIRCUIT','STOP_CIRCUIT']
        if kind=='measurement':
            motor=normalize_branches(result)['MOTOR']
            branch=copy.deepcopy(motor)
            branch.update(address=0x41,calibrated=False)
            for channel,v in [('voltage',5.),('current',0.),('power',0.)]:
                branch['measurements'][channel]['value']=v
            if self.fault=='circuit_stale':
                branch['timestamp_ms']=(self.tick()-2000)&0xffffffff
                for item in branch['measurements'].values():item['timestamp_ms']=branch['timestamp_ms']
            if self.fault=='circuit_missing':
                branch.update(connected=False,valid=False,status='NOT_CONNECTED')
                for item in branch['measurements'].values():item.update(valid=False,value=None)
            result['ina219']={'MOTOR':motor,'CIRCUIT':branch}
        super().emit(kind,payload,stamp)


class BranchPowerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name);self.engines=[];self.peers=[]
        self.profile=json.loads((ROOT/'deploy/pi/supervised-operator-profile.json').read_text())
        self.profile['protection_limits_verified']=True;self.profile['supply_sensing']['verified']=True
        self.profile['serial_identity']='IN_MEMORY_ONLY';self.path=self.root/'profile.json'
        self.path.write_text(json.dumps(self.profile))

    def tearDown(self):
        for e in self.engines:e.close()
        self.temp.cleanup()

    def engine(self, fault='healthy', enabled=True):
        def factory(*_):
            peer=CircuitPeer(fault);self.peers.append(peer)
            return STM32SerialConnection(port='IN_MEMORY_ONLY',device_id=peer.device_id,
                command_timeout=.05,require_crc=True,allow_motor_control=True,transport_factory=lambda *_:peer)
        e=AutomatedTestEngine(self.root/f'{len(self.engines)}.db',hardware_profile_path=self.path,
                             connection_factory=factory,hardware_control_enabled=enabled)
        self.engines.append(e);return e

    def finish(self, e):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            s=e.circuit_power.snapshot()
            if s and s['ended_at']:return s
            time.sleep(.005)
        self.fail('Circuit owner failed to terminate')

    def test_selection_has_no_io_and_requires_separate_authorized_power_action(self):
        e=self.engine();service=e.circuit_power
        self.assertFalse(service.select('CIRCUIT')['power_changed']);self.assertEqual(self.peers,[])
        with self.assertRaises(RunRejected):service.start(100,False)
        service.select('MOTOR')
        with self.assertRaises(RunRejected):service.start(100,True)
        self.assertEqual(self.peers,[])
        disabled=self.engine(enabled=False);disabled.circuit_power.select('CIRCUIT')
        with self.assertRaisesRegex(RunRejected,'runtime disabled'):disabled.circuit_power.start(100,True)
        self.assertEqual(self.peers,[])

    def test_power_session_records_only_circuit_sensor_and_valid_zero(self):
        e=self.engine();e.circuit_power.select('CIRCUIT');e.circuit_power.start(100,True)
        result=self.finish(e);self.assertEqual(result['state'],'STOPPED',result)
        self.assertTrue(result['stop_confirmed']);self.assertFalse(result['power_on'])
        self.assertEqual(result['measurements']['measurements']['voltage']['value'],5.)
        self.assertEqual(result['measurements']['measurements']['current']['value'],0.)
        self.assertIsNone(result['health_score'])
        with e.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM branch_power_samples').fetchone()[0],1)
        commands=[f.payload.get('command') for f in self.peers[0].frames]
        self.assertIn('START_CIRCUIT',commands);self.assertNotIn('START_TEST',commands)

    def test_cancel_and_cross_branch_exclusion(self):
        e=self.engine();e.circuit_power.select('CIRCUIT');e.circuit_power.start(2000,True)
        with self.assertRaises(RunRejected):e.circuit_power.select('MOTOR')
        with self.assertRaises(RunRejected):e.start(dict(mode='hardware'))
        deadline=time.monotonic()+1
        while time.monotonic()<deadline and e.circuit_power.snapshot()['state']!='POWERED':time.sleep(.005)
        e.stop(emergency=True)
        result=self.finish(e);self.assertFalse(result['power_on']);self.assertTrue(result['stop_confirmed'])
        e.circuit_power.select('MOTOR')

    def test_rejections_stale_missing_and_unconfirmed_stop(self):
        for fault in ('old_firmware','reject_circuit','circuit_stale','circuit_missing','circuit_stop_failure'):
            with self.subTest(fault=fault):
                e=self.engine(fault);e.circuit_power.select('CIRCUIT');e.circuit_power.start(100,True)
                result=self.finish(e);self.assertEqual(result['state'],'FAILED',result)
                self.assertTrue(result['reason'])
                if fault=='circuit_stop_failure':
                    self.assertIsNone(result['power_on']);self.assertFalse(result['stop_confirmed'])
                if fault=='old_firmware':
                    self.assertNotIn('START_CIRCUIT',[f.payload.get('command') for f in self.peers[-1].frames])

    def test_api_selection_no_transport_and_default_runtime_blocks_power(self):
        previous=main.DATABASE_PATH;main.DATABASE_PATH=self.root/'api.db'
        try:
            with TestClient(main.app) as client, patch('diagnostic_platform.hardware_runtime.HardwareRuntime.connection') as connection:
                response=client.post('/api/station/select',json={'branch':'CIRCUIT'})
                self.assertEqual(response.status_code,200);self.assertFalse(response.json()['power_changed'])
                self.assertEqual(client.get('/api/station/status').json()['selected_branch'],'CIRCUIT')
                self.assertEqual(client.post('/api/station/circuit/power',json={'on':True,'supervised_confirmed':True}).status_code,409)
                self.assertEqual(client.post('/api/station/circuit/power',json={'on':'true'}).status_code,422)
                self.assertEqual(client.post('/api/station/circuit/power',json={'on':False}).status_code,200)
                connection.assert_not_called()
        finally:main.DATABASE_PATH=previous

    def test_api_real_protocol_peer_power_and_csv_export(self):
        previous=main.DATABASE_PATH;main.DATABASE_PATH=self.root/'api-export.db'
        try:
            with TestClient(main.app) as client:
                e=self.engine()
                with patch.object(main,'automated_engine',e):
                    self.assertEqual(client.post('/api/station/select',json={'branch':'CIRCUIT'}).status_code,200)
                    response=client.post('/api/station/circuit/power',json={'on':True,'duration_ms':100,'supervised_confirmed':True})
                    self.assertEqual(response.status_code,200,response.text)
                    result=self.finish(e)
                    csv=client.get('/api/station/circuit/'+result['id']+'/csv')
                    self.assertEqual(csv.status_code,200);self.assertIn('CIRCUIT',csv.text)
                    self.assertIn('stm32_serial',csv.text);self.assertIn('voltage_V',csv.text)
                    self.assertEqual(client.get('/api/station/status').json()['circuit']['state'],'STOPPED')
        finally:main.DATABASE_PATH=previous
