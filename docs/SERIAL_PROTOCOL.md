# Raspberry Pi–STM32 Serial Protocol

Current November 6 integration: see [full automated integration](FULL_AUTOMATED_INTEGRATION.md)
for the current engine, CRC32 firmware, deployment and acceptance status.
Implementation-stage statements and earlier test counts below are historical.

## Current compatibility

The repository firmware now implements a communication-only subset of this
protocol. Status, capabilities, faults, heartbeat, correlation, and error frames
are compatible with the Python backend and tested on the host. Measurement and
motor commands return explicit errors; the firmware has been compiled but not
flashed or tested on a physical Nucleo board.

## Physical serial settings

| Setting | Value |
|---|---|
| Link | Nucleo ST-LINK virtual COM to STM32 USART2 |
| STM32 pins | PA2 TX, PA3 RX |
| Baud | 115200 |
| Data/parity/stop | 8-N-1 |
| Flow control | None |
| Pi default device | `/dev/ttyACM0` — must be confirmed |
| Frame boundary | One UTF-8 JSON object followed by `\n` |
| Backend maximum frame | 4096 bytes |
| Current firmware receive limit | 512 bytes; sufficient for defined requests |
| Protocol version | 1 |
| Default read timeout | 0.25 seconds |
| Default command timeout | 1.5 seconds |

## Envelope

```json
{
  "version": 1,
  "type": "command",
  "seq": 18,
  "device_id": "raspberry-pi",
  "timestamp_ms": 1792000000000,
  "payload": {}
}
```

Required fields are version, type, sequence, device ID, nonnegative timestamp in milliseconds, and an object payload. Oversized, malformed, incomplete, incorrectly typed, or unsupported-version frames are rejected.

The Raspberry Pi currently sends Unix epoch milliseconds. The STM32 has no
real-time clock synchronization and therefore responds with `HAL_GetTick()`
milliseconds since boot. Correlation must use `payload.reply_to`, not timestamps;
firmware timestamps are suitable only for relative timing until a time-sync
design is added.

## Message types

- `hello`
- `status`
- `capabilities`
- `measurement`
- `command`
- `ack`
- `error`
- `heartbeat`

## Commands

| Command | Intended response | Current firmware support |
|---|---|---|
| `GET_STATUS` | `status` with safe state and zero output | Implemented, unverified on hardware |
| `GET_CAPABILITIES` | supported firmware functions | Implemented, unverified on hardware |
| `READ_MEASUREMENTS` | `MEASUREMENTS_UNAVAILABLE` error | ADC/sensors unconfigured |
| `START_TEST` | `CONTROL_DISABLED` error | Motor control disabled |
| `STOP_TEST` | `CONTROL_DISABLED` error | Motor control disabled |
| `SET_PWM` | `CONTROL_DISABLED` error | PWM unconfigured |
| `SET_DIRECTION` | `CONTROL_DISABLED` error | Direction pin unconfigured |
| `STOP_MOTOR` | `CONTROL_DISABLED` error | No motor output exists |
| `GET_FAULTS` | `ack` with empty faults and safe state | Implemented, unverified on hardware |

## Example command

```json
{"version":1,"type":"command","seq":18,"device_id":"raspberry-pi","timestamp_ms":1792000000000,"payload":{"command":"GET_STATUS","arguments":{}}}
```

## Example acknowledgment

```json
{"version":1,"type":"ack","seq":44,"device_id":"STM32-ADS","timestamp_ms":1792000000010,"payload":{"reply_to":18,"result":{"state":"READY","faults":[]}}}
```

## Example error

```json
{"version":1,"type":"error","seq":45,"device_id":"STM32-ADS","timestamp_ms":1792000000011,"payload":{"reply_to":19,"code":"INVALID_STATE","message":"Motor is not armed"}}
```

## Response correlation and stale data

Every request uses a monotonically increasing sequence number. Responses identify the request with `payload.reply_to`. The backend ignores responses for a different request and ignores messages from a different device ID. If no matching response arrives by the command deadline, it raises a communication timeout.

The backend and communication-only firmware implement a versioned `heartbeat`
request using the same sequence/reply correlation. The firmware acknowledgment
reports `alive:true`, `SAFE_IDLE`, and `hardware_control:false`.

## Current firmware safety behavior

- The protocol uses fixed buffers and no dynamic allocation.
- Receive frames exceeding 512 bytes are discarded through the next newline and
  receive `FRAME_TOO_LARGE`.
- Missing fields, unsupported versions/types/commands, unavailable measurements,
  and disabled controls receive correlated error frames.
- A valid request refreshes the communication timer. After 2000 ms without one,
  the internal state becomes `COMMUNICATION_TIMEOUT`.
- No GPIO, timer, PWM, ADC, motor direction, or actuator code is present in the
  protocol module. The timeout state therefore cannot yet be considered a
  physically verified motor-stop mechanism.

## Error handling

- Device `error` messages become explicit backend exceptions containing code and message.
- Invalid JSON, types, versions, frame sizes, or response bodies become protocol errors.
- An empty read is retried only until the bounded deadline.
- Motor-control commands are rejected locally before any serial write unless control is explicitly enabled in code after verification.

## Safe disconnect

The current release never enables physical motor control. When future verified control is enabled, disconnect first sends `STOP_MOTOR` and requires an acknowledgment. The serial port is closed even if acknowledgment fails, but the backend raises `SafeDisconnectError` so the loss of confirmed safe state cannot be hidden. Reconnection must begin stopped and unarmed; it must never restore the preceding PWM value.

## Simulation adapter

`SimulatedSTM32Connection` implements status, capabilities, measurements, supported commands, faults, and stop-on-disconnect without a serial port. Simulated RPM is intentionally `null` because no RPM sensor is configured in the real firmware/hardware evidence.
