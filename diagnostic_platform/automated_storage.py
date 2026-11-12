"""Additive, numbered SQLite migration and durable automated-test journal."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def utcnow(): return datetime.now(timezone.utc).isoformat()
ACTIVE=('IDLE','PRECHECK','ARMED','RUNNING','STOPPING','ANALYZING')

def run_summary(run):
    if run is None:return None
    return {**run,'steps':[{**{k:v for k,v in step.items() if k!='samples'},
                           'sample_count':len(step.get('samples',[]))} for step in run.get('steps',[])]}

class RunStore:
    def __init__(self,path):
        self.path=str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS automated_runs(
              id TEXT PRIMARY KEY, state TEXT NOT NULL, mode TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, record_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS automated_samples(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES automated_runs(id),
              received_at TEXT NOT NULL, raw_json TEXT NOT NULL, quality_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS automated_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES automated_runs(id),
              received_at TEXT NOT NULL, event_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS simulated_circuit_runs(
              id TEXT PRIMARY KEY, captured INTEGER NOT NULL DEFAULT 0, report_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS automated_ownership(id INTEGER PRIMARY KEY CHECK(id=1),run_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS branch_power_sessions(id TEXT PRIMARY KEY, record_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS branch_power_samples(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES branch_power_sessions(id), received_at TEXT NOT NULL, record_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS automated_samples_run ON automated_samples(run_id,id);
            ''')
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)',(utcnow(),))
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(2,?)',(utcnow(),))
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(3,?)',(utcnow(),))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA journal_mode=WAL')
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def recover(self):
        # Called once at backend startup, under the OS process ownership lock.
        with self.connect() as db:
            for row in db.execute('SELECT * FROM automated_runs').fetchall():
                if row['state'] in ACTIVE:
                    item=json.loads(row['record_json']);item.update(state='DISCONNECTED',outcome='TEST_INCOMPLETE',
                        ended_at=utcnow(),reason='Backend interrupted; physical stop not confirmed',health_score=None,stop_confirmed=False)
                    db.execute('UPDATE automated_runs SET state=?,updated_at=?,record_json=? WHERE id=?',
                               (item['state'],utcnow(),json.dumps(item),row['id']))
            for row in db.execute('SELECT * FROM branch_power_sessions').fetchall():
                item=json.loads(row['record_json'])
                if not item.get('ended_at'):
                    item.update(state='FAILED',power_on=None,stop_confirmed=False,ended_at=utcnow(),
                                reason='Backend interrupted; physical stop unconfirmed')
                    db.execute('UPDATE branch_power_sessions SET record_json=? WHERE id=?',(json.dumps(item),row['id']))
            db.execute('DELETE FROM automated_ownership')
    def create(self,run):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try: db.execute('INSERT INTO automated_ownership VALUES(1,?)',(run['id'],))
            except sqlite3.IntegrityError as exc: raise RuntimeError('Another automated run owns the device') from exc
            db.execute('INSERT INTO automated_runs VALUES(?,?,?,?,?,?)',
                       (run['id'],run['state'],run['mode'],run['created_at'],utcnow(),json.dumps(run,allow_nan=False)))
    def save(self,run):
        with self.connect() as db:
            db.execute('UPDATE automated_runs SET state=?,updated_at=?,record_json=? WHERE id=?',
                       (run['state'],utcnow(),json.dumps(run_summary(run),allow_nan=False),run['id']))
    def release(self,run_id):
        with self.connect() as db: db.execute('DELETE FROM automated_ownership WHERE run_id=?',(run_id,))
    def sample(self,run_id,raw,quality):
        with self.connect() as db:
            cursor=db.execute('INSERT INTO automated_samples(run_id,received_at,raw_json,quality_json) VALUES(?,?,?,?)',
                       (run_id,utcnow(),json.dumps(raw,allow_nan=False),json.dumps(quality)))
            return cursor.lastrowid
    def update_quality(self,sample_id,quality):
        with self.connect() as db:db.execute('UPDATE automated_samples SET quality_json=? WHERE id=?',(json.dumps(quality),sample_id))
    def event(self,run_id,event):
        with self.connect() as db:
            db.execute('INSERT INTO automated_events(run_id,received_at,event_json) VALUES(?,?,?)',
                       (run_id,utcnow(),json.dumps(event,allow_nan=False)))
    def get(self,run_id):
        with self.connect() as db:
            row=db.execute('SELECT record_json FROM automated_runs WHERE id=?',(run_id,)).fetchone()
            if row is None: raise KeyError(run_id)
            item=json.loads(row[0])
            item['samples']=[{'id':r['id'],'received_at':r['received_at'],'raw':json.loads(r['raw_json']),
                             'quality':json.loads(r['quality_json'])} for r in db.execute('SELECT * FROM automated_samples WHERE run_id=? ORDER BY id',(run_id,))]
            item['events']=[json.loads(r[0]) for r in db.execute('SELECT event_json FROM automated_events WHERE run_id=? ORDER BY id',(run_id,))]
            return item
    def list(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT record_json FROM automated_runs ORDER BY created_at DESC LIMIT 200')]

    def create_simulated_circuit(self,report):
        from uuid import uuid4
        identifier=str(uuid4())
        result={**report,'run_id':identifier,'captured_count':0,'execution_state':'IN_PROGRESS','source':'SIMULATION'}
        with self.connect() as db:
            db.execute('INSERT INTO simulated_circuit_runs(id,report_json) VALUES(?,?)',(identifier,json.dumps(result)))
        return result
    def capture_simulated_circuit(self,identifier,index):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM simulated_circuit_runs WHERE id=?',(identifier,)).fetchone()
            if not row:raise KeyError(identifier)
            result=json.loads(row['report_json'])
            if type(index) is not int or index!=row['captured'] or index>=len(result['steps']):
                raise ValueError('Capture sequence changed or run already complete')
            result['captured_count']=index+1
            if result['captured_count']==len(result['steps']):result['execution_state']='COMPLETED'
            db.execute('UPDATE simulated_circuit_runs SET captured=?,report_json=? WHERE id=?',
                       (result['captured_count'],json.dumps(result),identifier))
            return result
