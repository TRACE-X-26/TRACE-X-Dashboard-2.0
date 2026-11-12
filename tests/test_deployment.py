import tempfile
import unittest
import sqlite3
from unittest.mock import patch
from zipfile import ZipFile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dashboard import mount_dashboard
from deploy.pi.configure import configure
import deploy.pi.build_bundle as bundle


class DeploymentTests(unittest.TestCase):
    def test_source_only_upgrade_excludes_existing_evidence_and_runtime_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('ADS_MODE=simulation\nADS_HARDWARE_CONTROL_ENABLED=false\n')
            (root / '.env').write_text('PRIVATE=preserve')
            (root / 'diagnostics.db').write_bytes(b'original database')
            (root / 'archive.sqlite3').write_bytes(b'original SQLite archive')
            (root / 'data').mkdir()
            (root / 'data/baseline.json').write_text('{"validated":true}')
            (root / 'run.csv').write_text('original recording')
            (root / 'STM32CubeIDE-ActiveLow-Workspace').mkdir()
            (root / 'STM32CubeIDE-ActiveLow-Workspace/old-main.c').write_text('old source')
            (root / 'commissioned.local.h').write_text('private approval')
            (root / 'app.py').write_text('# new runtime')
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(bundle, 'ROOT', root):
                output = root / 'deliverables/update.zip'
                bundle.build_bundle(output, source_only=True)
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {'Trace-X/app.py', 'Trace-X/.env.example'})
            self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))

    def test_bundle_excludes_machine_dependencies_and_backs_up_wal_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('ADS_MODE=simulation\n')
            (root / '.env').write_text('SECRET=not-for-transfer')
            (root / '.venv').mkdir()
            (root / '.venv/token').write_text('exclude')
            (root / 'app.py').write_text('# portable source')
            db = sqlite3.connect(root / 'diagnostics.db')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE evidence(value)')
            db.execute('INSERT INTO evidence VALUES (73)')
            db.commit()
            try:
                output = root / 'deliverables/test.zip'
                with patch.object(bundle, 'ROOT', root):
                    bundle.build_bundle(output)
                with ZipFile(output) as archive:
                    self.assertNotIn('Trace-X/.env', archive.namelist())
                    self.assertNotIn('Trace-X/.venv/token', archive.namelist())
                    self.assertIn('Trace-X/app.py', archive.namelist())
                    copy = root / 'backup.db'
                    copy.write_bytes(archive.read('Trace-X/diagnostics.db'))
                restored = sqlite3.connect(copy)
                try:
                    self.assertEqual(restored.execute('SELECT value FROM evidence').fetchone()[0], 73)
                finally:
                    restored.close()
            finally:
                db.close()
    def test_local_dashboard_preserves_api_and_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<h1>Trace-X</h1>')
            (root / 'app.js').write_text('console.log("offline")')
            app = FastAPI()
            @app.get('/api/health')
            def health():
                return {'status': 'ok'}
            mount_dashboard(app, root)
            with TestClient(app) as client:
                self.assertIn('Trace-X', client.get('/').text)
                self.assertEqual(client.get('/api/health').json(), {'status': 'ok'})
                self.assertEqual(client.get('/app.js').status_code, 200)
                self.assertEqual(client.get('/api/missing').status_code, 404)

    def test_missing_build_fails_with_setup_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'npm'):
                mount_dashboard(FastAPI(), Path(directory))

    def test_configuration_preserves_serial_opt_in_and_existing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, config = root / 'Trace X', root / 'config'
            configure(project, config)
            service = (config / 'systemd/user/trace-x.service').read_text()
            self.assertIn('--host 127.0.0.1', service)
            self.assertIn('--workers 1', service)
            env = config / 'trace-x/runtime.env'
            self.assertIn('ADS_LIVE_SERIAL_PORT=\n', env.read_text())
            env.write_text('ADS_LIVE_SERIAL_PORT=/dev/custom\n')
            configure(project, config)
            self.assertEqual(env.read_text(), 'ADS_LIVE_SERIAL_PORT=/dev/custom\n')

    def test_working_directory_is_unquoted_absolute_and_percent_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)/'Trace X % station'
            config=Path(directory)/'config'
            configure(project,config)
            service=(config/'systemd/user/trace-x.service').read_text()
            line=next(line for line in service.splitlines() if line.startswith('WorkingDirectory='))
            self.assertEqual(line,'WorkingDirectory='+str(project.resolve()).replace('%','%%'))
            self.assertNotIn('WorkingDirectory="',service)
            self.assertIn('StandardOutput=journal',service)
            self.assertTrue((config/'trace-x/runtime.env').exists())
            with self.assertRaises(ValueError):configure(Path(directory)/'bad\npath',config)
