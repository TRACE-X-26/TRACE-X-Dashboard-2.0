# Trace-X motor relay acceptance

November 6 update: see [bounded firmware delivery](BOUNDED_STM32_MOTOR_TEST.md)
for the new default-disabled command state machine, acquisition adapters and
remaining physical acceptance gates. Earlier implementation-stage descriptions
below are historical and do not establish current bench verification.

This is a manual bench procedure, not authorization to flash firmware or run the
motor. Keep all production motor-control commands disabled. The current change
performs no flash, GPIO exercise on hardware or motor energization.

## Wiring-design record

| Function | Confirmed design |
| --- | --- |
| Motor supply positive | 12 V positive → AEDIKO relay COM → NO → MD10C positive motor-supply input |
| Motor supply return | 12 V negative → MD10C negative motor-supply input |
| Motor relay input | STM32 PB5 |
| Circuit-testing relay | STM32 PB4; untouched by the motor interface |
| Driver PWM | PB10, TIM2 Channel 3 |
| Driver direction | PA8; no direction operation enabled |
| ADS serial | USART2, PA2 TX / PA3 RX, 115200 8N1 |

NO/COM selection is confirmed at design level. An open contact with a
de-energized coil is expected, but has not been measured. Trigger-jumper
selection, GPIO activation level, logic compatibility, contact behavior and
supply disconnection remain unverified. Record the relay's exact model and
jumper position; do not infer its trigger behavior from its brand.

## Stage 1: isolate and identify

1. Disconnect the 12 V source and motor. Verify absence of voltage before using
   continuity mode. Label PB5 and PB4 so motor tests cannot actuate the other
   relay. Inspect the actual COM/NO wiring against the design record.
2. Establish the relay module's coil supply, input voltage/current requirements,
   grounding and any isolation/jumper requirements from its actual documentation
   and measurements. Do not connect an unverified relay voltage to the STM32.
3. With contacts unpowered and the motor isolated, characterize the input using
   a compatible, current-limited bench logic source (disconnect the MCU input
   connection first). Test HIGH, LOW and undriven input for the actual jumper
   position. Measure input voltage and observe both coil state and COM–NO
   continuity. Record active and inactive levels. LEDs/clicks alone are not
   evidence of contact opening.
4. Verify that removal of coil power opens COM–NO. If it does not, reject the
   design or failed relay. Check that undriven input during MCU reset or an
   unpowered MCU cannot energize the relay. Establish and measure any necessary
   external bias/interlock; do not rely on an MCU pull before firmware starts.

## Stage 2: output and reset behavior

Use the isolated, instrumented bench setup and a separately authorized manual
firmware installation. Do not reconnect the motor. The default build has all
verification flags zero and active/inactive levels unknown: PB5 is undriven with
no pull. This state is not proof that the relay is off. If it activates the
relay, correct the external design before continuing.

Scope PB5, PB10 and reset, including the interval before application code runs.
Observe PB4 and PA8 to confirm the motor interface does not alter them. Test
cold power-up, reset-button hold/release, MCU power loss and recovery, and the
intended power-supply sequencing. Record relay input and contact behavior for
each case. Acceptance requires PB10 inactive and no relay activation pulse at
any transition; floating or ambiguous states fail acceptance.

After Stage 1 determines polarity, a reviewed bench configuration can specify
ADS_RELAY_ACTIVE_LEVEL=0 or 1 and ADS_RELAY_INACTIVE_LEVEL as its complement.
ADS_RELAY_DISCONNECT_LEVEL is a compatibility alias and must match inactive.
Only documented physical acceptance may set the relevant flags to 1:

- ADS_RELAY_POLARITY_VERIFIED: actual trigger-jumper/input behavior measured.
- ADS_RELAY_POWER_PATH_VERIFIED: actual contacts and supply interruption measured.
- ADS_RELAY_SAFE_OUTPUT_VERIFIED: initialization, reset, power sequencing and
  externally biased input behavior meet the acceptance criteria.

PB5 output drive is gated on all three flags. No flag enables remote motor
commands. When enabled for an accepted board, firmware preloads the inactive
latch before selecting GPIO output mode. Repeat the scope/contact tests on that
exact reviewed configuration. Do not mark an untested behavior verified merely
to make the firmware drive PB5.

## Stage 3: shutdown and actual supply interruption

Keep the motor physically disconnected. Use a suitable current-limited supply
and defined test load/bleed path in the approved bench setup; a floating supply
node is not a meaningful indication of disconnection. Use appropriate voltage
measurement instead of continuity mode on powered contacts. An independently
accessible physical power disconnect must remain available.

Record MD10C positive-to-negative motor-supply voltage and COM/NO voltage before
and after each stop. Verify the interruption path, expected discharge time and
absence of backfeed, accounting for any stored energy. The acceptance threshold
and maximum allowed shutdown/discharge time must be set for the actual hardware
before testing; a GPIO trace or relay click does not establish either.

| Test | Required observation |
| --- | --- |
| Startup and reset | No PWM pulses; relay remains de-energized; motor supply disconnected throughout startup/reset sequencing |
| Normal/repeated stop | TIM2 CH3 disabled, CCR3 zero, PB10 low, inactive PB5 request, measured contact opening and supply disconnection |
| Heartbeat loss | At the 2000 ms STM32 deadline, PWM disabled and relay de-energization requested; measure actual opening/discharge latency separately |
| Invalid/unsupported commands | No activation; malformed frames and rejected motor commands do not extend the motor watchdog deadline |
| Late heartbeat/reconnect | Timeout remains latched; no restart or output pulse |
| Fault injection | In a separately reviewed, motor-isolated test, callable fault path requests shutdown; recovery/reset never starts the motor |
| MCU/relay failure | Evaluate independently of firmware; verify the external power disconnect and fail-safe design rather than claiming software coverage |

Retain CSV/serial logs, scope captures, voltages, contact observations, wiring
revision, jumper setting, configuration/build identity, test IDs, operator and
UTC times. All motor commands remain disabled after this procedure until a
separate reviewed change explicitly enables them. This document does not do so.

## Limits

The communication watchdog is software on the STM32, enforced by SysTick and the
main loop. It is not an independent hardware watchdog or power interlock. CPU
lockup, disabled interrupts, failed clocks, a fault that prevents the handler
running, shorted driver electronics or welded/stuck relay contacts can defeat
software shutdown. Fault handlers are best effort. Opening motor supply also
does not guarantee immediate mechanical standstill. Provide the external
fail-safe circuit and physical disconnection required by the actual apparatus;
do not report a software stop request as measured physical safety.
