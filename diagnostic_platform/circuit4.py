"""Circuit 4 rules anchored to operator-reported multimeter measurements.

Thresholds are provisional engineering guard bands, not validated error/confidence
intervals. No ground-truth fault label is an input to the classifier.
"""
import math

ASSET_ID = 'CIRCUIT-4-LM324'
MODEL_VERSION = 'circuit4-lm324-v1'
REFERENCES = {
    'NORMAL': {'TP0': 5.0, 'TP1': 2.4744, 'TP2': 2.0167, 'TP3': 3.6877, 'TP4': 2.4742},
    'S1_OPEN': {'TP0': 5.0, 'TP1': .000166, 'TP2': 2.01461, 'TP3': .003477, 'TP4': 4.9670},
    'S2_SHUNT': {'TP0': 5.0, 'TP1': .40643, 'TP2': 2.01425, 'TP3': .003451, 'TP4': .40644},
}


def circuit4_asset():
    labels = {
        'TP0': ('5 V supply rail', 'Probe the regulated +5 V rail relative to circuit GND.', 4.75, 5.25),
        'TP1': ('Divider / LM324 pin 3 (+)', 'Probe the junction of S1, R2 and S2 at LM324 pin 3 relative to GND.', 2.2, 2.8),
        'TP2': ('Potentiometer / LM324 pin 2 (−)', 'Probe RV1 wiper / LM324 pin 2 relative to GND. Do not adjust RV1 during this capture.', 1.8, 2.2),
        'TP3': ('Comparator output / LM324 pin 1', 'Probe LM324 pin 1 relative to GND; this drives R4 and Q1.', 3.0, 4.3),
        'TP4': ('R1 / S1 upper node', 'Probe the node between R1 and S1 relative to GND. Keep both switches in the same state as previous readings.', 2.2, 2.8),
    }
    return {'asset_id': ASSET_ID, 'name': 'Circuit 4 · LM324 comparator', 'supply_voltage': 5.0,
            'diagnostic_model': MODEL_VERSION,
            'components': 'LM324; R1=10 kΩ; R2=10 kΩ; RV1=10 kΩ at ≈2.0 V; R3=1 kΩ; R4=4.7 kΩ; R5=1 kΩ; Q1=2N3904; LED1; S1/S2 fault switches.',
            'connections': '+5V→R1→TP4→S1→TP1→R2→GND; TP1→LM324 pin3(+); TP1→S2→R3→GND; RV1 wiper TP2→pin2(−); pin1 TP3→R4→Q1 base; +5V→R5→LED→Q1 collector; emitter→GND. LM324 pin4=+5V; pin11=GND.',
            'evidence_status': 'USER_REPORTED_MULTIMETER_VERIFIED; STM32_PATH_UNVERIFIED',
            'reference_values': REFERENCES,
            'test_points': [{'point_id': key, 'label': value[0], 'instruction': value[1],
                             'channel': 'test_point_voltage', 'minimum': value[2], 'maximum': value[3]}
                            for key, value in labels.items()]}


def classify_circuit4(readings):
    values = {r['point_id']: r['measured'] for r in readings if r.get('channel') == 'test_point_voltage'}
    result = {'model_version': MODEL_VERSION, 'classification': 'INSUFFICIENT_DATA',
              'verification': 'PROVISIONAL_RULES; STM32_CALIBRATION_UNVERIFIED',
              'suspected_region': None, 'health_score': None,
              'reason': 'Capture finite probe voltages at all five points TP0–TP4.',
              'normal_deviations': [],
              'limitations': ['One reported multimeter example per condition; no repeatability/error-rate validation.',
                              'TP0 is nominal/expected ≈5 V, not an exact fault-run measurement.',
                              'Sequential captures require unchanged supply, RV1 and switches; firmware acquisition timing is unverified.',
                              'No trained ML model, confidence percentage or motor/circuit health percentage.',
                              'R2 deviation and combined/other faults are not experimentally validated classes.']}
    required = set(REFERENCES['NORMAL'])
    if not required <= values.keys() or any(type(values[k]) not in (int, float) or not math.isfinite(values[k]) for k in required):
        return result
    result['normal_deviations'] = [{'point_id': k, 'measured': values[k], 'normal_reference': ref,
                                    'difference_V': values[k] - ref,
                                    'deviation_percent': (values[k] - ref) / ref * 100}
                                   for k, ref in REFERENCES['NORMAL'].items()]
    supply, divider, reference, output, upper = [values[k] for k in ('TP0', 'TP1', 'TP2', 'TP3', 'TP4')]
    if not 4.75 <= supply <= 5.25:
        result.update(classification='SUPPLY_OUT_OF_RANGE', suspected_region='5 V supply / circuit supply path',
                      reason='TP0 is outside the provisional 4.75–5.25 V supply gate; S1/S2 classification is withheld.')
    elif not 1.8 <= reference <= 2.2:
        result.update(classification='REFERENCE_OUT_OF_RANGE', suspected_region='RV1 / TP2 reference path',
                      reason='TP2 is outside the provisional 1.8–2.2 V reference gate; check RV1 before fault classification.')
    elif any(v < -.05 or v > supply + .15 for v in values.values()):
        result.update(classification='INCONCLUSIVE', reason='Probe voltages are inconsistent with the supplied single-supply circuit; check mapping and measurement quality.')
    elif abs(divider - upper) <= .15 and 2.2 <= divider <= 2.8 and 2.2 <= upper <= 2.8 and 3.0 <= output <= 4.3:
        result.update(classification='NORMAL_SIGNATURE', reason='TP1/TP4 agree near the measured normal divider level and TP3 is HIGH. Consistent with the normal signature; not proof all components are fault-free.')
    elif -.05 <= divider <= .1 and .9 * supply <= upper <= supply + .1 and upper - divider >= .8 * supply and -.05 <= output <= .1:
        result.update(classification='S1_OPEN_SIGNATURE', suspected_region='S1 or the connection between TP4 and TP1',
                      reason='TP1 is near GND, TP4 is near supply, and TP3 is LOW. This supports an open in the S1 path, not unique proof the switch itself failed.')
    elif .25 <= divider <= .65 and .25 <= upper <= .65 and abs(divider - upper) <= .15 and -.05 <= output <= .1:
        result.update(classification='S2_SHUNT_SIGNATURE', suspected_region='TP1-to-GND shunt path (S2/R3)',
                      reason='TP1/TP4 agree near the measured shunt level and TP3 is LOW. Consistent with S2/R3 shunting; other low-resistance paths may look similar.')
    else:
        result.update(classification='INCONCLUSIVE', reason='The full voltage pattern does not match the provisional normal, S1-open or S2-shunt signatures. Do not force a fault label.')
    return result
