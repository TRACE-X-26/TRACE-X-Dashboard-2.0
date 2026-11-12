# Bounded STM32 motor test — delivery and acceptance record

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

Date: November 6, 2026. Repository baseline: `69c8575`, branch
`trace-x-integration-2026-10-30`, TRACE-X-26/Dashboard.

**Firmware source and tests are implemented locally. Nothing has been flashed,
energized, committed or pushed by this task. Physical output is disabled. There
is no bench-approved duty/direction/duration or measured relay acceptance yet.
The existing dashboard layout and controls are unchanged and remain simulated.**

## 1. Device inspection and source provenance

Before editing, STM32CubeProgrammer 2.23.0 was run with `-l` (enumeration only).
It reported **No ST-Link detected**, no STM32 DFU device and no relevant USB
serial port. A second enumeration outside the sandbox confirmed the result.
No connection, reset, flash read, debug attach, erase or download was attempted.
The board on the Pi is not exposed to this Mac. Therefore the currently flashed
firmware identity and its exact matching source remain **unverified**. The
previously supplied Pi address was not treated as evidence of current access.
Do not describe the local ELF as a readback of the board.

Available comparison source was inspected at `/Users/markussanford/ADS`, linked
by CubeIDE workspace metadata. Its `Core/Src/main.c` SHA-256 is
`f75d5393660caba60e1c871495e57481cf091b2ff872283ae5071fc53ab94a0b`.
Its existing `Debug/ADS.elf` SHA-256 is
`eff95d32044698e217e24337696191c48085ec646b37dea9a923bcec1e811c1d`.
Neither was changed. This project implements automatic 50% PWM and 30-second
stop, INA219 register readings, A-edge encoder counting, DS18B20 one-wire/CRC,
and MOTOR_START/MOTOR_STOP text. Several comments incorrectly say 10%/10 seconds.
Its protocol files match repository commit `06a53c7` (communication-only v1).

Repository `ADS/` differs: `cf2e26c` added startup/fault/watchdog motor shutdown,
but no acquisition callback or automatic run. `69c8575` added passive plain-text
Pi parsing without changing firmware. This delivery reuses that shutdown and
ADS v1 envelopes; it ports available sensor routines into gated adapters and
adds pure conversion/cache tests. The vendor I2C files are copied unchanged
from the available local STM32 project, retaining ST copyright/license headers.
There is no recovered board firmware binary/source match or verified wiring.

Missing evidence: board readback/build identity; actual GPIO/probe wiring;
relay model, jumper, active level and reset contact measurements; physical kill
and enable-feedback wiring; calibrated shunt and INA219 identity; encoder CPR,
gear ratio and sign; temperature wiring/mounting and reference comparison; motor
limits; approved test duty and duration; communication-loss/contact-opening
scope traces. These gaps are gates, not assumptions silently marked verified.

## 2. Board gates and shutdown

Read `MOTOR_RELAY_BENCH_TEST.md` before any hardware change. Intended pin map:

| Function | Design/source evidence | This default build |
|---|---|---|
| PWM | PB10 / TIM2 CH3 | timer/channel off; pad held LOW |
| Direction | PA8 | no start/direction write |
| Motor relay | PB5, COM/NO motor supply path | input/no pull while polarity unverified |
| Circuit relay | PB4 | never accessed by motor code |
| Serial | USART2 PA2/PA3 via ST-LINK, 115200 8N1 | ADS v1 JSON, newline framing |
| Motor INA219 #1 | I2C1 PB8 SCL/PB9 SDA, address 0x40 in recovered source | sensor GPIO disabled |
| Encoder | PA6 A rising-edge EXTI; PC7 B input | sensor GPIO disabled |
| Housing DS18B20 | PA10 one-wire, external supply/pullup | sensor GPIO disabled |

These are intended/source mappings, **not a confirmation of physical wiring**.
PB5 input/no pull does not establish that the relay is off; external reset-time
fail-safe bias is required. The physical kill switch/power disconnect must stay
independent of software. No unknown kill-input GPIO has been invented.

