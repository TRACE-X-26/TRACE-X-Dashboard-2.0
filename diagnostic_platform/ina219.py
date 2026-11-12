"""Independent INA219 normalization. No circuit-to-motor fallback or actuation."""
from .collector import validate_measurements

UNITS={'voltage':'V','current':'A','power':'W'}
STATUSES={'CONNECTED','NOT_CONNECTED','CONFIG_ERROR','READ_ERROR','CONVERSION_TIMEOUT',
          'OVERFLOW','NOT_INITIALIZED','STALE'}

def normalize_branches(result):
    import math
    out={}
    branches=result.get('ina219',{})
    if not isinstance(branches,dict):branches={}
    for label,address in [('MOTOR',0x40),('CIRCUIT',0x41)]:
        branch=branches.get(label)
        if branch is None and label=='MOTOR' and not branches:
            # Older ADS JSON motor fields remain usable; no circuit is invented.
            try:
                measurements=validate_measurements(result)
                branch=dict(address=address,status='CONNECTED',connected=True,configured=True,
                    valid=all(measurements[k]['valid'] for k in UNITS),
                    calibrated=result.get('voltage_current_calibrated',False),
                    timestamp_ms=result.get('electrical_completed_ms',0),started_ms=result.get('electrical_started_ms',0),
                    sequence=result.get('electrical_sequence',0),measurements={k:measurements[k] for k in UNITS})
            except ValueError:branch=None
        empty=dict(address=address,status='NOT_REPORTED' if branch is None else 'MALFORMED',
                   connected=False,configured=False,valid=False,calibrated=False,timestamp_ms=None,
                   started_ms=None,sequence=None,measurements={k:dict(value=None,unit=u,valid=False,timestamp_ms=0) for k,u in UNITS.items()})
        try:
            if not isinstance(branch,dict) or type(branch.get('address')) is not int or branch['address']!=address:
                raise ValueError
            if branch.get('status') not in STATUSES:raise ValueError
            for flag in ('connected','configured','valid','calibrated'):
                if type(branch.get(flag)) is not bool:raise ValueError
            for key in ('timestamp_ms','started_ms','sequence'):
                if type(branch.get(key)) is not int or not 0<=branch[key]<=0xffffffff:raise ValueError
            m=branch.get('measurements',{})
            if set(m)!=set(UNITS):raise ValueError
            for name,unit in UNITS.items():
                item=m[name]
                if item.get('unit')!=unit or type(item.get('valid')) is not bool:raise ValueError
                if type(item.get('timestamp_ms')) is not int or not 0<=item['timestamp_ms']<=0xffffffff:raise ValueError
                v=item.get('value')
                if item['valid'] and (type(v) not in (int,float) or not math.isfinite(v)):raise ValueError
                if not item['valid'] and v is not None:raise ValueError
            valid=all(item['valid'] for item in m.values())
            if branch['valid']!=valid:raise ValueError
            if valid and (not branch['connected'] or not branch['configured'] or branch['status']!='CONNECTED'):raise ValueError
            if valid and any(item['timestamp_ms']!=branch['timestamp_ms'] for item in m.values()):raise ValueError
            out[label]={**branch,'measurements':{k:dict(v) for k,v in m.items()}}
        except (ValueError,TypeError,KeyError,AttributeError):out[label]=empty
    return out
