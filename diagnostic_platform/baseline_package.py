"""Build reviewable matched-run references from exported automated run reports."""
import argparse
import json
import math
import statistics
from pathlib import Path

from .health_analysis import analyze

CONTEXT = ('device_id', 'calibration_id', 'fixture_id', 'pwm_percent', 'direction',
           'load_id', 'condition', 'supply_range', 'duration_ms', 'firmware_version',
           'sensor_configuration', 'procedure_version')
CHANNELS = ('voltage', 'current', 'rpm', 'power')


def build_package(manifest):
    runs = manifest.get('runs', [])
    if len(runs) < 5:
        raise ValueError('At least five independent known-good physical runs required')
    seen, context, features = set(), None, []
    for run in runs:
        run_id = run.get('id')
        if not isinstance(run_id, str) or not run_id or run_id in seen:
            raise ValueError('Unique run identities required')
        seen.add(run_id)
        if run.get('known_good') is not True or run.get('source') != 'stm32_serial':
            raise ValueError('Independent physical known-good confirmation required for each run')
        if run.get('state') != 'COMPLETED' or run.get('stop_confirmed') is not True:
            raise ValueError('Completed capture and confirmed stop required')
        steps = run.get('steps', [])
        if len(steps) != 1:
            raise ValueError('Use one procedure per baseline capture')
        step = steps[0]
        if step.get('test_id') != runs[0]['steps'][0].get('test_id'):
            raise ValueError('Baseline procedure identities differ')
        current = step.get('result', {}).get('operating_context', {})
        if any(current.get(key) is None or current.get(key) == '' for key in CONTEXT):
            raise ValueError('Full operating context required')
        if current.get('load_id') == 'UNKNOWN' or current.get('condition') == 'UNKNOWN':
            raise ValueError('Document load and physical condition before baseline approval')
        if context is not None and context != current:
            raise ValueError('Operating contexts differ')
        context = current
        # Exported samples are stored separately from step summaries.
        samples = [dict(values={key: item.get('value') if item.get('valid') is True else None
                               for key, item in record['raw']['measurements'].items()},
                        raw=record['raw'], quality=record['quality'])
                   for record in run.get('samples', []) if record['raw'].get('test_id') == step['test_id']]
        window=step.get('result',{}).get('analysis_window_ms',[0,30000])
        if window[0] and type(step.get('started_ms')) is int:
            samples=[sample for sample in samples if window[0]<=
                     ((sample['raw']['electrical_started_ms']-step['started_ms'])&0xffffffff)<=window[1]]
        if any(sample['raw'].get('voltage_current_calibrated') is not True or
               sample['raw'].get('encoder_calibrated') is not True for sample in samples):
            raise ValueError('Firmware electrical and encoder calibration confirmation required')
        report = analyze(samples, completed=True, source='stm32_serial')
        if report['unverified_channels'] or any(report['features'][key]['count'] < 5 for key in CHANNELS):
            raise ValueError('Five distinct calibrated acquisitions per required channel required')
        features.append(report['features'])
    ranges, stability, statistics_by_channel = {}, {}, {}
    for channel in CHANNELS:
        floor = manifest.get('tolerances', {}).get(channel)
        max_std = manifest.get('max_std', {}).get(channel)
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in (floor, max_std)):
            raise ValueError('Positive repeatability tolerance and stability limit required for ' + channel)
        if any(item[channel]['std'] > max_std for item in features):
            raise ValueError('Known-good run exceeds supplied stability criterion for '+channel)
        values = [item[channel]['mean'] for item in features]
        center = statistics.median(values)
        mad = statistics.median(abs(value-center) for value in values)
        width = max(floor, 4*1.4826*mad)
        bounds = [center-width, center+width]
        if not all(math.isfinite(value) for value in bounds):
            raise ValueError('Non-finite baseline bounds')
        ranges[channel] = bounds
        stability[channel] = max_std
        statistics_by_channel[channel] = dict(independent_runs=len(values), mean=statistics.fmean(values),
                                              median=center, mad=mad, std=statistics.pstdev(values))
    approval = manifest.get('approval', {})
    approved = all(isinstance(approval.get(key), str) and approval[key].strip()
                   for key in ('reviewer', 'evidence_id', 'approved_at'))
    return dict(version='matched-run-envelope-v2', validated=approved,
                status='APPROVED' if approved else 'CANDIDATE_REQUIRES_APPROVAL',
                operating_context=context, independent_runs=len(seen), evidence_run_ids=sorted(seen),
                ranges=ranges, max_std=stability, statistics=statistics_by_channel, approval=approval,
                uncertainty='Provisional robust diagnostic bands across independent runs; no probabilistic failure or life prediction.',
                health_score=None, test_id=runs[0]['steps'][0]['test_id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = build_package(json.loads(args.manifest.read_text()))
    args.output.write_text(json.dumps(package, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