`ads_board_config.h` defaults master enable, wiring/calibration/kill/communication
verification flags to zero, duty and maximum duration to zero, forward GPIO
level to unknown, and encoder CPR/gearing to unknown. Existing relay gates in
`ads_motor.h` remain. Set no acceptance flags merely to make a test start.

In addition, `ADS_Motor_InterlocksReady()` is a weak hook returning **false**.
A reviewed board-specific implementation with documented physical input(s) is
still required. It must be ISR-safe, nonblocking and fail closed; no I2C, logging,
serial or debounce waits in this hook. It must detect external stop/enable loss
and require deliberate physical recovery. Releasing an interlock does not clear
the firmware latch. Even setting every compile flag does not make this default
hook ready. Bench evidence must include this implementation, actual cutoff and
reset behavior. This is a deliberate remaining integration block.

Once separately accepted, the gated adapter uses the recovered 1 kHz timer
setup (84 MHz timer clock, PSC=83, ARR=999), PB10 AF1, fixed PA8 direction, and
known PB5 active/inactive levels. There is no output at boot, arm or SET_PWM.
The start adapter is atomic against ordinary interrupts and rejects a latched
shutdown. No changes to PB4 or circuit ADC scaling are involved.

All run exits call the same `ADS_Motor_Stop`: disable channel and timer, clear
CCR3, drive PB10 LOW, request verified relay de-energization. SysTick enforces
both the two-second communication deadline and bounded run duration independently
of main-loop serial processing; interlock loss also latches shutdown. MCU faults,
UART faults/overflow and failed transmission request shutdown. This is software
protection, not an independent hardware watchdog or proof of contact opening,
zero mechanical speed, welded-contact protection or CPU-lockup coverage.

## 3. State machine and ADS v1 commands

The portable controller states are DISARMED, ARMED, RUNNING, STOPPED and LOCKOUT.
A fresh heartbeat and explicit ARM_TEST are required for each run. Only a new,
accepted ARM_TEST after a fresh heartbeat can recover a fault/communication
lockout; heartbeat, STOP, reconnect and initialization never automatically rearm.
Runtime sensor/interlock readiness is checked before arm/start and while armed
or running. Motor current and temperature limits must be configured and valid.

Only one configured PWM and FORWARD direction are supported; there is no sweep.
Duration must be positive and at most the bench maximum (hard upper bound 30 s).
SET_PWM stages the approved value while armed; it never applies output. Changing
PWM while running or requesting SET_DIRECTION is rejected. Requested PWM and
applied PWM are separate fields. STOP_TEST and STOP_MOTOR always request the
common shutdown, including duplicate/old stops and disabled builds; they do not
clear a lockout or emit duplicate stop events.

START/ARM/SET_PWM controls use a monotonically increasing uint32 request sequence
per MCU boot. Replayed or older controls are rejected, including a duplicate
START after a previous run completed. A new START while running also fails and
cannot reset its timer. The Pi must retain sequence state or read GET_STATUS's
`last_control_seq` before reconnecting and continue above it. Do not wrap sequences
or replay saved commands across MCU resets. At uint32 exhaustion, isolate motor
power and establish a new MCU session rather than wrapping. There is no multi-
client arbitration; use one serial owner.

Original GET_STATUS, GET_CAPABILITIES, GET_FAULTS, heartbeat and READ_MEASUREMENTS
remain. Control decisions use ACK `payload.result.accepted`, `reason`,
`requested_pwm_percent`, `applied_pwm_percent`, state, run_id, timestamps,
last_control_seq, faults and stop_reason. An ACK alone is not acceptance.
Malformed envelopes retain correlated error handling when sequence is readable;
structurally unparseable input returns error reply_to=0 and does not run anything.

Examples below use **synthetic test inputs**, not approved operating settings:

```json
{"version":1,"type":"heartbeat","seq":1,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{}}
{"version":1,"type":"command","seq":2,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{"command":"ARM_TEST","arguments":{}}}
{"version":1,"type":"command","seq":3,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{"command":"SET_PWM","arguments":{"pwm_percent":10}}}
{"version":1,"type":"command","seq":4,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{"command":"START_TEST","arguments":{"pwm_percent":10,"direction":"FORWARD","duration_ms":1000}}}
{"version":1,"type":"command","seq":5,"device_id":"raspberry-pi","timestamp_ms":0,"payload":{"command":"STOP_TEST","arguments":{}}}
```

