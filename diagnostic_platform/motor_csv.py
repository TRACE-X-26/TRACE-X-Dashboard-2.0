"""Export the durable motor journal; no serial access or synthetic substitutions."""
import csv
import io

FIELDS=('run_id','test_id','source','record_type','timestamp','stm32_timestamp_ms',
        'requested_pwm_percent','applied_pwm_percent','voltage_V','current_A','power_W',
        'rpm','rpm_calibrated','motor_state','shutdown_reason','run_shutdown_reason',
        'stop_confirmed','quality','operating_mode','power_feedback_installed','power_feedback_state','motor_sensor_status','motor_connected','motor_valid','motor_timestamp_ms',
        'circuit_voltage_V','circuit_current_A','circuit_power_W','circuit_sensor_status',
        'circuit_connected','circuit_valid','circuit_timestamp_ms')

def render_motor_csv(run):
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=FIELDS);writer.writeheader()
    common=dict(run_id=run['id'],source=run['source'],stop_confirmed=run.get('stop_confirmed',False),
                run_shutdown_reason=run.get('reason') or run.get('outcome') or run['state'])
    for sample in run.get('samples',[]):
        raw=sample['raw'];channels=raw.get('measurements',{})
        row=dict(common,test_id=raw.get('test_id'),record_type='sample',timestamp=sample['received_at'],
            stm32_timestamp_ms=raw.get('electrical_completed_ms'),
            requested_pwm_percent=raw.get('requested_pwm_percent'),applied_pwm_percent=raw.get('applied_pwm_percent'),
            rpm_calibrated=raw.get('encoder_calibrated',False),motor_state=raw.get('motor_state'),
            shutdown_reason=raw.get('shutdown_reason'),quality=';'.join(sample.get('quality',[])),
            operating_mode=raw.get('operating_mode'),power_feedback_installed=raw.get('power_feedback_installed'),
            power_feedback_state=raw.get('power_feedback_state'))
        for name,column in [('voltage','voltage_V'),('current','current_A'),('power','power_W'),('rpm','rpm')]:
            item=channels.get(name,{})
            row[column]=item.get('value') if item.get('valid') is True else None
        from .ina219 import normalize_branches
        branches=normalize_branches(raw)
        for name,prefix in [('MOTOR','motor'),('CIRCUIT','circuit')]:
            branch=branches[name]
            row.update({prefix+'_sensor_status':branch['status'],prefix+'_connected':branch['connected'],
                        prefix+'_valid':branch['valid'],prefix+'_timestamp_ms':branch['timestamp_ms']})
        for name,column in [('voltage','circuit_voltage_V'),('current','circuit_current_A'),('power','circuit_power_W')]:
            item=branches['CIRCUIT']['measurements'][name]
            row[column]=item['value'] if item['valid'] else None
        writer.writerow(row)
    # Events preserve the confirmed STM32 start/stop times separately from samples.
    for event in run.get('events',[]):
        payload=event.get('payload',{})
        if payload.get('event') not in ('MOTOR_START','MOTOR_STOP'):continue
        writer.writerow(dict(common,test_id=event.get('test_id'),record_type=payload['event'],
            stm32_timestamp_ms=event.get('timestamp_ms'),shutdown_reason=payload.get('reason')))
    writer.writerow(dict(common,record_type='run_end',timestamp=run.get('ended_at'),
        motor_state=run.get('device_state','UNKNOWN'),applied_pwm_percent=run.get('applied_pwm_percent'),
        shutdown_reason=common['run_shutdown_reason']))
    return output.getvalue()
