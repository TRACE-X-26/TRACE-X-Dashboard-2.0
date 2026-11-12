"""Auditable offline archive import. Historical references never authorize output."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from .history import parse_csv
from .import_history import import_archive
from .motor_health import TEST_CATALOG, replay_csv


def stats(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    center = statistics.median(values)
    return dict(count=len(values), mean=statistics.fmean(values), median=center,
                min=values[0], max=values[-1], std=statistics.pstdev(values),
                mad=statistics.median(abs(v-center) for v in values))


def audit_archives(archives, output, database=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runs, files, rejected, replay = {}, [], [], {}
    content_groups = {}
    for archive in archives:
        archive = Path(archive)
        if database is not None:
            import_archive(archive, Path(database))
        with ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                if not entry.filename.lower().endswith('.csv'):
                    continue
                provenance = dict(archive=archive.name, path=entry.filename, bytes=entry.file_size)
                if entry.file_size > 2_000_000:
                    rejected.append(dict(provenance, reason='CSV_SIZE_LIMIT'))
                    continue
                raw = zipped.read(entry)
                digest = hashlib.sha256(raw).hexdigest()
                provenance['sha256'] = digest
                files.append(provenance)
                if digest in runs:
                    runs[digest]['sources'].append(provenance)
                    continue
                # Preserve exact bytes without trusting ZIP paths.
                original = output / 'originals' / (digest + '.csv')
                original.parent.mkdir(exist_ok=True)
                original.write_bytes(raw)
                try:
                    text = raw.decode('utf-8-sig')
                    rows = list(csv.DictReader(io.StringIO(text), strict=True))
                    match = re.search(r'/test_(\d+)/', entry.filename)
                    test = int(match[1]) if match else int(float(rows[0]['test'])) if rows else None
                    mass = re.search(r'_(\d+(?:p\d+)?)(?:gg|g)\.csv$', entry.filename)
                    metadata = dict(filename=entry.filename, condition='UNKNOWN',
                                    device_id='TRACE-X-UNVERIFIED', attached_mass_g=None,
                                    filename_mass_label_g=float(mass[1].replace('p', '.')) if mass else None,
                                    mass_label_status='FILENAME_ONLY_UNVERIFIED',
                                    friction_condition=None, calibration_verified=False)
                    if rows and 'software_result' in rows[0] and not any(row.get('raw_message') for row in rows):
                        parsed = dict(samples=[], events=[], warnings=[dict(line=2, code='SOFTWARE_RESULT_ONLY')],
                                      metadata=metadata, source='HISTORICAL_CSV')
                    else:
                        parsed = parse_csv(text, metadata)
                except (ValueError, KeyError, UnicodeError, csv.Error) as exc:
                    rejected.append(dict(provenance, reason=str(exc)))
                    continue
                normalized = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
                content_groups.setdefault(normalized, []).append(digest)
                features = {}
                for field in ('voltage', 'current', 'rpm', 'temperature', 'recorded_power', 'input_power'):
                    features[field] = {
                        'all_recorded': stats([s[field] for s in parsed['samples']
                                               if s[field] is not None and not s['duplicate']]),
                        'logged_running': stats([s[field] for s in parsed['samples']
                                                 if s[field] is not None and not s['duplicate'] and s['phase'] == 'RUNNING'])}
                metadata['recorded_target_pwm_labels'] = sorted({
                    row.get('target_pwm_percent') or row.get('target_pwm') or row.get('pwm_command_percent') or row.get('pwm_percent')
                    for row in rows} - {None, ''})
                run = dict(run_id=digest, test_number=test, sources=[provenance],
                           content_sha256=normalized, metadata=metadata,
                           source_rows=len(rows), canonical=parsed, features=features,
                           baseline_status='HISTORICAL_REFERENCE',
                           baseline_eligible=False,
                           baseline_exclusion_reasons=[
                               'KNOWN_GOOD_CONDITION_UNCONFIRMED', 'OPERATING_CONTEXT_UNVERIFIED',
                               'CALIBRATION_UNVERIFIED', 'DEVICE_PHASE_TIMING_UNVERIFIED'])
                runs[digest] = run
                # Existing dashboard replay contract. Reported power remains reported;
                # instantaneous power is never synthesized from adjacent serial lines.
                replay[digest] = replay_csv(rows, test)
                replay[digest]['source_paths'] = [entry.filename]
                has_start=any(event['event']=='MOTOR_START' for event in parsed['events'])
                window = [s for s in parsed['samples'] if
                          s['phase'] in (('RUNNING',) if has_start else ('BEFORE_START',)) and not s['duplicate']]
                replay[digest]['metrics'] = {}
                for field, channel in [('voltage','motor_voltage_V'), ('current','motor_current_A'),
                                       ('rpm','motor_rpm'), ('recorded_power','motor_power_W')]:
                    values = [s[field] for s in window if s[field] is not None]
                    if values:
                        summary = stats(values)
                        replay[digest]['metrics'][channel] = dict(median=summary['median'], min=summary['min'],
                                                                  max=summary['max'], samples=summary['count'])

    tests = {}
    for test, (name, planned_pwm) in TEST_CATALOG.items():
        group = [r for r in runs.values() if r['test_number'] == test]
        tests[test] = dict(name=name, planned_pwm_percent=planned_pwm,
                           independent_capture_files=len(group),
                           files_with_measurements=sum(bool(r['canonical']['samples']) for r in group),
                           approved_baseline_runs=0)
    result = dict(schema_version=1, files=files, runs=list(runs.values()), tests=tests,
                  rejected_files=rejected,
                  exact_duplicate_files=len(files)-len({f['sha256'] for f in files}),
                  equivalent_csv_groups=[v for v in content_groups.values() if len(v)>1],
                  approved_baselines=[],
                  ml=dict(enabled=False, reason='No independently verified ground-truth labels'),
                  reference_policy='Per-run descriptions only. No pooling across unknown load, motor, direction or calibration.')
    (output / 'canonical.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    catalog = {key: dict(value, present_in_archive=bool(value['independent_capture_files']))
               for key, value in tests.items()}
    readable_replay = {runs[key]['sources'][0]['path']+' ['+key[:12]+']': value for key,value in replay.items()}
    (output / 'archive_replay.json').write_text(json.dumps(dict(test_catalog=catalog, runs=readable_replay), indent=2, allow_nan=False))
    with (output / 'run_features.csv').open('w', newline='') as stream:
        columns = ['run_id', 'test', 'channel', 'phase', 'count', 'mean', 'median', 'min', 'max', 'std', 'mad', 'baseline_status']
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for run in runs.values():
            for channel, phases in run['features'].items():
                for phase, values in phases.items():
                    writer.writerow(dict(run_id=run['run_id'], test=run['test_number'], channel=channel,
                                         phase=phase, baseline_status=run['baseline_status'], **values))
    references = [dict(run_id=run['run_id'],test_number=run['test_number'],
                       status='PROVISIONAL_UNVERIFIED',context=run['metadata'],
                       statistics=run['features'],independent_runs=1,
                       approval_required=run['baseline_exclusion_reasons'],
                       uncertainty='Single capture; repeated samples are correlated. No statistical prediction interval.')
                  for run in runs.values() if run['canonical']['samples']]
    (output / 'candidate_references.json').write_text(json.dumps(
        dict(candidates=references,approved=[],policy=result['reference_policy']), indent=2,allow_nan=False))
    (output / 'excluded_measurements.json').write_text(json.dumps(
        [dict(run_id=run['run_id'],line=warning['line'],reason=warning['code'])
         for run in runs.values() for warning in run['canonical']['warnings']],indent=2))
    summary=dict(csv_files=len(files), unique_runs=len(runs), duplicate_files=result['exact_duplicate_files'],
                 rejected_files=len(rejected), tests=tests)
    (output / 'summary.json').write_text(json.dumps(summary,indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--database', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_archives(args.archives, args.output, args.database), indent=2))


if __name__ == '__main__':
    main()
