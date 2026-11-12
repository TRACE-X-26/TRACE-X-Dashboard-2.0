"""Offline ZIP inventory/import. Archived Python files are never executed."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from .history import parse_csv
from .storage import DiagnosticStore


def import_archive(archive: Path, database: Path) -> dict:
    inventory = []
    with ZipFile(archive) as zipped, DiagnosticStore(database) as store:
        for entry in zipped.infolist():
            if not entry.filename.endswith('.csv'):
                continue
            item = {'path': entry.filename, 'size': entry.file_size}
            if entry.file_size > 2_000_000:
                inventory.append({**item, 'status': 'SKIPPED_SIZE_LIMIT'})
                continue
            raw = zipped.read(entry)
            item['original_sha256'] = hashlib.sha256(raw).hexdigest()
            text = raw.decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            pwm_labels = sorted({r.get('target_pwm_percent') or r.get('target_pwm') or r.get('pwm_command_percent') for r in rows} - {None, ''})
            mass = re.search(r'_([0-9]+(?:p[0-9]+)?)(gg|g)\.csv$', entry.filename)
            metadata = {'filename': entry.filename, 'device_id': 'TRACE-X-UNVERIFIED',
                        'condition': 'UNKNOWN', 'attached_mass_g': None,
                        'fixture_description': '', 'target_pwm_percent': None,
                        'filename_mass_label_g': float(mass[1].replace('p', '.')) if mass else None,
                        'mass_label_status': 'FILENAME_ONLY_UNVERIFIED' if mass else 'UNAVAILABLE',
                        'recorded_target_pwm_labels': pwm_labels,
                        'archive': archive.name, 'original_sha256': item['original_sha256']}
            try:
                result = parse_csv(text, metadata)
                recording_id = store.save_recording(text, result, datetime.now(timezone.utc).isoformat())
                item.update(status='IMPORTED', recording_id=recording_id, rows=len(rows),
                            samples=len(result['samples']), events=len(result['events']),
                            filename_mass_label_g=metadata['filename_mass_label_g'],
                            target_pwm_labels=pwm_labels,
                            warnings=dict(Counter(w['code'] for w in result['warnings'])),
                            recorded_features=result['recorded_features'])
            except (ValueError, csv.Error) as exc:
                item.update(status='NOT_A_MEASUREMENT_RECORDING', reason=str(exc), rows=len(rows))
            inventory.append(item)
    return {'archive': str(archive), 'csv_files': len(inventory),
            'unique_csv_contents': len({i.get('original_sha256') for i in inventory}),
            'imported_unique_recordings': len({i['recording_id'] for i in inventory if 'recording_id' in i}),
            'files': inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = import_archive(args.archive, args.database)
    args.report.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}))


if __name__ == '__main__':
    main()
