"""Create a portable source bundle with a consistent SQLite backup."""
import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {'.git', '.venv', '.venv-pi', 'node_modules', '__pycache__', '.metadata',
            'Debug', 'Release', 'build', 'TraceX.app', '.pytest_cache', 'deliverables', '.agents', '.codex', '.aws'}


def build_bundle(output: Path, recordings: Path | None = None, *, source_only=False):
    if source_only and recordings:
        raise ValueError('A source-only update must not include recordings')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        paths = []
        for parent, directories, files in os.walk(ROOT):
            directories[:] = sorted(d for d in directories if d not in EXCLUDED and not (d.startswith('STM32CubeIDE-') and d.endswith('Workspace')) and not (Path(parent) / d).is_symlink())
            paths.extend(Path(parent) / filename for filename in sorted(files))
        for path in paths:
            relative = path.relative_to(ROOT)
            if source_only and (set(relative.parts) & {'data', 'recordings', 'experiments', 'baselines',
                                                        'STM32CubeIDE-TraceX-Workspace', '.settings'} or
                                path.suffix in {'.csv', '.tsv', '.xlsx', '.sqlite', '.sqlite3'} or
                                '.sqlite-' in path.name or '.sqlite3-' in path.name):
                continue
            if not path.is_file() or path.is_symlink() or set(relative.parts) & EXCLUDED:
                continue
            if path.name.endswith('.local.h'):
                continue
            if path.resolve() == output.resolve() or path.name.startswith('.env') or path.name == '.DS_Store':
                continue
            if path.name.endswith('.automation.lock') or path.suffix in {'.db', '.pyc', '.tsbuildinfo', '.zip'} or path.name.endswith(('.db-wal', '.db-shm')):
                continue
            archive.write(path, 'Trace-X/' + relative.as_posix())
        archive.write(ROOT / '.env.example', 'Trace-X/.env.example')
        database = ROOT / 'diagnostics.db'
        if database.exists() and not source_only:
            backup = Path(temporary) / 'diagnostics.db'
            source = sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True)
            target = sqlite3.connect(backup)
            try:
                source.backup(target)
            finally:
                source.close(); target.close()
            archive.write(backup, 'Trace-X/diagnostics.db')
        if recordings:
            archive.write(recordings, 'Trace-X/recordings/' + recordings.name)
    with ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'Bundle verification failed: {bad}')
        return {'path': str(output), 'files': len(archive.namelist()), 'bytes': output.stat().st_size}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'deliverables/Trace-X-Pi.zip')
    parser.add_argument('--recordings', type=Path)
    parser.add_argument('--source-only', action='store_true', help='Upgrade code/UI without shipping or overwriting databases, baselines or recordings')
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.output, args.recordings, source_only=args.source_only)))
