import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import api.main as main

class AutomatedApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.previous=main.DATABASE_PATH
        main.DATABASE_PATH=Path(self.temp.name)/'test.db'
        self.context=TestClient(main.app);self.client=self.context.__enter__()
    def tearDown(self):
        self.context.__exit__(None,None,None);main.DATABASE_PATH=self.previous;self.temp.cleanup()
    def test_full_api_sequence_stream_results_and_export(self):
        registry=self.client.get('/api/automated/registry').json()
        self.assertEqual(sum(p['available'] for p in registry),11)
        response=self.client.post('/api/automated/runs',json={'run_all':True,'duration_ms':300})
        self.assertEqual(response.status_code,201,response.text)
        run=response.json()
        with self.client.websocket_connect('/ws/automated/'+run['id']) as socket:
            messages=[]
            while True:
                message=socket.receive_json();messages.append(message)
                if message['ended_at']:break
        self.assertEqual(messages[-1]['state'],'COMPLETED',messages[-1].get('reason'))
        self.assertTrue(any(m.get('latest_measurement') for m in messages))
        result=self.client.get('/api/automated/runs/'+run['id']).json()
        self.assertTrue(result['samples']);self.assertEqual(result['source'],'SIMULATION')
        self.assertEqual(len(result['steps']),6)
        report=self.client.get('/api/automated/runs/'+run['id']+'/report')
        self.assertEqual(report.status_code,200)
        self.assertIn('attachment',report.headers['content-disposition'])
        self.assertEqual(report.json()['id'],run['id'])
        csv=self.client.get('/api/automated/runs/'+run['id']+'/csv')
        self.assertEqual(csv.status_code,200)
        self.assertIn('requested_pwm_percent',csv.text)
        self.assertIn('SIMULATION',csv.text)
        self.assertTrue(Path(result['csv_path']).exists())
        status=self.client.get('/api/motor/hardware/status').json()
        self.assertFalse(status['profile_ready'])
        self.assertIsNone(status['active_run'])
    def test_unavailable_hardware_and_bad_configuration(self):
        self.assertEqual(self.client.post('/api/automated/runs',json={'mode':'hardware','tests':['pwm_10']}).status_code,409)
        self.assertEqual(self.client.post('/api/automated/runs',json={'tests':['continuity']}).status_code,409)
        self.assertEqual(self.client.post('/api/automated/runs',json={'duration_ms':-1,'tests':['idle']}).status_code,422)
        self.assertEqual(self.client.get('/api/automated/runs/missing').status_code,404)
    def test_concurrent_browsers_cannot_start_conflicting_sequences(self):
        run=self.client.post('/api/automated/runs',json={'tests':['pwm_10'],'duration_ms':2000}).json()
        second=self.client.post('/api/automated/runs',json={'tests':['idle']})
        self.assertEqual(second.status_code,409)
        stop=self.client.post('/api/automated/runs/'+run['id']+'/stop?emergency=true')
        self.assertTrue(stop.json()['accepted'])
        for _ in range(100):
            result=self.client.get('/api/automated/runs/'+run['id']).json()
            if result['ended_at']:break
            time.sleep(.01)
        self.assertEqual(result['state'],'EMERGENCY_STOP')
        self.assertIsNone(result['health_score'])

    def test_circuit_simulation_capture_requires_backend_sequence(self):
        profiles=self.client.get('/api/circuits/profiles').json()['profiles']
        payload={'profile_id':profiles[0]['profile_id'],'mode':'DIAGNOSE','scenario':'healthy'}
        response=self.client.post('/api/circuits/run',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        report=response.json();identifier=report['run_id']
        self.assertEqual(report['execution_state'],'IN_PROGRESS')
        self.assertEqual(self.client.post(f'/api/circuits/simulated-runs/{identifier}/capture?index=1').status_code,409)
        for i in range(len(report['steps'])):
            report=self.client.post(f'/api/circuits/simulated-runs/{identifier}/capture?index={i}').json()
        self.assertEqual(report['execution_state'],'COMPLETED')
        self.assertEqual(report['source'],'SIMULATION')
        self.assertEqual(self.client.get('/api/circuits/capabilities').json()['continuity']['status'],'UNSUPPORTED')

    def test_supervised_operator_confirmation_must_be_a_boolean(self):
        response=self.client.post('/api/automated/runs',json={'mode':'hardware','tests':['pwm_50'],
            'operator_authorized':True,'supervised_confirmed':'true'})
        self.assertEqual(response.status_code,422)
        status=self.client.get('/api/motor/hardware/status').json()
        self.assertEqual(status['operating_mode'],'NORMAL')
        self.assertFalse(status['profile_ready'])