In the delivered default build ARM/START/SET_PWM return accepted=false,
reason=CONTROL_DISABLED, applied_pwm_percent=0. STOP returns accepted=true for
the software shutdown request, with physical_stop_verified=false.

Accepted starts and the first stop emit ADS v1 `type:event` envelopes. Example
from the fake-output harness (never hardware evidence):

```json
{"version":1,"type":"event","seq":6,"device_id":"STM32-ADS","timestamp_ms":1000,"payload":{"event":"MOTOR_STOP","event_sequence":2,"run_id":4,"reason":"COMPLETED","applied_pwm_percent":0,"physical_motion_confirmed":false,"physical_stop_verified":false}}
```

Events confirm the STM32 software output transition/shutdown request, not physical
rotation or measured power removal. `run_id` is the accepted START request seq;
event_sequence detects event gaps. GET_STATUS retains latest run/start/stop
information for lost-event recovery. Main-loop event dispatch can lag SysTick's
physical output stop; timestamp is software confirmation time, not a scope trace.

UART reception now uses interrupts and a bounded 1024-byte ring so sensor reads
and response transmission do not normally lose incoming bytes. Overflow/error
requests stop, discards the incomplete frame and resynchronizes at newline.
One-wire critical slots remain short; continuous reception and timing still need
bench validation. The receive-frame limit remains 512 bytes; Python allows
larger responses. Do not interleave legacy text with ADS JSON in this build.

## 4. Acquisition and calibration contract

`main.c` now registers `ADS_Sensors_Acquire` and measurement metadata. The callback
returns a cache, not blocking conversions. With wiring gate OFF, channels are
invalid/null. With wiring confirmed but voltage/current or encoder calibration
unconfirmed, those engineering channels remain invalid/null. Temperature may be
conversion-valid with temperature_calibrated=false; this is not a claim of
bench accuracy. No values come from simulation or circuit ADC channels.

