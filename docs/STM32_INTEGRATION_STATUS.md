# Trace-X integration status

November 6 update: see [bounded firmware delivery](BOUNDED_STM32_MOTOR_TEST.md)
for the new default-disabled command state machine, acquisition adapters and
remaining physical acceptance gates. Earlier implementation-stage descriptions
below are historical and do not establish current bench verification.

This change extends the existing ADS STM32CubeIDE project. USART2 remains
115200 8N1 on PA2/PA3. No PWM start or motor activation exists in the checked-in
main.c. The motor stop interface now configures PB10 at zero duty and gates
PB5 drive on verified relay configuration. No alternate project is used.

## Verified signal mapping and remaining hardware blockers

User-supplied wiring: PB5 controls the relay switching DC geared-motor power,
PB10 is TIM2 Channel 3 to the MD10C PWM input and PA8 is direction. PB4 is
the separate circuit-testing relay and is not altered by motor shutdown. The pin map is recorded in
main.h user-code definitions. PA8 remains untouched; no direction/start API or
PWM timer is enabled. ADS.ioc still describes the original Cube-generated
peripherals; motor pad handling is explicit user code, not a generated timer
configuration. Both CubeIDE configurations include the Core source tree and
therefore the added Core/Src/ads_motor.c.

The motor power path is confirmed at wiring-design level: 12 V positive → relay
COM → NO → MD10C positive motor-supply input, with 12 V negative connected to
the MD10C negative motor-supply input. Physical contact opening and supply
interruption remain to be measured. Trigger-jumper setting, HIGH/LOW input
activation, logic compatibility and reset-safe output behavior are unverified.

The default build leaves PB5 as input with GPIO_NOPULL and never writes its
output latch. Undriven is an unverified state, not proof of disconnection. A
verified external circuit must maintain power disconnection during reset,
brownout, an unpowered MCU and failures that prevent code execution.

ADS_RELAY_ACTIVE_LEVEL and ADS_RELAY_INACTIVE_LEVEL are initially -1 (unknown).
The inactive level must complement the verified active level; the earlier
ADS_RELAY_DISCONNECT_LEVEL name must agree with inactive. PB5 output drive
requires all three independent flags: ADS_RELAY_POLARITY_VERIFIED,
ADS_RELAY_POWER_PATH_VERIFIED and ADS_RELAY_SAFE_OUTPUT_VERIFIED. All default to
0. Design-level confirmation of NO/COM wiring does not set any of these physical
acceptance flags. Contradictory verified levels fail to compile. No configuration
flag enables remote motor commands.

Follow [the manual relay bench procedure](MOTOR_RELAY_BENCH_TEST.md) to record
GPIO waveforms, reset behavior, contact opening and actual motor-supply voltage.
No flash or powered test is performed by this change.

There are still no INA219, DS18B20 or encoder acquisition implementations or
configuration. Supply the actual routines, INA219 shunt/calibration, encoder
counts per output revolution and one-wire wiring to finish acquisition.

## Single stop interface and shutdown plan

ADS_Motor_Stop is the only hardware stop interface. It disables TIM2 CH3 output,
disables TIM2 counting and clears CCR3 before preloading PB10 low and configuring
it as GPIO output. PWM is never started. With all relay acceptance flags set,
it preloads PB5 inactive before selecting output mode; otherwise PB5 remains
undriven. This is a stop request, not physical confirmation of disconnected power.

ADS_Motor_Init requests stop immediately after HAL_Init, before clock/UART setup.
Protocol callback registration requests stop again. STOP_MOTOR/STOP_TEST attempt
shutdown but retain CONTROL_DISABLED responses because no motor-control command
is enabled. Other motor commands remain disabled without activating any output.
Error_Handler and NMI/HardFault/MemManage/BusFault/UsageFault call ADS_Motor_Fault,
which latches shutdown and uses the same stop interface.

