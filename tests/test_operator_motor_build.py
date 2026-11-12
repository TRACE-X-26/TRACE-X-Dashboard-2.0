"""Actual operator profile against fake GPIO; no real board is exercised."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from diagnostic_platform.automated_engine import load_hardware_profile, RunRejected

ROOT = Path(__file__).resolve().parents[1]


class OperatorMotorBuildTests(unittest.TestCase):
    def test_make_and_cubeide_profiles_boot_stopped_and_enforce_shutdown(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('Host C compiler unavailable')
        project = ET.parse(ROOT / 'ADS/.cproject')
        symbols = project.findall(".//option[@superClass='com.st.stm32cube.ide.mcu.gnu.managedbuild.tool.c.compiler.option.definedsymbols']")
        self.assertEqual(len(symbols), 2)
        for option in symbols:
            self.assertIn('ADS_USE_PROTECTED_PROFILE=1', [e.get('value') for e in option])
        with tempfile.TemporaryDirectory() as directory:
            for route in ('make', 'cubeide'):
                with self.subTest(route=route):
                    flags = (['-include', str(ROOT / 'ADS/bench/supervised.operator.h')]
                             if route == 'make' else ['-DADS_USE_OPERATOR_PROFILE=1'])
                    exe = Path(directory) / route
                    subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    '-I', str(ROOT / 'tests/hal_stub'), '-I', str(ROOT / 'ADS/Core/Inc'),
                                    *flags,'-DADS_PROTECTION_LIMITS_VERIFIED=1', str(ROOT / 'ADS/Core/Src/ads_motor.c'),
                                    str(ROOT / 'tests/power_feedback_harness.c'), '-o', str(exe)],
                                   check=True, capture_output=True)
                    subprocess.run([str(exe)], check=True)

    def test_both_com_low_drivers_preload_high_and_release_on_all_stops(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            for route in ('make','cubeide'):
                with self.subTest(route=route):
                    flags=(['-include',str(ROOT/'ADS/bench/supervised.operator.h')]
                           if route=='make' else ['-DADS_USE_OPERATOR_PROFILE=1'])
                    exe=Path(directory)/route
                    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                        '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),*flags,'-DADS_PROTECTION_LIMITS_VERIFIED=1',
                        str(ROOT/'ADS/Core/Src/ads_motor.c'),str(ROOT/'ADS/Core/Src/ads_circuit_relay.c'),
                        str(ROOT/'tests/active_low_relays_harness.c'),'-o',str(exe)],check=True,capture_output=True)
                    subprocess.run([str(exe)],check=True)

    def test_pi_operator_profile_keeps_actual_device_identity_required(self):
        profile = ROOT / 'deploy/pi/supervised-operator-profile.json'
        with self.assertRaises(RunRejected):
            load_hardware_profile(profile)
        data = json.loads(profile.read_text())
        self.assertFalse(data['commissioning_attestation']['independently_verified_by_agent'])
        self.assertFalse(data['encoder']['calibrated'])
        self.assertFalse(data['power_feedback_installed'])
        data['serial_identity'] = 'TEST_FIXTURE_ONLY'
        data['protection_limits_verified']=True
        data['supply_sensing']['verified']=True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            path.write_text(json.dumps(data))
            loaded = load_hardware_profile(path)
            self.assertEqual(loaded['operating_mode'], 'SUPERVISED_TEST')
            self.assertTrue(loaded['electrical_limits_enabled'])
            self.assertEqual(loaded['limits']['max_current'],1.5)
