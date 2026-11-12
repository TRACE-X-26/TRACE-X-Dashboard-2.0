"""Explicit hardware permission and read-only ADS contract validation.

Configuration permission is never proof of the firmware flashed on a board.
This module never arms, sets PWM, starts a run, or sends heartbeats by itself.
"""
import time

from .collector import validate_measurements
from .stm32 import STM32SerialConnection


class RunRejected(ValueError):
    pass


class HardwareRuntime:
    def __init__(self, *, enabled=False, baud=115200, read_timeout=.25,
                 command_timeout=.35):
        self.enabled = enabled is True
        self.baud = baud
        self.read_timeout = read_timeout
        self.command_timeout = command_timeout
        self.last_preflight = None
        self.checked_at = 0.

    def require_permission(self):
        if not self.enabled:
            raise RunRejected('Hardware runtime disabled: explicitly set ADS_HARDWARE_CONTROL_ENABLED=true after commissioning')

    def connection(self, profile, *, control=False):
        if control:
            self.require_permission()
        from serial.tools import list_ports
        matches = [p for p in list_ports.comports()
                   if p.serial_number == profile['serial_identity']]
        if len(matches) != 1:
            raise ConnectionError('Validated STM32 USB identity absent or ambiguous')
        return STM32SerialConnection(port=matches[0].device, baud=self.baud,
                                     read_timeout=self.read_timeout,
                                     command_timeout=self.command_timeout,
                                     device_id=profile['device_id'], require_crc=True,
                                     allow_motor_control=control)

    @staticmethod
    def validate_contract(profile, caps, status, duration):
        if caps.get('device_id') != profile['device_id'] or caps.get('firmware_version') != profile['firmware_version']:
            raise RunRejected('Firmware/device identity mismatch')
        if caps.get('integrity') != 'CRC32':
            raise RunRejected('CRC32-capable firmware required')
        if caps.get('hardware_control') is not True:
            raise RunRejected('Firmware output blocked: ' + str(caps.get('hardware_block_reason', 'CONTROL_DISABLED')))
        if caps.get('operating_mode') != profile.get('operating_mode', 'NORMAL'):
            raise RunRejected('Firmware/Pi operating mode mismatch')
        if profile.get('electrical_limits_enabled') is not True or caps.get('electrical_limits_enabled') is not True:
            raise RunRejected('Firmware/Pi electrical-limit policy mismatch')
        if caps.get('protection_limits_verified') is not True:
            raise RunRejected('Firmware protection limits unverified')
        if caps.get('supply_sensing_verified') is not True or caps.get('supply_sensing')!='DOWNSTREAM_POWER_CHECK' or caps.get('power_check_required') is not True or caps.get('power_check_timeout_ms')!=1500 or caps.get('power_check_settle_ms')!=50:
            raise RunRejected('Firmware downstream power-check contract mismatch')
        for name,wire in [('min_voltage','min_voltage_mv'),('max_voltage','max_voltage_mv'),('max_current','max_current_ma')]:
            if type(caps.get(wire)) is not int or caps[wire]!=round(profile['limits'][name]*1000):
                raise RunRejected('Firmware/Pi protection limit mismatch: '+name)
        if caps.get('motor_relay_active_level')!=0 or caps.get('circuit_relay_active_level')!=0:
            raise RunRejected('Firmware COM-LOW relay polarity mismatch')
        if caps.get('power_feedback_installed') is not profile.get('power_feedback_installed', False):
            raise RunRejected('Firmware/Pi power feedback installation mismatch')
        if profile.get('power_feedback_installed') and status.get('power_feedback_state') != 'HIGH':
            raise RunRejected('Power feedback is not HIGH')
        if caps.get('temperature_enabled') is not profile.get('temperature_enabled', True):
            raise RunRejected('Temperature configuration differs between firmware and Pi')
        if type(caps.get('fixed_pwm_percent')) is not int or caps['fixed_pwm_percent'] != profile['fixed_pwm_percent']:
            raise RunRejected('Approved duty mismatch')
        if type(caps.get('max_duration_ms')) is not int or caps['max_duration_ms'] != profile['max_duration_ms'] or not 0 < duration <= caps['max_duration_ms'] <= 30000:
            raise RunRejected('Firmware/Pi duration bound mismatch')
        if caps.get('fixed_direction') != 'FORWARD' or caps.get('heartbeat_timeout_ms') != 2000:
            raise RunRejected('Fixed direction or heartbeat shutdown capability mismatch')
        required = {'PREPARE_TEST_POWER','ARM_TEST', 'SET_PWM', 'START_TEST', 'STOP_TEST', 'EMERGENCY_STOP',
                    'GET_STATUS', 'GET_CAPABILITIES', 'READ_MEASUREMENTS'}
        commands = caps.get('commands')
        if not isinstance(commands, list) or not required.issubset(commands):
            raise RunRejected('Required ADS motor commands are missing')
        if type(status.get('applied_pwm_percent')) is not int or status['applied_pwm_percent'] != 0 or status.get('state') not in {'DISARMED', 'STOPPED', 'LOCKOUT'}:
            raise RunRejected('Output not initially disabled / controller state unknown')
        if status.get('power_check_required') is not True or status.get('motor_relay_requested_on') is not False:
            raise RunRejected('Initial motor relay-off command state not confirmed')
        # LOCKOUT may be cleared only by the explicit, operator-authorized ARM
        # path; this read-only check never clears faults or renews a heartbeat.

    @staticmethod
    def validate_sensors(profile, raw, tick, *, phase="running", powered_ms=None):
        channels = validate_measurements(raw)
        names = ['voltage', 'current', 'power', 'rpm']
        if profile.get('temperature_enabled', True):
            names.append('temperature')
        if raw.get('voltage_current_calibrated') is not True:
            raise RunRejected('Motor electrical calibration unverified')
        if profile.get('temperature_enabled', True) and raw.get('temperature_calibrated') is not True:
            raise RunRejected('Temperature calibration unverified')
        for name in names:
            item = channels[name]
            if not item['valid'] or ((tick - item['timestamp_ms']) & 0xffffffff) > (3000 if name == 'temperature' else 1500):
                raise RunRejected('Sensor acquisition invalid or stale: ' + name)
        if type(raw.get('sample_sequence')) is not int or type(raw.get('electrical_sequence')) is not int:
            raise RunRejected('Acquisition sequence missing')
        if len({channels[name]['timestamp_ms'] for name in ('voltage', 'current', 'power')}) != 1:
            raise RunRejected('Motor electrical values are not from the same acquisition')
        prefixes = ['electrical', 'encoder'] + (['temperature'] if profile.get('temperature_enabled', True) else [])
        for prefix in prefixes:
            begin, end = raw.get(prefix + '_started_ms'), raw.get(prefix + '_completed_ms')
            if type(begin) is not int or type(end) is not int or ((end - begin) & 0xffffffff) > 3000:
                raise RunRejected('Invalid sensor acquisition interval: ' + prefix)
        limits=profile['limits']
        if abs(channels['current']['value'])>=limits['max_current']:
            raise RunRejected('OVERCURRENT')
        voltage=channels['voltage']['value']
        if voltage<0 or voltage>limits['max_voltage']:raise RunRejected('SUPPLY_OUT_OF_RANGE')
        if phase=='deenergized':
            if voltage>=limits['min_voltage']:raise RunRejected('POWER_PRESENT_WHILE_STOPPED: check relay contacts or retained charge')
            if channels['rpm']['value']!=0:raise RunRejected('Motor must be stationary before the power check')
        elif phase=='checking':
            if type(powered_ms) is not int:raise RunRejected('Power-check acquisition timestamp missing')
            delta=(raw['electrical_started_ms']-powered_ms)&0xffffffff
            if delta<50 or delta>=0x80000000:raise RunRejected('Power-check acquisition pending')
            if voltage<limits['min_voltage']:raise RunRejected('SUPPLY_OUT_OF_RANGE: relay/load supply failed the power check')
        elif phase=='running':
            if voltage<limits['min_voltage']:raise RunRejected('SUPPLY_OUT_OF_RANGE')
        else:raise RunRejected('Unknown electrical protection phase')
        return channels

    def remember(self, report):
        self.last_preflight = report
        self.checked_at = time.monotonic()
        return self.snapshot()

    def snapshot(self):
        report = dict(self.last_preflight or {'ready': False, 'reason': 'Read-only hardware preflight not yet performed',
                                              'firmware_hardware_control': None})
        report['runtime_enabled'] = self.enabled
        report['age_seconds'] = round(time.monotonic() - self.checked_at, 2) if self.checked_at else None
        report['stale'] = self.checked_at == 0 or time.monotonic() - self.checked_at > 15
        report['ready'] = report['ready'] and self.enabled and not report['stale']
        if report['stale'] and self.last_preflight:
            report['reason'] = 'Preflight snapshot expired; repeat before testing'
        return report
