# Hardware mapping

Source: `Adaptive Diagnosis System.fzz`, inspected September 12, 2026.

This document distinguishes connections confirmed by the Fritzing project from
values that must be verified on the physical prototype. Do not energize the
system based only on this document; review the electrical design and component
datasheets first.

## Confirmed components

| Function | Fritzing part/title | Software role |
|---|---|---|
| Host computer | Raspberry Pi 5 | UI, storage, reports, diagnostic engine |
| Real-time controller | Generic `STM32_Nucleo_board` | Sampling, control, safety |
| Motor | 3–12 V DC motor | First diagnostic target |
| Motor control | Cytron MD10C R2 | PWM and direction control |
| Motor monitoring | INA219 — MOTOR | Motor bus voltage/current/power |
| Circuit monitoring | INA219 — Circuit | External-circuit voltage/current/power |
| Temperature | DS18B20 probe | Motor temperature |
| Switching | Two-relay module | Test-path switching/isolation |
| Input power | 12 V, 5 A bench supply | Main supply |
| Conversion | XL4015 CC/CV module | Regulated auxiliary/test supply |
| Distribution | FRC-style power distribution board | Fused branch distribution |
| Voltage probe | 30 kΩ / 10 kΩ divider | Scales probe voltage to 25% |
| Probe protection | BAT54S Schottky clamps, 100 nF capacitor | ADC input protection/filtering |
| Temperature pull-up | 4.7 kΩ resistor | DS18B20 one-wire pull-up |
| Safety | Main, motor, and circuit fuses; kill switch | Hardware protection/shutdown |

## Confirmed STM32 signal groups

The Fritzing netlist and the installed Nucleo part definition identify the
following intended Arduino-header connections. STM32 pin translations are from
ST UM1724 for NUCLEO-F401RE. These are **design mappings**, not evidence that the
physical wiring or CubeIDE peripheral configuration has been verified.

| Intended function | Nucleo header | STM32 pin/function | Current `.ioc` status |
|---|---|---|---|
| MD10C PWM | D6 | PB10 / TIM2_CH3 | Not configured |
| MD10C direction | D7 | PA8 / GPIO | Not configured |
| Relay input 1 | D4 | PB5 / GPIO | Not configured |
| Relay input 2 | D5 | PB4 / TIM3_CH1 or GPIO | Not configured |
| DS18B20 data | D2 | PA10 / GPIO | Not configured |
| Protected voltage probe | A0 | PA0 / ADC1_IN0 | Not configured |
| INA219 SDA | A4/SDA | PC1 or PB9 depending solder bridges | Not configured |
| INA219 SCL | A5/SCL | PC0 or PB8 depending solder bridges | Not configured |
| Sensor supply | 3V3 | 3.3 V rail | Physical verification required |
| Common reference | GND | Ground | Physical verification required |

The MD10C custom part has unnamed connector metadata, but its breadboard graphic
aligns the D6 connection with `PWM` and the D7 connection with `DIR`. Confirm
those terminal labels on the actual MD10C before connection.

## Important software implications

- Both INA219 boards can share I2C only if they have different addresses.
- The DS18B20 requires a one-wire GPIO and the shown 4.7 kΩ pull-up.
- The motor driver requires distinct PWM and direction outputs.
- Relay outputs may be active-low; startup firmware must default them to the
  electrically safe state.
- A 30 kΩ/10 kΩ divider gives a ratio of 0.25. With a 3.3 V ADC this corresponds
  to an ideal 13.2 V full-scale input before tolerances and clamp headroom.
- RPM and vibration measurements exist in the software model but no RPM or
  vibration sensor is present in this Fritzing file. They must remain optional
  until those sensors are added.
- The Raspberry Pi 5 is present in the drawing but has no wired data connection
  in the Fritzing netlist. USB serial remains the proposed Pi–STM32 link, not a
  connection confirmed by this file.

## Information still required before firmware pin definitions

1. Confirm the physical board is NUCLEO-F401RE / STM32F401RET6.
2. Inspect A4/A5 solder bridges to determine whether I2C reaches PB9/PB8.
3. Confirm MD10C PWM/DIR terminal labels, logic levels, and common ground.
4. Confirm INA219 I2C addresses and which controller reads them.
5. Confirm relay channel purpose and whether each input is active-low.
6. Record fuse current ratings and physical kill-switch behavior.
7. Confirm ADC reference, divider values, clamp orientation, and safe probe limit.
8. Confirm the Raspberry Pi USB serial device path and permissions.

## Proposed Pi–STM32 measurement frame

The firmware should publish newline-delimited JSON initially:

```json
{"type":"measurement","seq":1,"time_ms":1250,"motor_voltage_v":11.92,"motor_current_a":0.84,"circuit_voltage_v":5.01,"circuit_current_a":0.12,"temperature_c":36.5,"pwm_percent":65.0,"direction":"forward","relay_mask":0,"faults":[]}
```

RPM and vibration fields should be omitted or set to `null` until the associated
hardware exists. Commands should use separate messages with sequence numbers and
acknowledgements; motor-enable commands must be rejected when a hardware safety
fault is active.