INA219 #1 is triggered for a single shunt+bus conversion (MODE=011) about every
100 ms; the adapter waits for CNVR, checks overflow and bounds conversion/read
completion to 20 ms. It reads held bus/shunt registers before triggering another
conversion, so the pair has an electrical_sequence and one acquisition interval.
Current is calculated from signed shunt voltage and the measured shunt resistance,
not an unconfigured current-register calibration. Voltage is V, current A, power
W. The default 100 milliohm shunt is source evidence only, not a bench result.
Pi power should be V*A only for valid channels with the same electrical_sequence
and pair timestamp; never combine separate text readings. Shunt and bus ADC
conversions are sequential, not simultaneous. See [TI INA219 datasheet, sections
8.3 and 8.6](https://www.ti.com/lit/ds/symlink/ina219.pdf).

Encoder counting is x1: rising edges on PA6/A only; PC7/B determines signed delta.
B is an input, not another edge interrupt. CPR means A rising edges per encoder-
shaft revolution. The reported shaft has `gear_num/gear_den` encoder revolutions
per reported-shaft revolution. RPM = signed_delta*60000*gear_den /
(CPR*elapsed_ms*gear_num). ADS_ENCODER_FORWARD_SIGN must be measured so positive
RPM means the agreed FORWARD rotation. The old literal 400 is not adopted as a
calibration. Zero delta is valid stationary RPM, not proof of a healthy encoder.
Telemetry reports encoder_direction FORWARD/REVERSE/STATIONARY/UNKNOWN separately
from the fixed commanded direction. Pulse frequency, overflow and encoder-loss
behavior require bench checks; a stationary disconnected encoder cannot be
identified from zero counts alone.

DS18B20 uses PA10 open drain with verified external 3.3 V pullup and externally
powered, single-device wiring (Skip ROM); parasite power/multidrop are not
supported by this adapter. Conversion is scheduled without a 750 ms busy wait.
Presence, completion, scratchpad CRC, reserved bytes and temperature range are
checked; resolution-dependent undefined bits are masked. A real 0 C conversion
stays valid; absent/failed/incomplete/CRC-corrupt/stale conversions return
valid=false/value=null. Housing temperature requires verified physical mounting.
See [DS18B20 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf).

Each channel carries `timestamp_ms`, unit, value and valid. Temperature timestamps
are receipt/completion times for conversions spanning the preceding interval,
not instantaneous housing temperature. Metadata includes sample_sequence (cache
revision/attempt counter), electrical_sequence, electrical_started_ms,
electrical_completed_ms, encoder_started_ms/encoder_completed_ms,
temperature_started_ms/temperature_completed_ms, calibration flags,
encoder_direction and source.
Cache reads do not invent a new acquisition. Default invalid channels can have
zero timestamps; a valid timestamp of zero at boot is legal. Electrical/RPM
snapshots stale after 1500 ms; temperature after 3000 ms. Pi must exclude invalid
and uncalibrated channels and deduplicate acquisition sequence values.

To select a run: require the accepted START and confirmed start event; match
run_id and stop event; use unsigned tick differences for wrap, bounded below
2^31 ms. Keep only acquisition intervals fully within start/stop, particularly
electrical_started_ms >= run start and electrical_completed_ms < stop. Temperature
conversions or RPM averaging intervals crossing boundaries must be excluded using
their started/completed metadata. Never select
samples by Pi receipt time alone. Events and cached samples may arrive later.

## 5. Build, flash and USB-only acceptance

Build from the repository root on this development Mac:

```sh
.venv/bin/python -m unittest discover -s tests -q
make -C ADS -j4
```

`ADS/Makefile` defaults to the installed GNU Tools for STM32 14.3.rel1 path.
On another machine, use `make -C ADS TOOLCHAIN=/path/to/toolchain/bin`; if its
bin directory is on PATH, use `make -C ADS TOOLCHAIN=`. The makefile has **no flash
or clean target**. It compiles tracked sources into `build/stm32-default-disabled/`,
leaving the old ignored `ADS/Debug/ADS.elf` untouched. Only the newly built ELF is
the artifact for this change. Both linker scripts and the .ioc stack reservation
are increased to 8 KiB for bounded JSON formatting and interrupt headroom.

Flash manually only after isolating motor energy:

1. Disconnect the external 12 V motor supply physically; isolate the motor and
   relay contacts. USB alone must not backfeed the driver/load. Verify absence
   of motor energy. Preserve the working project and its binary before changing
   the board. The old project automatically starts PWM after reset if powered.
2. In STM32CubeIDE use a separate workspace to avoid the two identically named
   ADS projects. Import `.../Documents/ChatGPT/Capstone/ADS` as the existing project,
   not `/Users/markussanford/ADS`. Confirm NUCLEO-F401RE / STM32F401RET6 target.
3. For CubeIDE managed builds, refresh the project and verify that ads_test.c,
   ads_acquisition.c, ads_sensors.c, ads_motor.c and the added HAL I2C files are
   included. Rebuild only this project. Alternatively build with the makefile
   above and select its exact ELF explicitly for download.
4. Before Download/Run/Debug verify the selected ELF path; old launch files say
   `Debug/ADS.elf` and are not automatically updated to the makefile artifact.
   Use CubeProgrammer's GUI to select `build/stm32-default-disabled/ADS.elf`, or
   explicitly select that image in CubeIDE's load-image configuration. Do not
   select the other project's ELF. Keep every acceptance gate at its default.
5. Connect ST-LINK USB, select the actual probe and program/verify that exact
   image. This is a manual operator action, not performed by this delivery.
6. Do not regenerate .ioc and assume it contains accepted motor/sensor wiring:
   the gated peripheral setup is explicit user code. Regeneration needs review
   of IRQ handlers, user code, HAL module includes and the new source list.

USB-only protocol acceptance on the Pi (one serial owner):

```sh
cd /home/amirzoom8/intelligent-diagnostic-system/dashboard/Dashboard-trace-x-integration-2026-10-30
systemctl --user stop trace-x.service
# Also stop any manually running backend, miniterm or recorder with Ctrl+C.
.venv-pi/bin/python -m pip install -r requirements-backend.txt
.venv-pi/bin/python -m diagnostic_platform.verify_stm32 \
  --port /dev/ttyACM0 --baud 115200 --protocol json
```

Use the actual `/dev/serial/by-id/...` path where available. Default passive/auto
verification will time out because this firmware replies to requests rather
than broadcasting legacy sensor text. JSON verification sends only status,
capabilities, faults and heartbeat; it does not arm/start outputs. Expect firmware
`0.3.0-bounded-test-default-disabled`, hardware_control=false, state DISARMED,
fixed_pwm_percent=0 and max_duration_ms=0 in capabilities. A silence-only or
identity mismatch fails acceptance; do not flash again blindly.

With power still isolated, a reviewed serial test client may additionally send
ARM_TEST/SET_PWM/START_TEST examples from section 3; expect rejection, zero
applied PWM and no start event. Repeated STOP_TEST must acknowledge without
clearing a fault or producing an output pulse. READ_MEASUREMENTS must return
invalid/null motor channels in the default wiring-disabled build; receiving
JSON does not validate sensors. Confirm actual PB10 waveform, PB5 contact/reset
behavior and unchanged PB4 using instruments. Serial responses alone cannot
establish those physical properties.

To test live acquisition later, first verify sensor wiring, then use a separate
reviewed sensor-only configuration with **ADS_PHYSICAL_OUTPUT_ENABLED=0**.
Confirm INA219 #1 mapping and shunt against references, CPR/gearing/sign using an
independent speed/count reference, and DS18B20 including a valid 0 C conversion
and sensor-removal behavior. No sensor gate changes are made by this delivery.

Before any later output-enabled build, complete MOTOR_RELAY_BENCH_TEST.md, supply
a reviewed ISR-safe interlock hook and approve a fixed duty, direction, run bound,
current and temperature limits. With motor energy disconnected, test scope/load
behavior for normal completion, repeated cancellation, interlock loss, missing
heartbeat, UART disconnect/overflow, reset and fault paths; measure contact
opening and discharge, not just GPIO. Physically demonstrate that late heartbeat,
reconnect, restored sensor or released kill switch cannot restart output without
explicit rearm. Only then separately authorize a supervised powered test. A fake
register test or syntax build is not bench acceptance.

## 6. Pi runner integration still required

`diagnostic_platform/stm32.py` now preserves command arguments (previously they
were discarded), understands event envelopes, queues up to 128 observed events
and correlates replies. `drain_events()` drains events already seen during
request exchanges; it is not a background serial consumer. The adapter's
allow_motor_control default remains false. No environment variable enables it.
The simulation adapter does not advertise ARM_TEST support.

The existing dashboard motor controls and diagnostic-run WebSocket remain
simulation paths. **There is no configuration-only way to start a physical
bounded test from the dashboard yet.** Layout/controls were preserved; the Pi
runner implementation is a separately required integration after bench
acceptance, not an implied completed feature.

The required runner must:

- Own the serial port exclusively and replace/cooperate with the passive
  LiveMonitor reader; never open a second competing reader.
- Discover capabilities/identity, calibration, interlocks and limits; seed the
  monotonic command sequence above last_control_seq. Do not silently downgrade
  to legacy text or arm after reconnect.
- Obtain explicit operator arm intent after acceptance, send fresh heartbeats
  about every 500 ms on a deadline-aware serial owner, and check accepted=false
  even on ACK envelopes. Configure exactly the approved fixed PWM and duration.
- Wait for accepted START plus MOTOR_START, retain run_id/start time, poll
  READ_MEASUREMENTS at a bounded rate and continue processing unsolicited events.
  Monitor sample freshness/validity, faults and missing replies. No concurrent
  long serial operation may starve heartbeats beyond 2 s.
- Stop/cancel via STOP_TEST through a finally path; await correlated ACK and stop
  event/status, verify zero applied PWM. Missing ACK is a fault, never proof of
  stop. The MCU bound/watchdog and independent physical disconnect remain the
  fallback, not a promise from Python cleanup.
- Select only valid, calibrated acquisition intervals within the confirmed run;
  compute power from the matching electrical pair. Save raw envelopes, run IDs,
  sequences, calibration/build identities and start/stop/fault evidence into the
  experiment store. Existing passive live display is volatile, not a recorder.
- Feed measurements and real command state into existing dashboard components
  while retaining an explicit hardware source label and separate simulation.
  Do not infer health/stall from zero RPM without commanded state and matched
  operating-condition baselines. No ML or calibrated health score is added here.

Current dashboard preview remains available with its previous simulation setup:

```sh
ADS_MODE=simulation ADS_SERVE_DASHBOARD=1 ADS_LIVE_SERIAL_PORT= \
  .venv-pi/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 13115 --workers 1
```

Open http://127.0.0.1:13115/ on the Pi. This does not run a physical test. Do not
set ADS_MODE=hardware: the runtime adapter remains intentionally gated. A passive
reader alone will not display request-only JSON acquisition; the future single-
owner runner must publish those responses to the live monitor.

## 7. Observed verification results

Final software checks on November 6, 2026:

- `.venv/bin/python -m unittest discover -s tests -q`: **126 tests passed**, 6.448 s,
  no skips/failures. Includes the existing C protocol and motor-safety harnesses,
  new bounded-state/acquisition harness, fake-register output tests with both
  relay polarities, Python request arguments/events/correlation tests, and ARM
  syntax checking of gated source branches against actual STM32 headers.
- `make -C ADS -j4`: **successful NUCLEO-F401RE target compile/link**, GNU ARM GCC
  14.3.rel1; Cortex-M4, hard-float FPv4-SP-D16. Tracked application sources use
  -Wall -Wextra -Werror. ST vendor HAL sources additionally suppress existing
  unused-parameter warnings; no vendor driver implementation was edited.
- ELF size: text 21,200 bytes; data 92; BSS 11,996 (including linker reservations);
  total reported 33,288. Stack reservation 8 KiB. Real worst-case stack depth,
  serial throughput, timing/latency and electrical behavior remain bench work.
- Gated branches were syntax-checked only with synthetic flags; **no output-enabled
  firmware image was linked**. Fake GPIO/timer tests do not use a board.
- `git -c core.whitespace=cr-at-eol diff --check`: passed. Existing Cube-generated
  CRLF line endings were retained. No frontend file differs from baseline.

Firmware artifact (local, Git-ignored): `build/stm32-default-disabled/ADS.elf`.

SHA-256: `1c1f01d8fe9e27c315c5c6a90cba4af639a03f9d8be3d1636dc36e07d1b279a7`. Matching checksum file is alongside the ELF.

**Not verified:** actual installed firmware; Pi serial behavior for this new
image; INA219 calibration; encoder CPR/gearing/direction; DS18B20 wiring/mounting;
relay polarity/reset/contact behavior; physical interlock/kill switch implementation;
actual shutdown on communication loss; motor movement; powered motor tests;
physical dashboard runner. These are explicitly not covered by passing tests.
No device was flashed/reset, no motor energized, no Git commit or push made.
The original `/Users/markussanford/ADS` motor-test project and old binary remain
unchanged. The old `deliverables/Trace-X-Pi.zip` was **not rebuilt** for this
firmware-only delivery; do not use that archive as the source for this update.

## 8. Modified and created files

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
- `diagnostic_platform/protocol.py`
- `diagnostic_platform/stm32.py`
- `docs/BOUNDED_STM32_MOTOR_TEST.md`
- `docs/MOTOR_RELAY_BENCH_TEST.md`
- `docs/STM32_INTEGRATION_PLAN.md`
- `docs/STM32_INTEGRATION_STATUS.md`
- `tests/bounded_motor_harness.c`
- `tests/bounded_output_harness.c`
- `tests/hal_stub/stm32f4xx_hal.h`
- `tests/test_bounded_motor.py`
- `tests/test_firmware_protocol.py`
- `tests/test_motor_safety.py`
- `tests/test_stm32.py`
