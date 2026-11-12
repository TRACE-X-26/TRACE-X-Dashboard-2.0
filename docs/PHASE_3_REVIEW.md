# Phase 3 Firmware Communication Review

**Status:** communication-only firmware compiles; no board was flashed

**Motor output:** disabled and unconfigured

**ADC/sensors:** disabled and unconfigured

**CubeMX regenerated:** no

## Software checks

From the repository root:

```bash
source .venv/bin/activate
python3 -m unittest discover -s tests
```

Expected result: 49 tests pass. Three of these compile the hardware-independent
C protocol with the Mac host compiler, feed it frames created by the production
Python encoder, and validate the C replies with the production Python decoder.

## Open and build in STM32CubeIDE

1. Open STM32CubeIDE.
2. Choose **File → Import → Existing Projects into Workspace**.
3. Select `/Users/markussanford/Documents/ChatGPT/Capstone/ADS`.
4. Confirm project `ADS` is selected and finish the import.
5. Select the **Debug** build configuration.
6. Choose **Project → Clean**, then **Project → Build Project**.

The automated clean Debug build completed with zero errors and zero warnings.
Do not open the `.ioc` and approve code generation during this review; the clock
source representation still needs an explicit decision.

## Source review

- `ADS/Core/Inc/ads_protocol.h`: limits, timeout, safe states, compile-time
  legacy banner switch.
- `ADS/Core/Src/ads_protocol.c`: parser and safe response implementation.
- `ADS/Core/Src/main.c`: only `USER CODE` regions changed; USART2 and clock
  initialization remain generated and unchanged.
- `docs/STM32_FIRMWARE_AUDIT.md`: configuration and clock evidence.
- `docs/STM32_INTEGRATION_PLAN.md`: gated path toward hardware functionality.

## Optional board check — only with motor power disconnected

Flashing is not required to approve this software phase. If you choose to test
the board, disconnect the MD10C motor supply and all unverified sensor circuits
first. Flash the Debug image, identify the ST-LINK virtual COM port, and send
only `GET_STATUS`, `GET_CAPABILITIES`, `GET_FAULTS`, and heartbeat frames.

Expected behavior:

- valid safe requests receive correlated JSON replies;
- measurement requests return `MEASUREMENTS_UNAVAILABLE`;
- all motor requests return `CONTROL_DISABLED`;
- nothing configures or toggles a PWM or direction pin.

Do not connect motor power based on a successful serial test.
