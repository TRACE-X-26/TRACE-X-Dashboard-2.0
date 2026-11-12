import unittest
from unittest.mock import patch

from diagnostic_platform.live import LiveMonitor


class LiveMonitorTests(unittest.TestCase):
    def test_default_never_opens_serial(self):
        with patch.object(LiveMonitor, '_open_serial', side_effect=AssertionError('must not open')):
            monitor = LiveMonitor()
            monitor.start()
            self.assertFalse(monitor.snapshot()['enabled'])
            self.assertFalse(monitor.snapshot()['hardware_control'])

    def test_asynchronous_legacy_values_are_not_fabricated_power(self):
        monitor = LiveMonitor()
        monitor.feed('Voltage: 12.276 V')
        monitor.feed('Current: 0.134 A')
        state = monitor.snapshot()
        self.assertEqual(state['channels']['voltage']['value'], 12.276)
        self.assertNotIn('input_power', state['channels'])
        self.assertIsNone(state['diagnosis']['health_score'])

    def test_stale_channel_and_failed_sensor_do_not_appear_current(self):
        monitor = LiveMonitor()
        with patch('diagnostic_platform.live.time.monotonic', return_value=100):
            monitor.feed('Temperature: 31.4 C')
        with patch('diagnostic_platform.live.time.monotonic', return_value=104):
            self.assertEqual(monitor.snapshot()['channels']['temperature']['quality'], 'STALE')
        monitor.feed('TEMPERATURE SENSOR: NOT DETECTED')
        self.assertNotIn('temperature', monitor.snapshot()['channels'])

    def test_structured_motor_values_and_circuit_exclusion(self):
        monitor = LiveMonitor()
        monitor.feed('{"mode":"MOTOR","motor_voltage_V":12,"motor_current_A":0.5}')
        self.assertEqual(monitor.snapshot()['channels']['input_power']['value'], 6)
        monitor.feed('{"mode":"CIRCUIT","voltage":5}')
        self.assertEqual(monitor.snapshot()['channels']['voltage']['value'], 12)
        self.assertIn('NON_MOTOR_ROW_EXCLUDED', monitor.snapshot()['warnings'])

    def test_reset_and_event_state(self):
        monitor = LiveMonitor()
        monitor.feed('MOTOR_START')
        monitor.feed('Motor RPM: 78')
        self.assertEqual(monitor.snapshot()['recorded_motor_phase'], 'RUNNING')
        monitor.feed('reboot')
        self.assertEqual(monitor.snapshot()['channels'], {})
        self.assertEqual(monitor.snapshot()['recorded_motor_phase'], 'UNKNOWN')

    def test_probe_fault_invalidates_probe_without_scaling_or_replacing_supply(self):
        import json

        monitor = LiveMonitor()
        monitor._connected = True
        frame = {'mode': 'CIRCUIT', 'asset_id': 'CIRCUIT', 'test_point_id': 'TP1',
                 'test_point_voltage_V': 0, 'circuit_supply_voltage_V': 12, 'circuit_current_A': .25}
        monitor.feed(json.dumps(frame))
        values = {c['channel']: c['value'] for c in monitor.snapshot()['circuit_channels']}
        self.assertEqual(values['test_point_voltage'], 0)
        self.assertEqual(values['circuit_power'], 3)
        monitor.feed(json.dumps({**frame, 'test_point_voltage_V': 5.2}))
        values = {c['channel']: c['value'] for c in monitor.snapshot()['circuit_channels']}
        self.assertEqual(values['test_point_voltage'], 5.2)
        monitor.feed(json.dumps({**frame, 'protection_event': True}))
        state = monitor.snapshot()
        self.assertNotIn('test_point_voltage', {c['channel'] for c in state['circuit_channels']})
        self.assertIn('PROBE_SATURATION_OR_PROTECTION_EVENT', state['warnings'])
        self.assertEqual(state['channels'], {})

    def test_ads_power_requires_a_shared_acquisition_tick_and_zero_temperature_is_valid(self):
        from diagnostic_platform.collector import CHANNELS

        values = {'voltage': 12, 'current': -.25, 'power': 17, 'temperature': 0, 'rpm': 0}
        measurements = {name: dict(value=values[name], unit=unit, valid=True, timestamp_ms=100)
                        for name, unit in CHANNELS.items()}
        monitor = LiveMonitor()
        monitor._feed_ads_measurements({'measurements': measurements}, 'now', 100)
        self.assertEqual(monitor.snapshot()['channels']['input_power']['value'], -3)
        self.assertEqual(monitor.snapshot()['channels']['temperature']['value'], 0)
        measurements['current']['timestamp_ms'] += 1
        monitor._feed_ads_measurements({'measurements': measurements}, 'later', 101)
        state = monitor.snapshot()
        self.assertNotIn('input_power', state['channels'])
        self.assertIn('MOTOR_ELECTRICAL_TIMESTAMPS_DIFFER', state['warnings'])
