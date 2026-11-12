"""Explicit software STM32 simulator; never opens serial/GPIO or claims hardware."""
import time
from collections import deque
from .protocol import ProtocolMessage, MessageType, encode_message, decode_message, unprotect_frame

class STM32Simulator:
    device_id='SIM-STM32-ADS'
    def __init__(self,pwm=10,scenario='healthy'):
        self.pwm=pwm or 10; self.scenario=scenario; self.responses=deque(); self.closed=False
        self.epoch=time.monotonic(); self.last_heartbeat=0; self.seen_heartbeat=False
        self.state='DISARMED'; self.applied=0; self.requested=0; self.run_id=0
        self.started=0; self.stopped=0; self.duration=0; self.sequence=0; self.event_sequence=0
        self.last_control=0; self.sample_sequence=0; self.lost=False; self.corrupt=False
        self.frames=[]
    def tick(self): return int((time.monotonic()-self.epoch)*1000)
    def emit(self,kind,payload,stamp=None):
        self.sequence+=1
        msg=ProtocolMessage(MessageType(kind),self.sequence,self.device_id,payload,self.tick() if stamp is None else stamp)
        frame=encode_message(msg,checksum=True)
        if self.corrupt: frame=frame[:-4]+b'BAD\n'
        self.responses.append(frame)
    def event(self,event,reason):
        self.event_sequence+=1
        self.emit('event',dict(event=event,event_sequence=self.event_sequence,run_id=self.run_id,reason=reason,
                              applied_pwm_percent=self.applied,physical_stop_verified=False),
                  self.started if event=='MOTOR_START' else self.stopped)
    def stop(self,reason,locked=False):
        running=self.state=='RUNNING'; self.applied=0
        self.state='LOCKOUT' if locked or self.state=='LOCKOUT' else 'STOPPED'
        if running:
            self.stopped=self.tick(); self.event('MOTOR_STOP',reason)
    def poll(self):
        if self.state in {'ARMED','RUNNING'} and self.tick()-self.last_heartbeat>=2000:
            self.stop('HEARTBEAT_LOSS',True)
        elif self.state=='RUNNING' and self.tick()-self.started>=self.duration:
            self.stop('COMPLETED')
    def status(self):
        return dict(state=self.state,applied_pwm_percent=self.applied,requested_pwm_percent=self.requested,
                    run_id=self.run_id,started_ms=self.started,stopped_ms=self.stopped,
                    last_control_seq=self.last_control,hardware_control=True,source='SIMULATION',
                    faults=['LOCKOUT'] if self.state=='LOCKOUT' else [],direction='FORWARD')
    def write(self,frame):
        if self.closed or self.lost: raise ConnectionError('Simulated device disconnected')
        unprotect_frame(frame,required=True); request=decode_message(frame); self.frames.append(request)
        self.poll(); seq=request.sequence; args=request.payload.get('arguments',{})
        command=request.payload.get('command','HEARTBEAT'); result={}; accepted=True; reason='NONE'; kind='ack'
        if command=='HEARTBEAT':
            self.last_heartbeat=self.tick();self.seen_heartbeat=True;result={'alive':True,**self.status()}
        elif command in {'GET_CAPABILITIES','GET_DEVICE_INFO'}:
            kind='capabilities'; result=dict(device_id=self.device_id,firmware_version='sim-0.3.0-bounded',
                hardware_control=True,integrity='CRC32',fixed_pwm_percent=self.pwm,max_duration_ms=30000,
                fixed_direction='FORWARD',heartbeat_timeout_ms=2000,
                measurement_types=['voltage','current','power','temperature','rpm'],
                commands=['ARM_TEST','START_TEST','STOP_TEST','SET_PWM','CLEAR_FAULTS','EMERGENCY_STOP',
                          'GET_STATUS','GET_CAPABILITIES','READ_MEASUREMENTS'],source='SIMULATION')
        elif command in {'GET_STATUS','GET_FAULTS'}: result=self.status();kind='status'
        elif command in {'STOP_TEST','STOP_MOTOR'}:
            self.stop('CANCELLED');result={'accepted':True,**self.status()}
        elif command=='EMERGENCY_STOP':
            self.stop('EMERGENCY_STOP',True);result={'accepted':True,**self.status()}
        elif command in {'ARM_TEST','CLEAR_FAULTS','START_TEST','SET_PWM','SET_DIRECTION'}:
            if seq<=self.last_control:accepted=False;reason='DUPLICATE_OR_OLD_REQUEST'
            else:
                self.last_control=seq
                if command in {'ARM_TEST','CLEAR_FAULTS'}:
                    if not self.seen_heartbeat or self.tick()-self.last_heartbeat>=2000 or self.state=='RUNNING':
                        accepted=False;reason='FRESH_HEARTBEAT_REQUIRED'
                    else:self.state='ARMED'
                elif command=='SET_DIRECTION':accepted=False;reason='FIXED_DIRECTION_ONLY'
                elif self.state!='ARMED':accepted=False;reason='ARM_REQUIRED_OR_RUNNING'
                elif args.get('pwm_percent')!=self.pwm:accepted=False;reason='PWM_OUT_OF_RANGE'
                elif command=='SET_PWM':self.requested=args['pwm_percent']
                elif type(args.get('duration_ms')) is not int or not 0<args['duration_ms']<=30000 or args.get('direction')!='FORWARD':
                    accepted=False;reason='INVALID_TEST_PARAMETERS'
                else:
                    self.started=self.tick();self.stopped=0;self.duration=args['duration_ms'];self.run_id=seq
                    self.applied=self.requested=args['pwm_percent'];self.state='RUNNING'
                    # Response is emitted below before event, matching C firmware.
            result={'accepted':accepted,'reason':reason,**self.status()}
        elif command in {'READ_MEASUREMENTS','GET_SENSOR_DATA'}:
            kind='measurement';self.sample_sequence+=1;stamp=self.tick();running=self.applied>0
            values=dict(voltage=12.,current=.1 if not running else .6,rpm=self.pwm*25. if running else 0.,temperature=25.)
            if self.scenario=='overloaded': values['current']=20.
            if self.scenario=='undervoltage':values['voltage']=5.
            if self.scenario=='overheating':values['temperature']=150.
            if self.scenario=='stalled':values['rpm']=0.;values['current']=20.
            values['power']=values['voltage']*values['current']
            units=dict(voltage='V',current='A',power='W',temperature='degC',rpm='rpm')
            result=dict(measurements={k:dict(value=None if self.scenario=='sensor_failure' and k=='current' else v,
                valid=not(self.scenario=='sensor_failure' and k=='current'),unit=units[k],timestamp_ms=stamp) for k,v in values.items()},
                sample_sequence=self.sample_sequence,electrical_sequence=self.sample_sequence,
                electrical_started_ms=stamp,electrical_completed_ms=stamp,encoder_started_ms=stamp,encoder_completed_ms=stamp,
                temperature_started_ms=stamp,temperature_completed_ms=stamp,voltage_current_calibrated=True,
                encoder_calibrated=True,temperature_calibrated=True,source='SIMULATION',encoder_direction='FORWARD' if running else 'STATIONARY')
            if self.scenario=='communication_loss' and self.sample_sequence>3:self.lost=True;raise ConnectionError('Injected USB loss')
        else:accepted=False;result={'accepted':False,'reason':'UNSUPPORTED_COMMAND'}
        self.emit(kind,{'reply_to':seq,'result':result})
        if command=='START_TEST' and accepted:self.event('MOTOR_START','OUTPUT_APPLIED')
        return len(frame)
    def readline(self):
        self.poll()
        return self.responses.popleft() if self.responses else b''
    def close(self):self.stop('DISCONNECTED',True);self.closed=True
