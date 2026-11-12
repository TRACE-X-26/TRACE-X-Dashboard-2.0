"""Experimental run-grouped classifier validation; production predictions stay disabled."""
import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from .baseline_package import CONTEXT

FEATURES = ('voltage', 'current', 'rpm', 'power')


def train(manifest):
    rows = manifest.get('runs', [])
    report = dict(enabled=False, model_version='nearest-centroid-experimental-v1',
                  validation='Leave one recording session out; scaling fitted inside each training fold',
                  independent_runs=len(rows), probability_calibration='Not applicable; no probabilities',
                  reason='Verified labels and at least three recording sessions per class required')
    if not rows:
        return report
    if not isinstance(rows[0].get('operating_context'),dict) or any(
            rows[0]['operating_context'].get(key) in (None,'','UNKNOWN') for key in CONTEXT):
        return report
    groups = {}
    identities = set()
    context = rows[0].get('operating_context')
    for row in rows:
        if (row.get('source') != 'stm32_serial' or row.get('label_verified') is not True or row.get('measurements_verified') is not True
                or not row.get('label_evidence_id') or not row.get('recording_session_id')
                or not row.get('run_id') or row['run_id'] in identities
                or row.get('operating_context') != context or not context):
            return report
        identities.add(row['run_id'])
        if not isinstance(row.get('label'), str) or not row['label']:
            return report
        if any(type(row.get('features', {}).get(key)) not in (int, float)
               or not math.isfinite(row['features'][key]) for key in FEATURES):
            return report
        groups.setdefault(row['label'], set()).add(row['recording_session_id'])
    if len(groups) < 2 or any(len(sessions) < 3 for sessions in groups.values()):
        return report

    def fit(training):
        scales = [statistics.pstdev(row['features'][key] for row in training) or 1.0 for key in FEATURES]
        centers = {label: [statistics.fmean(row['features'][key] for row in training if row['label'] == label)
                           for key in FEATURES] for label in groups}
        return centers, scales

    confusion = {label: Counter() for label in groups}
    for session in sorted({row['recording_session_id'] for row in rows}):
        training = [row for row in rows if row['recording_session_id'] != session]
        centers, scales = fit(training)
        for row in rows:
            if row['recording_session_id'] != session:
                continue
            predicted = min(centers, key=lambda label: sum(
                ((row['features'][key]-centers[label][i])/scales[i])**2 for i, key in enumerate(FEATURES)))
            confusion[row['label']][predicted] += 1
    metrics = {}
    for label in groups:
        tp = confusion[label][label]
        fn = sum(confusion[label].values())-tp
        fp = sum(confusion[other][label] for other in groups if other != label)
        tn = len(rows)-tp-fn-fp
        precision = tp/(tp+fp) if tp+fp else 0
        recall = tp/(tp+fn) if tp+fn else 0
        metrics[label] = dict(precision=precision, recall=recall,
                             f1=2*precision*recall/(precision+recall) if precision+recall else 0,
                             false_positive_rate=fp/(fp+tn) if fp+tn else None,
                             false_negative_rate=fn/(tp+fn) if tp+fn else None)
    centers, scales = fit(rows)
    return dict(report, reason='Experimental validation only; independent deployment review required',
                model=dict(centroids=centers, scales=scales, features=list(FEATURES)),
                confusion_matrix={key: dict(value) for key, value in confusion.items()},
                class_distribution=dict(Counter(row['label'] for row in rows)), metrics=metrics,
                feature_importance='No causal importance claimed for centroid distances')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(train(json.loads(args.manifest.read_text())), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
