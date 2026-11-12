"""ADS v1 acquisition and append-only experiment recording; no motor commands."""
from __future__ import annotations
import argparse
import csv
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

CHANNELS = {'voltage': 'V', 'current': 'A', 'power': 'W', 'temperature': 'degC', 'rpm': 'rpm'}


def validate_measurements(result):
    measurements = result.get('measurements')
    if not isinstance(measurements, dict) or set(measurements) != set(CHANNELS):
        raise ValueError('Expected all five ADS measurement channels')
    for name, unit in CHANNELS.items():
        item = measurements[name]
        if not isinstance(item, dict) or item.get('unit') != unit or type(item.get('valid')) is not bool:
            raise ValueError('Invalid measurement metadata')
        tick = item.get('timestamp_ms')
        if type(tick) is not int or not 0 <= tick <= 0xffffffff:
            raise ValueError('Invalid acquisition timestamp')
        value = item.get('value')
        if item['valid']:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Valid measurement requires a finite number')
        elif value is not None:
            raise ValueError('Invalid measurement must use null')
    return measurements


class ExperimentRecorder:
    def __init__(self, directory, test_id):
        self.test_id = str(test_id)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex}.csv'
        self.file = self.path.open('x', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=['received_at', 'test_id', 'channel', 'value', 'unit', 'valid', 'timestamp_ms', 'branch', 'address', 'sensor_status', 'connected', 'calibrated'])
        self.writer.writeheader()
        self.file.flush()

    def record(self, result):
        measurements = validate_measurements(result)
        timestamp = datetime.now(timezone.utc).isoformat()
        from .ina219 import normalize_branches
        branches=normalize_branches(result)
        for channel,item in measurements.items():
            motor=branches['MOTOR'] if channel in ('voltage','current','power') else {}
            self.writer.writerow(dict(received_at=timestamp,test_id=self.test_id,channel=channel,**item,
                branch='MOTOR',address=motor.get('address'),sensor_status=motor.get('status'),
                connected=motor.get('connected'),calibrated=motor.get('calibrated')))
        if 'ina219' in result:
            circuit=branches['CIRCUIT']
            for channel,item in circuit['measurements'].items():
                self.writer.writerow(dict(received_at=timestamp,test_id=self.test_id,channel=channel,**item,
                    branch='CIRCUIT',address=circuit['address'],sensor_status=circuit['status'],
                    connected=circuit['connected'],calibrated=circuit['calibrated']))
        self.file.flush()

    def close(self):
        self.file.close()


def main():
    from .stm32 import STM32SerialConnection
    import time
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--crc32',action='store_true',help='Use protected framing for firmware 0.4.0')
    parser.add_argument('--test-id', required=True)
    parser.add_argument('--directory', default='data/experiments')
    args = parser.parse_args()
    recorder = ExperimentRecorder(args.directory, args.test_id)
    connection = STM32SerialConnection(port=args.port,require_crc=args.crc32)
    try:
        connection.connect()
        while True:
            connection.heartbeat()
            recorder.record(connection.read_measurements())
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        connection.disconnect()
        recorder.close()


if __name__ == '__main__':
    main()
