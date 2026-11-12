# Full integration file manifest

Includes the earlier local bounded-firmware work carried into this integration.
All paths are relative to the repository root. Generated ELF, frontend dist and
Pi ZIP are local artifacts, excluded from Git.

- `.env.example`
- `.gitignore`
- `ADS/ADS.ioc`
- `ADS/Core/Inc/ads_acquisition.h`
- `ADS/Core/Inc/ads_board_config.h`
- `ADS/Core/Inc/ads_motor.h`
- `ADS/Core/Inc/ads_protocol.h`
- `ADS/Core/Inc/ads_sensors.h`
- `ADS/Core/Inc/ads_test.h`
- `ADS/Core/Inc/stm32f4xx_hal_conf.h`
- `ADS/Core/Src/ads_acquisition.c`
- `ADS/Core/Src/ads_motor.c`
- `ADS/Core/Src/ads_protocol.c`
- `ADS/Core/Src/ads_sensors.c`
- `ADS/Core/Src/ads_test.c`
- `ADS/Core/Src/main.c`
- `ADS/Core/Src/stm32f4xx_it.c`
- `ADS/Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_i2c.h`
- `ADS/Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_i2c_ex.h`
- `ADS/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c`
- `ADS/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c`
- `ADS/Makefile`
- `ADS/STM32F401RETX_FLASH.ld`
- `ADS/STM32F401RETX_RAM.ld`
- `README.md`
- `api/main.py`
- `api/schemas.py`
- `deploy/pi/build_bundle.py`
- `deploy/pi/configure.py`
- `deploy/pi/hardware-profile.example.json`
- `deploy/pi/install.sh`
- `diagnostic_platform/automated_engine.py`
- `diagnostic_platform/automated_storage.py`
- `diagnostic_platform/collector.py`
- `diagnostic_platform/device_simulator.py`
- `diagnostic_platform/health_analysis.py`
- `diagnostic_platform/live.py`
- `diagnostic_platform/protocol.py`
- `diagnostic_platform/stm32.py`
- `diagnostic_platform/test_registry.py`
- `diagnostic_platform/text_telemetry.py`
- `diagnostic_platform/verify_stm32.py`
- `docs/ARCHITECTURE.md`
- `docs/BOUNDED_STM32_MOTOR_TEST.md`
- `docs/CURRENT_STATE.md`
- `docs/FULL_AUTOMATED_INTEGRATION.md`
- `docs/FULL_INTEGRATION_AUDIT.md`
- `docs/FULL_INTEGRATION_FILES.md`
- `docs/HARDWARE_CAPABILITIES.md`
- `docs/MOTOR_RELAY_BENCH_TEST.md`
- `docs/SERIAL_PROTOCOL.md`
- `docs/STM32_FIRMWARE_AUDIT.md`
- `docs/STM32_INTEGRATION_PLAN.md`
- `docs/STM32_INTEGRATION_STATUS.md`
- `docs/STM32_PLAIN_TEXT_MOTOR.md`
- `frontend/src/App.tsx`
- `frontend/src/PhysicalCircuit.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `tests/bounded_motor_harness.c`
- `tests/bounded_output_harness.c`
- `tests/hal_stub/stm32f4xx_hal.h`
- `tests/test_automated_api.py`
- `tests/test_automated_engine.py`
- `tests/test_bounded_motor.py`
- `tests/test_deployment.py`
- `tests/test_firmware_protocol.py`
- `tests/test_health_analysis.py`
- `tests/test_motor_safety.py`
- `tests/test_stm32.py`
- `tests/test_text_telemetry.py`

Additional dashboard motor-control increment: see [changed-file list](DASHBOARD_MOTOR_CONTROL.md#files-changed-for-this-increment). New files include diagnostic_platform/motor_csv.py, frontend/src/HardwareMotorControls.tsx, tests/test_motor_dashboard_integration.py and docs/DASHBOARD_MOTOR_CONTROL.md.

Dual INA219 increment: see [changed-file list](DUAL_INA219_INTEGRATION.md#changed-files-in-this-increment) for the new independent driver, read-only polling, verifier, branch displays and tests.
