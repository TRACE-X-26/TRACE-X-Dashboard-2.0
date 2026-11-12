from __future__ import annotations

import argparse
import json
import math
import time
from glob import glob
from typing import Callable

from .protocol import CommandName
from .stm32 import STM32SerialConnection
from .live import LiveMonitor
from .text_telemetry import SerialLineDecoder


def discover_serial_port() -> str:
    """Return the most stable available STM32 serial path."""
    candidates = [
        *sorted(glob("/dev/serial/by-id/*STMicroelectronics*")),
        *sorted(glob("/dev/serial/by-id/*STLink*")),
        *sorted(glob("/dev/ttyACM*")),
        *sorted(glob("/dev/cu.usbmodem*")),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            return candidate
    raise FileNotFoundError(
        "No STM32 serial port found. Connect the Nucleo ST-LINK USB port and "
        "check /dev/ttyACM* or /dev/serial/by-id/."
    )


def verify_connection(
    port: str,
    baud: int = 115200,
    *,
    connection_factory: Callable[..., STM32SerialConnection] = STM32SerialConnection,
    require_crc: bool = False,
) -> dict:
    """Explicit JSON request/response checks, retained for API compatibility."""
    crc_options={'require_crc':True} if require_crc else {}
    connection = connection_factory(
        **crc_options,
        port=port,
        baud=baud,
        command_timeout=3.0,
        allow_motor_control=False,
    )
    connection.connect()
    try:
        status = connection.status()
        capabilities = connection.capabilities()
        faults = connection.execute(CommandName.GET_FAULTS.value)
        heartbeat = connection.heartbeat()
    finally:
        connection.disconnect()

    if status.get("hardware_control") is not False:
        raise RuntimeError("STM32 did not report hardware control as disabled")
    if heartbeat.get("alive") is not True:
        raise RuntimeError("STM32 heartbeat did not report alive")

    return {
        "port": port,
        "baud": baud,
        "device_id": capabilities.device_id,
        "firmware_version": capabilities.firmware_version,
        "state": status.get("state"),
        "faults": faults.get("faults", status.get("faults", [])),
        "heartbeat_alive": heartbeat.get("alive"),
        "hardware_control": status.get("hardware_control"),
        "commands": list(capabilities.commands),
        "format": "ads_json_v1",
    }


def verify_telemetry(port: str, baud: int = 115200, *, timeout: float = 6,
                     protocol: str = 'auto', transport_factory=None, clock=time.monotonic) -> dict:
    """Passively recognize complete text cycles or valid unsolicited JSON.

    Never writes serial bytes. Silence is not permission to send commands.
    Request/response firmware can be checked explicitly with --protocol json.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Timeout must be a finite positive number')
    if protocol not in {'auto', 'plain-text'}:
        raise ValueError('Passive protocol must be auto or plain-text')
    monitor = LiveMonitor()
    decoder = SerialLineDecoder()
    transport = (transport_factory or LiveMonitor._open_serial)(port, baud)
    monitor._connected = True  # A real transport is open; no simulation adapter is used.
    deadline = clock() + timeout
    warnings = set()
    recognized_text = False
    try:
        while clock() < deadline:
            chunk = transport.read(256)
            lines, errors = decoder.feed(chunk)
            if errors:
                decoder.reset()
                monitor._text_motor.reset()
                warnings.update(errors)
                continue
            for line in lines:
                if line.lstrip().startswith('{') and protocol == 'plain-text':
                    continue
                if line.lstrip().startswith('{'):
                    # Validate protocol JSON rather than treating arbitrary JSON as a device handshake.
                    from .protocol import decode_message, MessageType
                    try:
                        message = decode_message(line)
                        if message.device_id != 'STM32-ADS':
                            continue
                        if message.message_type not in {MessageType.MEASUREMENT, MessageType.STATUS, MessageType.CAPABILITIES, MessageType.HELLO}:
                            continue
                        monitor.feed(line)
                        warnings.update(monitor.snapshot()['warnings'])
                        if 'INVALID_JSON_FRAME' in monitor.snapshot()['warnings']:
                            continue
                        return {'port': port, 'baud': baud, 'format': 'ads_json_v1',
                                'source': 'stm32_serial', 'hardware_connected': True,
                                'device_id': message.device_id, 'message_type': message.message_type.value,
                                'motor_sample': monitor.snapshot()['motor_sample'],
                                'read_only': True, 'commands_sent': False, 'hardware_control': False,
                                'hardware_safety_verified': False, 'warnings': sorted(warnings)}
                    except ValueError:
                        warnings.add('INVALID_JSON_FRAME')
                        continue
                monitor.feed(line)
                state = monitor.snapshot()
                recognized_text |= state['motor_format'] == 'plain_text'
                warnings.update(state['warnings'])
                if state['motor_sample'] is not None:
                    sample = {**state['motor_sample'], 'hardware_connected': True, 'stale': False}
                    return {'port': port, 'baud': baud, 'format': 'plain_text', 'source': 'stm32_serial',
                            'hardware_connected': True, 'motor_sample': sample,
                            'read_only': True, 'commands_sent': False, 'hardware_control': False,
                            'hardware_safety_verified': False, 'warnings': sorted(warnings)}
    finally:
        transport.close()
    if recognized_text:
        missing = ', '.join(monitor.snapshot()['pending_motor_fields'])
        detail = ', '.join(sorted(warnings)) or 'none'
        raise TimeoutError(f'Plain-text STM32 telemetry detected but no complete valid cycle within {timeout:g}s. Missing fields: {missing}. Warnings: {detail}. Check sensor status; no commands were sent.')
    raise TimeoutError(f'No compatible passive telemetry within {timeout:g}s. Close other serial readers and check wiring/baud. For request/response JSON firmware use --protocol json. No commands were sent.')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely verify Raspberry Pi USB serial communication with STM32."
    )
    parser.add_argument(
        "--port",
        help="Serial device path. If omitted, the tester searches by-id and ttyACM paths.",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--crc32", action="store_true", help="Require protected ADS v1 frames for current firmware")
    parser.add_argument('--protocol', choices=('auto', 'plain-text', 'json'), default='auto',
                        help='Default auto passively detects text/streamed JSON. json explicitly sends status/capability/fault/heartbeat checks.')
    parser.add_argument('--timeout', type=float, default=6, help='Passive detection timeout in seconds (default 6).')
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        port = args.port or discover_serial_port()
        result = verify_connection(port, args.baud, require_crc=args.crc32) if args.protocol == 'json' else verify_telemetry(
            port, args.baud, timeout=args.timeout, protocol=args.protocol)
    except Exception as exc:
        print("STM32 CONNECTION TEST: FAILED")
        print(f"Reason: {exc}")
        print("Check the USB cable, serial port, plugdev/dialout membership, and close other serial programs.")
        return 1

    print("STM32 CONNECTION TEST: PASSED")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
