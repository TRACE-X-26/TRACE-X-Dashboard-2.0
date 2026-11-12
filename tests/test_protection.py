"""Protected firmware and profile gates; no physical hardware access."""
import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from diagnostic_platform.automated_engine import load_hardware_profile,RunRejected
ROOT=Path(__file__).resolve().parents[1]
class ProtectionTests(unittest.TestCase):
    def test_actual_c_protection_numeric_edges_invalid_stale_and_rollover(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host compiler unavailable')
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'protection'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'ADS/Core/Inc'),
                str(ROOT/'ADS/Core/Src/ads_protection.c'),str(ROOT/'tests/protection_harness.c'),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)
    def test_wrong_topology_is_rejected_without_changing_motor_limits(self):
        p=json.loads((ROOT/'deploy/pi/supervised-operator-profile.json').read_text())
        p['serial_identity']='IN_MEMORY_ONLY';p['protection_limits_verified']=True
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'profile.json'
            for location,verified in [('UPSTREAM_MOTOR_RELAY',False),('UPSTREAM_MOTOR_RELAY',True)]:
                p['supply_sensing']={'location':location,'verified':verified};path.write_text(json.dumps(p))
                with self.assertRaisesRegex(RunRejected,'Downstream motor sensing'):load_hardware_profile(path)
                # Circuit supply switching does not borrow motor voltage/sensing requirements.
                with self.assertRaises(RunRejected):load_hardware_profile(path,require_motor_protection=False)
            p['supply_sensing']={'location':'DOWNSTREAM_MOTOR_RELAY','verified':True}
            path.write_text(json.dumps(p));load_hardware_profile(path)

    def test_missing_protection_callback_fails_closed_even_with_fake_commissioning(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host compiler unavailable')
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'missing'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),
                '-include',str(ROOT/'ADS/bench/supervised.operator.h'),
                '-DADS_PROTECTION_LIMITS_VERIFIED=1',
                '-DTEST_PROTECTION_MISSING=1',str(ROOT/'ADS/Core/Src/ads_motor.c'),
                str(ROOT/'ADS/Core/Src/ads_circuit_relay.c'),str(ROOT/'tests/active_low_relays_harness.c'),
                '-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)

    def test_current_cubeide_default_cannot_energize_either_branch(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host compiler unavailable')
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'disabled'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),
                '-DADS_USE_PROTECTED_PROFILE=1','-DTEST_DEFAULT_DISABLED=1',
                str(ROOT/'ADS/Core/Src/ads_motor.c'),str(ROOT/'ADS/Core/Src/ads_circuit_relay.c'),
                str(ROOT/'tests/active_low_relays_harness.c'),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)

    def test_actual_output_driver_zero_pwm_power_check_deadline_and_failed_sample(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host compiler unavailable')
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'prepower'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),
                '-include',str(ROOT/'ADS/bench/supervised.operator.h'),
                '-DADS_PROTECTION_LIMITS_VERIFIED=1','-DTEST_PREPOWER=1',
                str(ROOT/'ADS/Core/Src/ads_motor.c'),str(ROOT/'ADS/Core/Src/ads_circuit_relay.c'),
                str(ROOT/'tests/active_low_relays_harness.c'),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)