The motor layer has its own 2000 ms communication watchdog, initialized at motor
startup and polled from SysTick as well as the main loop. A structurally valid
ADS heartbeat invokes ADS_Motor_Heartbeat; sensor/status requests, malformed
frames and motor commands do not refresh this motor deadline. A heartbeat first
checks the previous deadline, so one arriving at or after 2000 ms cannot conceal
a timeout. Unsigned tick subtraction handles wraparound. A fault/timeout latch
is never cleared by heartbeat, Stop or reinitialization; only MCU reset clears
static storage, and startup after reset requests stop again. There is no rearm
or motor-start interface. The protocol's existing timeout state remains latched
as well. This is a software communication watchdog, not independent hardware
protection: a stalled CPU, disabled interrupts or relay hardware failure can
prevent shutdown. Fault-handler shutdown is best effort.

Complete electrical acceptance before enabling future control: check startup and
reset disconnection, normal stop, heartbeat loss at 2 seconds, repeated stops,
fault shutdown and recovery without automatic restart. Leave motor energy
isolated until the physical stop path and reset defaults have been established.

## Firmware interfaces

ADS_Protocol_SetHardwareCallbacks registers acquisition and stop callbacks using
the protocol callback context. Registration calls stop immediately. The stop
callback is bound in main.c to ADS_Motor_Stop; acquisition remains unbound.
ADS_Protocol_SetHeartbeatCallback connects accepted ADS heartbeats to the motor
watchdog. The existing protocol timeout also invokes stop at >=2000 ms without
heartbeat. main.c polls protocol every serial iteration; SysTick enforces the
motor watchdog independently of serial processing. Future acquisition must
remain nonblocking and publish cached timestamped snapshots.

READ_MEASUREMENTS is implemented. Its measurement response payload.result has a
measurements object with voltage (V), current (A), power (W), temperature (degC)
and rpm (rpm). Each channel contains value, unit, valid and timestamp_ms (MCU
monotonic acquisition tick, not UTC). Invalid channels have value:null. Unbound
acquisition returns all channels invalid with timestamp 0 (never acquired).
Adapters supply signed milli-units and must reject stale data, CRC failures,
INA219 overflow/calibration failure and invalid encoder configuration. A stopped
encoder's zero RPM is valid only with a functioning, configured acquisition.

Capabilities advertises READ_MEASUREMENTS but measurement_types stays empty
until physical sensor acquisition is actually bound. Hardware control is false.
Frames are newline-delimited JSON; receive limit is 512 bytes, responses fit the
4096-byte backend limit. The command parser deliberately accepts an ASCII subset
(no escaped strings or fractional request numbers); it rejects duplicate keys,
trailing content, malformed containers and misplaced command fields. Commands
require a payload command string and arguments object. Epoch millisecond request
timestamps are accepted; STM32 response timestamps are uint32 MCU ticks.

## Raspberry Pi and dashboard

The existing STM32SerialConnection requests ADS v1 measurements. The existing
LiveMonitor now consumes the channel schema, validates units/validity/timestamps
and clears failed channels instead of retaining an earlier reading. Existing
snapshot/API wiring remains usable by the Trace-X dashboard. Live monitoring is
passive; this request/response firmware emits measurements only when requested.

Run the recorder with motor power isolated until startup behavior is verified:

```
python -m diagnostic_platform.collector --port /dev/serial/by-id/DEVICE --test-id bench-001 --directory data/experiments
```

It sends heartbeat and READ_MEASUREMENTS only, records one row per sensor with
UTC receipt time, MCU acquisition tick, test ID, units and validity, flushes each
snapshot and creates a unique exclusive CSV per invocation. It never overwrites
an earlier experiment. Stop with Ctrl+C. Use a single process to own the serial
port; do not run the passive dashboard serial reader on the same port as the
recorder. A future shared serial service can feed both consumers. The dashboard
consumer interface is LiveMonitor.feed(serial_frame); no second serial reader is
needed when integrating that service.

## Verification

Host tests exercise protocol compatibility, malformed/oversize frame recovery,
startup state, exact timeout stop callback, normal and repeated stop requests,
latched timeout after heartbeat/start attempts, fault recovery into a stopped
state, motor watchdog enforcement without protocol polling, tick wraparound,
late-heartbeat rejection, TIM2 CH3 disable/CCR3 zeroing, GPIO preloading order,
all relay verification gates and both relay disconnect polarities using a HAL
test double, signed fixed-point serialization,
missing channels, recording isolation and dashboard invalidation. They do not
verify electrical outputs, physical sensors, STM32 flashing or Pi hardware.
