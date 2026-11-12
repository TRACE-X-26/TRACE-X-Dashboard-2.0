# STM32 Firmware and `.ioc` Audit

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

**Inspected:** October 14, 2026

**Project:** `ADS/` in this repository

**Board:** NUCLEO-F401RE / STM32F401RET6

**Cube firmware package:** STM32Cube FW_F4 V1.28.3

**CubeMX version recorded by project:** 6.18.1

## Preservation scope

The complete CubeIDE project was inspected before source changes. `ADS.ioc`,
CubeIDE metadata, startup code, linker scripts, generated initialization
functions, HAL drivers, and existing pin assignments were not regenerated or
rewritten. The communication integration adds two application files and touches
only `USER CODE` regions in `Core/Src/main.c`.

Machine-specific `TraceX.app`, transient drawing files, and generated
`Debug/`/`Release/` outputs are excluded from Git. This does not affect opening
or rebuilding the project in STM32CubeIDE.

The imported `ADS Debug.launch` file still contains its original absolute
ST-LINK log path (`/Users/markussanford/ADS/Debug/...`). It is not used by the
build. If debugging from the repository copy, create or update the local launch
configuration in STM32CubeIDE so its log/output path points at the active
workspace; this metadata was left unchanged during source integration.

## Existing generated configuration

| Peripheral | Configuration | Status |
|---|---|---|
| USART2 | Asynchronous TX/RX on PA2/PA3 | **IMPLEMENTED; BUILD VERIFIED, HARDWARE UNVERIFIED** |
| GPIO PA5 | Nucleo LD2 green LED, push-pull output low | **UNCHANGED** |
| GPIO PC13 | Nucleo B1 pushbutton, falling-edge mode | **UNCHANGED** |
| SWD/SWO | PA13, PA14, PB3 | **UNCHANGED DEBUG INTERFACE** |
| ADC | Not configured; HAL module disabled | **UNSUPPORTED** |
| I²C | Not configured; HAL module disabled | **UNSUPPORTED** |
| Timer/PWM | Not configured; HAL timer module disabled | **UNSUPPORTED** |
| RPM input/capture | Not configured | **UNSUPPORTED** |
| Relay outputs | Not configured | **UNSUPPORTED** |
| Hardware watchdog | Not configured | **UNSUPPORTED** |

There is no assigned MD10C PWM pin or direction pin. The communication-only
firmware does not initialize or write any prospective motor pin.

## Actual pin map

| STM32 pin | `.ioc` label/function | Current use |
|---|---|---|
| PA2 | `USART_TX` / USART2_TX | STM32 to ST-LINK virtual COM transmit |
| PA3 | `USART_RX` / USART2_RX | ST-LINK virtual COM to STM32 receive |
| PA5 | `LD2 [Green Led]` | Initialized low; no protocol behavior |
| PC13 | `B1 [Blue PushButton]` | Configured input/EXTI; no application handler |
| PA13 | TMS/SWDIO | Debug |
| PA14 | TCK/SWCLK | Debug |
| PB3 | SWO | Debug trace |

## USART2 implementation comparison

Generated USART2 settings match the Raspberry Pi transport:

- 115200 baud, 8 data bits, no parity, 1 stop bit
- no hardware flow control
- 16x oversampling
- PA2/PA3, AF7, alternate-function push-pull
- Nucleo ST-LINK virtual COM connection

The original main loop used blocking `HAL_UART_Transmit` to send
`STM32 CONNECTED TO PI\r\n` once per second and never called a receive API. The
Phase 2 backend expects newline-delimited JSON request/response frames, so the
plain-text loop could not interoperate with it.

The integration retains the original banner path behind
`ADS_PROTOCOL_LEGACY_BANNER_ENABLED`, defaulting to `0`. The default path polls
USART2 one byte at a time with a 1 ms bound, assembles a bounded line, and passes
it to the hardware-independent protocol module. UART pin and initialization code
are unchanged.

## Clock investigation

The runtime clock path is unambiguous in both `Core/Src/main.c` and the prior
compiled listing:

- HSI = 16 MHz is enabled.
- PLL source = HSI.
- PLLM=16, PLLN=336, PLLP=4, PLLQ=7.
- SYSCLK/HCLK = 84 MHz, APB1 = 42 MHz, APB2 = 84 MHz.

The `.ioc` also records the 84/42/84 MHz derived values, but reserves PH0/PH1 as
an external HSE clock source. It does not serialize explicit `RCC.PLLSource` or
`PLLM` fields. That can represent an unused HSE pin reservation with the default
HSI PLL choice, or stale clock metadata; the file alone cannot distinguish the
two. The generated source is newer than the `.ioc` and the previous ELF listing
matches the HSI implementation.

Decision: keep the known generated HSI clock code unchanged. Before any future
CubeMX regeneration, open Clock Configuration and explicitly choose whether HSI
or the Nucleo ST-LINK MCO/HSE bypass is authoritative, save the `.ioc`, inspect
the generated diff, and recheck USART2 baud on hardware. Do not switch clock
sources as part of communication or motor work.

## Communication integration status

`Core/Inc/ads_protocol.h` and `Core/Src/ads_protocol.c` implement the safe subset
of protocol version 1. Supported now:

- `GET_STATUS`
- `GET_CAPABILITIES`
- `GET_FAULTS`
- heartbeat request/acknowledgment
- correlated error responses
- bounded 512-byte receive frames
- a 2000 ms communication-age safety state

The firmware explicitly rejects measurement requests and every motor command.
It advertises no measurement types and reports `hardware_control:false`, PWM 0,
and direction `UNCONFIGURED`.

## Build evidence

STM32CubeIDE 14.3 ARM GCC completed a clean headless Debug build with zero errors
and zero warnings. The resulting image used 16,276 bytes of flash text/data and
2,516 bytes of BSS (18,884 bytes total reported by `arm-none-eabi-size`). This is
compile evidence only; the image was not flashed and no hardware behavior was
verified.
