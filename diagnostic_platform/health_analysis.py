"""Conservative, deterministic summaries; no learned model or invented hardware thresholds."""
import math
import statistics

ALGORITHM='trace-x-matched-baseline-v2'

class PredictiveModel:
    """Optional interface; no model is instantiated or claimed trained."""
    def predict(self,features,context): raise NotImplementedError

def analyze(samples, *, completed, source, baselines=None, limits=None, test_id=None, context=None, required_channels=None):
    report=dict(algorithm_version=ALGORITHM,condition='INSUFFICIENT_DATA',health_score=None,
                source=source,findings=[],features={},model_trained=False,operating_context=context)
    if not completed:report['condition']='TEST_INCOMPLETE';return report
    required=set(required_channels or ('voltage','current','rpm','power'))
    required.discard('temperature')
    if not required or not required <= {'voltage','current','rpm','power'}:
        report['findings']=['Invalid required feature configuration'];return report
    # Report available electrical observations even while encoder calibration is pending.
    # RPM remains excluded from a definitive assessment until calibrated.
    valid=[s for s in samples if not (set(s.get('quality',[]))-{'RPM_UNCALIBRATED'})]
    report['required_channels']=sorted(required)
    report['unverified_channels']=['rpm'] if any('RPM_UNCALIBRATED' in s.get('quality',[]) for s in samples) else []
    conflicting=set()
    missing_ticks=set()
    for channel in ('voltage','current','rpm','power'):
        unique={}
        for sample in valid:
            value=sample['values'].get(channel)
            timestamp=sample.get('raw',{}).get('measurements',{}).get(channel,{}).get('timestamp_ms')
            if type(value) in (int,float) and math.isfinite(value):
                if source!='SIMULATION' and type(timestamp) is not int:
                    missing_ticks.add(channel)
                    continue
                key=timestamp if timestamp is not None else id(sample)
                if key in unique and unique[key]!=value:
                    conflicting.add(channel)
                unique.setdefault(key,value)
        values=list(unique.values())
        report['features'][channel]=dict(median=statistics.median(values) if values else None,
            mad=statistics.median(abs(value-statistics.median(values)) for value in values) if values else None,
            count=len(values),mean=statistics.fmean(values) if values else None,
            std=statistics.pstdev(values) if values else None,min=min(values) if values else None,max=max(values) if values else None)
    if conflicting or missing_ticks:
        report['findings']=['Conflicting or missing device acquisition timestamps for '+', '.join(sorted(conflicting|missing_ticks))]
        return report
    if len(valid)<5:
        report['findings']=['Too few valid, calibrated, in-window acquisition samples'];return report
    if any(report['features'][name]['count']<5 for name in required):
        report['findings']=['At least five distinct valid acquisitions per channel required'];return report
    baseline=(baselines or {}).get(test_id,{})
    minimum_runs=3 if source=='SIMULATION' else 5
    if baseline.get('validated') is not True or type(baseline.get('independent_runs')) is not int or baseline.get('independent_runs',0)<minimum_runs:
        report['findings']=[f'No approved baseline from at least {minimum_runs} independent matched runs'];return report
    if context is not None and baseline.get('operating_context')!=context:
        report['findings']=['Baseline operating conditions/calibration do not match this run'];return report
    if source!='SIMULATION':
        evidence=baseline.get('evidence_run_ids',[])
        if not isinstance(evidence,list) or len(set(evidence))<5:
            report['findings']=['Independent healthy-run evidence identifiers required'];return report
        approval=baseline.get('approval',{})
        if not isinstance(approval,dict) or not all(isinstance(approval.get(key),str) and approval[key].strip()
                for key in ('reviewer','evidence_id','approved_at')):
            report['findings']=['Documented reviewer approval required for physical baseline assessment'];return report
    # The profile supplies approved per-channel acceptance envelopes; no estimated thresholds are promoted automatically.
    envelopes=baseline.get('ranges',{})
    if not required<=set(envelopes):
        report['findings']=['Incomplete baseline acceptance envelope'];return report
    stability=baseline.get('max_std',{})
    if not required<=set(stability):
        report['findings']=['Validated per-channel stability limits required'];return report
    if source!='SIMULATION':
        from .baseline_package import CONTEXT
        if not context or any(context.get(key) is None or context.get(key)=='' for key in CONTEXT):
            report['findings']=['Full motor, load, firmware, supply and procedure context required'];return report
        if context.get('load_id')=='UNKNOWN' or context.get('condition')=='UNKNOWN':
            report['findings']=['Document physical load and condition before health assessment'];return report
    penalties=0
    if required & set(report['unverified_channels']):
        report['findings']=['Required RPM calibration is unverified'];return report
    for channel in sorted(required):
        bounds=envelopes[channel]
        if not isinstance(bounds,(list,tuple)) or len(bounds)!=2:
            report['findings']=['Invalid baseline envelope'];return report
        low,high=bounds
        if not all(type(v) in (int,float) and math.isfinite(v) for v in bounds) or low>high:
            report['findings']=['Invalid baseline envelope'];return report
        feature=report['features'][channel]
        if feature['mean'] is None: return report
        max_std=stability.get(channel)
        if type(max_std) not in (int,float) or not math.isfinite(max_std) or max_std<0:
            report['findings']=['Invalid stability envelope'];return report
        if not low<=feature['mean']<=high or feature['std']>max_std:
            penalties+=1
            report['findings'].append(f'{channel} mean {feature["mean"]:.4g} against approved {low:.4g}–{high:.4g}; standard deviation {feature["std"]:.4g} against limit {max_std:.4g}. Investigate matched load, supply and sensor evidence.')
        midpoint=(low+high)/2
        delta=feature['mean']-midpoint
        observations={name: data['mean'] for name,data in report['features'].items()}
        causes={
            'current': 'Increased demand may reflect load, mechanical resistance, supply changes or sensor error.',
            'rpm': 'Reduced speed may reflect load, supply loss, obstruction or encoder scaling.',
            'voltage': 'A deviation may reflect supply regulation, wiring drop or voltage acquisition.',
            'power': 'Input power changes reflect electrical demand; confirm voltage and current together.'}
        followup={
            'current': 'Compare matched load and RPM, then repeat with a confirmed unloaded fixture.',
            'rpm': 'Verify encoder scaling and applied PWM, then compare supply and current.',
            'voltage': 'Check supply voltage at the branch with a reference instrument.',
            'power': 'Review synchronized voltage/current and confirm operating load.'}
        report.setdefault('comparisons',[]).append(dict(direction='above' if delta>0 else 'below' if delta<0 else 'equal',
            baseline_midpoint=midpoint, deviation=delta, supporting_measurements=observations,
            possible_causes=causes[channel], followup=followup[channel],
            contradictory_evidence='Multiple causes remain possible; this result does not isolate a component.',
            evidence_quality='Approved matched envelope; physical label and calibration attestations required.',
            channel=channel,observed=feature['mean'],
            reference_range=[low,high],difference_from_midpoint=feature['mean']-(low+high)/2,
            observed_std=feature['std'],approved_max_std=max_std,
            interpretation='Investigate operating load, supply and sensor validity before assigning a mechanical cause.'))
    report['health_score']=max(0,100-20*penalties) if source=='SIMULATION' else None
    report['condition']='HEALTHY' if not penalties else 'WARNING'
    report['score_basis']='Legacy simulation index.' if source=='SIMULATION' else 'No validated physical numerical scoring model; approved envelope classification only.'
    return report
