"""Read-only verification of the two STM32-owned INA219 addresses over ADS v1."""
import argparse
import json
import time
from .ina219 import normalize_branches
from .stm32 import STM32SerialConnection

def verify(connection,samples=5,interval=.5):
    valid_counts={'MOTOR':0,'CIRCUIT':0};latest={}
    connection.connect()
    try:
        caps=connection.execute('GET_CAPABILITIES')
        for index in range(samples):
            latest=normalize_branches(connection.execute('READ_MEASUREMENTS'))
            for name,branch in latest.items():valid_counts[name]+=int(branch['valid'])
            if index+1<samples:time.sleep(interval)
        return dict(firmware_version=caps.get('firmware_version'),source='stm32_serial',
            read_only=True,motor_commands_sent=False,physical_operation_verified=False,
            passed=all(b['connected'] and b['valid'] and valid_counts[name]>0 for name,b in latest.items()),
            valid_sample_counts=valid_counts,ina219=latest)
    finally:connection.disconnect()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--samples',type=int,default=5,choices=range(1,101),metavar='1..100')
    args=parser.parse_args()
    connection=STM32SerialConnection(port=args.port,require_crc=True,allow_motor_control=False,command_timeout=2)
    try:
        result=verify(connection,args.samples)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0 if result['passed'] else 1
    except Exception as exc:
        print(json.dumps(dict(passed=False,error=str(exc),motor_commands_sent=False)))
        return 1
if __name__=='__main__':raise SystemExit(main())
