import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class MotorSafetyTests(unittest.TestCase):
    def test_stop_startup_repeated_shutdown_and_recovery_for_both_polarities(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Host C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            for verified, level, polarity, safe_output in [(0, -1, 0, 0), (1, 0, 1, 1), (1, 1, 1, 1),
                                                               (1, 0, 0, 1), (1, 1, 1, 0), (0, 0, 1, 1)]:
                with self.subTest(verified=verified, disconnect_level=level):
                    executable = str(Path(directory) / 'motor')
                    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'tests/hal_stub'), '-I', str(ROOT / 'ADS/Core/Inc'),
                        f'-DADS_RELAY_POWER_PATH_VERIFIED={verified}',
                        f'-DADS_RELAY_DISCONNECT_LEVEL={level}',
                        f'-DADS_RELAY_ACTIVE_LEVEL={1-level if level != -1 else -1}',
                        f'-DADS_RELAY_POLARITY_VERIFIED={polarity}',
                        f'-DADS_RELAY_SAFE_OUTPUT_VERIFIED={safe_output}',
                        str(ROOT / 'ADS/Core/Src/ads_motor.c'),
                        str(ROOT / 'ADS/Core/Src/ads_protocol.c'),
                        str(ROOT / 'ADS/Core/Src/ads_test.c'),
                        str(ROOT / 'tests/motor_safety_harness.c'), '-o', executable],
                        check=True, capture_output=True)
                    for scenario in ["startup", "watchdog", "fault", "wrap", "protocol", "late", "fault-before-init"]:
                        subprocess.run([executable, scenario], check=True)

    def test_verified_relay_requires_explicit_binary_disconnect_level(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Host C compiler unavailable')
        for level in [-1, 2]:
            completed = subprocess.run([compiler, '-fsyntax-only',
                '-I', str(ROOT / 'tests/hal_stub'), '-I', str(ROOT / 'ADS/Core/Inc'),
                '-DADS_RELAY_POWER_PATH_VERIFIED=1', f'-DADS_RELAY_DISCONNECT_LEVEL={level}',
                str(ROOT / 'ADS/Core/Src/ads_motor.c')], capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(b'explicit relay disconnect level', completed.stderr)

    def test_verified_polarity_rejects_unknown_or_matching_levels(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Host C compiler unavailable')
        for active, inactive in [(-1, -1), (0, 0), (1, 1), (2, 0)]:
            completed = subprocess.run([compiler, '-fsyntax-only',
                '-I', str(ROOT / 'tests/hal_stub'), '-I', str(ROOT / 'ADS/Core/Inc'),
                '-DADS_RELAY_POLARITY_VERIFIED=1', f'-DADS_RELAY_ACTIVE_LEVEL={active}',
                f'-DADS_RELAY_INACTIVE_LEVEL={inactive}', str(ROOT / 'ADS/Core/Src/ads_motor.c')],
                capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(b'opposite active/inactive binary levels', completed.stderr)

    def test_startup_and_fault_handlers_use_the_stop_interface(self):
        main = (ROOT / 'ADS/Core/Src/main.c').read_text()
        self.assertLess(main.index('  ADS_Motor_Init();'), main.index('  SystemClock_Config();'))
        self.assertIn('ADS_Protocol_SetHardwareCallbacks(&ads_protocol, ADS_Sensors_Acquire, ADS_StopMotor)', main)
        self.assertIn('ADS_Motor_Fault();', main[main.index('void Error_Handler(void)'):])
        handlers = (ROOT / 'ADS/Core/Src/stm32f4xx_it.c').read_text()
        for name in ['NMI', 'HardFault', 'MemManage', 'BusFault', 'UsageFault']:
            body = handlers.split(f'void {name}_Handler(void)', 1)[1].split('while (1)', 1)[0]
            self.assertIn('ADS_Motor_Fault();', body)
        self.assertIn('ADS_Motor_Poll(HAL_GetTick());', handlers[handlers.index('void SysTick_Handler'):])
