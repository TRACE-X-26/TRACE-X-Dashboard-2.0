"""Operator-guided capture and provisional range analysis; never actuates hardware."""
from datetime import datetime, timezone
from .circuit4 import MODEL_VERSION, classify_circuit4


UNITS = {'test_point_voltage': 'V', 'circuit_supply_voltage': 'V', 'circuit_current': 'A', 'circuit_power': 'W'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def start_capture(asset):
    return {'asset': asset, 'source': 'HARDWARE_UNVERIFIED', 'state': 'IN_PROGRESS',
            'started_at': utc_now(), 'armed_at': None, 'readings': [],
            'condition': 'INSUFFICIENT_DATA', 'hardware_control': False}


def next_point(session):
    if session['state'] != 'IN_PROGRESS':
        raise ValueError('This circuit test is already complete')
    return session['asset']['test_points'][len(session['readings'])]


def arm_capture(session, point_id):
    point = next_point(session)
    if point['point_id'] != point_id:
        raise ValueError('Confirm the current test point')
    session['armed_at'] = utc_now()
    return session


def capture_reading(session, snapshot):
    point = next_point(session)
    if not session['armed_at']:
        raise ValueError('Confirm probe placement before capturing')
    if not snapshot['connected']:
        raise ValueError('STM32 receiver is disconnected')
    match = next((c for c in snapshot.get('circuit_channels', [])
                  if c['asset_id'] == session['asset']['asset_id'] and c['point_id'] == point['point_id']
                  and c['channel'] == point['channel']), None)
    if not match or match['quality'] == 'STALE' or match['age_seconds'] > 3:
        raise ValueError('Waiting for a fresh matching circuit channel and test-point ID')
    if datetime.fromisoformat(match['timestamp']) <= datetime.fromisoformat(session['armed_at']):
        raise ValueError('Waiting for a new reading after probe confirmation')
    measured = match['value']
    within = point['minimum'] <= measured <= point['maximum']
    session['readings'].append({**point, 'measured': measured, 'unit': UNITS[point['channel']],
                                'timestamp': match['timestamp'], 'captured_at': utc_now(),
                                'quality': match['quality'], 'calibration_version': match.get('calibration_version'),
                                'result': 'WITHIN_RANGE' if within else 'OUTSIDE_RANGE',
                                'explanation': 'Within configured limits; calibration is unverified.' if within else
                                'Outside configured limits at this test point; the failing component is not uniquely identified.'})
    session['armed_at'] = None
    if session['asset'].get('diagnostic_model') == MODEL_VERSION:
        session['diagnostic'] = classify_circuit4(session['readings'])
    if len(session['readings']) == len(session['asset']['test_points']):
        session['state'] = 'COMPLETE'
        session['completed_at'] = utc_now()
        session['condition'] = 'ABNORMAL_READING' if any(r['result'] == 'OUTSIDE_RANGE' for r in session['readings']) else 'WITHIN_CONFIGURED_RANGES'
        if 'diagnostic' in session:
            session['condition'] = session['diagnostic']['classification']
    return session
