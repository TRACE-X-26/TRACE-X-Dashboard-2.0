from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from .control import SimulatedMotorController
from .drivers import DeviceCapabilities
from .protocol import (
    CommandName,
    MessageType,
    ProtocolError,
    ProtocolMessage,
    command_message,
    decode_message,
    encode_message,
    unprotect_frame,
)


class CommunicationTimeout(TimeoutError):
    pass


class DeviceResponseError(RuntimeError):
    pass


class HardwareControlDisabled(PermissionError):
    pass


class SafeDisconnectError(RuntimeError):
    pass


class SerialTransport(Protocol):
    def write(self, data: bytes) -> int: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...


class PySerialTransport:
    """Small adapter around pyserial, imported only when hardware is requested."""

    def __init__(self, port: str, baud: int, read_timeout: float) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for the physical STM32 adapter"
            ) from exc
        self._serial = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=read_timeout,
            write_timeout=read_timeout,
            exclusive=True,
        )
        # Kernel exclusivity also blocks non-cooperating later opens on Linux/macOS.
        try:
            import fcntl
            import termios
            fcntl.ioctl(self._serial.fileno(), termios.TIOCEXCL)
        except Exception:
            self._serial.close()
            raise

    def write(self, data: bytes) -> int:
        return int(self._serial.write(data))

    def readline(self) -> bytes:
        return bytes(self._serial.readline())

    def close(self) -> None:
        self._serial.close()


TransportFactory = Callable[[str, int, float], SerialTransport]


class STM32SerialConnection:
    """Synchronous request/response adapter for the target STM32 protocol.

    ADS v1 framing with request correlation and timestamped firmware events.
    Physical commands remain disabled by default. The explicitly opted-in
    automated runtime can authorize a connection for a bounded operator run;
    read-only probes never enable this gate. Firmware has independent gates.
    """

    CONTROL_COMMANDS = {
        CommandName.PREPARE_TEST_POWER,
        CommandName.ARM_CIRCUIT,
        CommandName.START_CIRCUIT,
        CommandName.STOP_CIRCUIT,
        CommandName.ARM_TEST,
        CommandName.CLEAR_FAULTS,
        CommandName.EMERGENCY_STOP,
        CommandName.START_TEST,
        CommandName.STOP_TEST,
        CommandName.SET_PWM,
        CommandName.SET_DIRECTION,
        CommandName.STOP_MOTOR,
    }

    def __init__(
        self,
        *,
        port: str,
        baud: int = 115200,
        read_timeout: float = 0.25,
        command_timeout: float = 1.5,
        device_id: str = "STM32-ADS",
        allow_motor_control: bool = False,
        require_crc: bool = False,
        transport_factory: TransportFactory = PySerialTransport,
    ) -> None:
        self.port = port
        self.baud = baud
        self.read_timeout = read_timeout
        self.command_timeout = command_timeout
        self.device_id = device_id
        self.allow_motor_control = allow_motor_control
        self.require_crc = require_crc
        self.transport_factory = transport_factory
        self._transport: SerialTransport | None = None
        self._sequence = 0
        self.last_timestamp_ms = 0
        self.last_response_frame = ""
        self._lock = threading.Lock()
        self._capabilities: DeviceCapabilities | None = None
        self._events: list[ProtocolMessage] = []

    def connect(self) -> None:
        with self._lock:
            if self._transport is not None:
                return
            self._transport = self.transport_factory(
                self.port, self.baud, self.read_timeout
            )

    def is_connected(self) -> bool:
        return self._transport is not None

    def status(self) -> dict:
        return self.execute(CommandName.GET_STATUS.value)

    def capabilities(self) -> DeviceCapabilities:
        response = self.execute(CommandName.GET_CAPABILITIES.value)
        capabilities = DeviceCapabilities(
            device_id=str(response.get("device_id", self.device_id)),
            measurement_types=tuple(response.get("measurement_types", ())),
            commands=tuple(response.get("commands", ())),
            firmware_version=response.get("firmware_version"),
        )
        self._capabilities = capabilities
        return capabilities

    def read_measurements(self) -> dict:
        return self.execute(CommandName.READ_MEASUREMENTS.value)

    def heartbeat(self) -> dict:
        with self._lock:
            if self._transport is None:
                raise ConnectionError("STM32 serial connection is not open")
            self._sequence += 1
            request = ProtocolMessage(
                MessageType.HEARTBEAT,
                self._sequence,
                "raspberry-pi",
                {},
                int(time.time() * 1000),
            )
            self._transport.write(encode_message(request, checksum=self.require_crc))
            return self._await_response(request.sequence)

    def probe_legacy_banner(self) -> str:
        """Read the current firmware's transmit-only connectivity banner."""
        with self._lock:
            if self._transport is None:
                raise ConnectionError("STM32 serial connection is not open")
            deadline = time.monotonic() + self.command_timeout
            while time.monotonic() < deadline:
                frame = self._transport.readline()
                if not frame:
                    continue
                try:
                    text = frame.decode("ascii").strip()
                except UnicodeDecodeError as exc:
                    raise ProtocolError("Legacy banner is not ASCII") from exc
                if text == "STM32 CONNECTED TO PI":
                    return text
                raise ProtocolError("Unexpected legacy firmware banner")
        raise CommunicationTimeout("Timed out waiting for the legacy STM32 banner")

    def execute(self, command: str, arguments: dict | None = None) -> dict:
        try:
            command_name = CommandName(command)
        except ValueError as exc:
            raise ValueError(f"Unsupported STM32 command: {command}") from exc
        if command_name in self.CONTROL_COMMANDS and not self.allow_motor_control:
            raise HardwareControlDisabled(
                "Physical motor control is disabled pending firmware and electrical safety verification"
            )
        with self._lock:
            if self._transport is None:
                raise ConnectionError("STM32 serial connection is not open")
            self._sequence += 1
            request = command_message(command_name, self._sequence, arguments=arguments)
            self._transport.write(encode_message(request, checksum=self.require_crc))
            return self._await_response(request.sequence)

    def seed_sequence(self, last_sequence: int) -> None:
        if type(last_sequence) is not int or not 0 <= last_sequence < 0xffffffff:
            raise ValueError('Invalid/exhausted MCU request sequence')
        with self._lock:
            self._sequence = max(self._sequence,last_sequence)

    def _await_response(self, request_sequence: int) -> dict:
        assert self._transport is not None
        deadline = time.monotonic() + self.command_timeout
        while time.monotonic() < deadline:
            frame = self._transport.readline()
            if not frame:
                continue
            message = decode_message(unprotect_frame(frame, required=self.require_crc))
            if message.device_id != self.device_id:
                continue
            self.last_timestamp_ms = message.timestamp_ms
            if message.message_type is MessageType.EVENT:
                self._events.append(message)
                self._events = self._events[-128:]
                continue
            reply_to = message.payload.get("reply_to")
            if type(reply_to) is not int or reply_to != request_sequence:
                continue
            if message.message_type is MessageType.ERROR:
                code = message.payload.get("code", "DEVICE_ERROR")
                detail = message.payload.get("message", "STM32 rejected the request")
                raise DeviceResponseError(f"{code}: {detail}")
            if message.message_type not in {
                MessageType.ACK,
                MessageType.STATUS,
                MessageType.CAPABILITIES,
                MessageType.MEASUREMENT,
            }:
                raise ProtocolError("Unexpected STM32 response type")
            result = message.payload.get("result", {})
            if not isinstance(result, dict):
                raise ProtocolError("STM32 response result must be an object")
            self.last_response_frame=frame.decode('ascii',errors='replace').strip()
            return result
        raise CommunicationTimeout(
            f"STM32 command {request_sequence} timed out after {self.command_timeout:.2f}s"
        )

    def drain_events(self) -> list[ProtocolMessage]:
        """Events observed during exchanges; this is not a background serial pump."""
        with self._lock:
            events, self._events = self._events, []
            return events

    def disconnect(self) -> None:
        with self._lock:
            transport = self._transport
        if transport is None:
            return
        stop_error: Exception | None = None
        if self.allow_motor_control:
            try:
                self.execute(CommandName.STOP_MOTOR.value)
            except Exception as exc:
                stop_error = exc
        with self._lock:
            if self._transport is not None:
                transport, self._transport = self._transport, None
                transport.close()
            self._capabilities = None
            self._events.clear()
        if stop_error is not None:
            raise SafeDisconnectError(
                "Serial connection closed, but STOP_MOTOR was not acknowledged"
            ) from stop_error


class SimulatedSTM32Connection:
    """Development adapter with the same operations as the serial connection."""

    def __init__(self, controller: SimulatedMotorController | None = None) -> None:
        self.controller = controller or SimulatedMotorController()
        self.connected = False
        self.sequence = 0

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.controller.command("sim-disconnect", "disable")
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def capabilities(self) -> DeviceCapabilities:
        self._require_connection()
        return DeviceCapabilities(
            "SIM-STM32-ADS",
            ("motor_voltage", "motor_current", "temperature"),
            tuple(command.value for command in CommandName if command not in {CommandName.ARM_TEST, CommandName.CLEAR_FAULTS, CommandName.EMERGENCY_STOP, CommandName.GET_DEVICE_INFO, CommandName.GET_SENSOR_DATA}),
            "sim-1.0",
        )

    def status(self) -> dict:
        self._require_connection()
        state = self.controller.snapshot()
        return {
            "device_id": "SIM-STM32-ADS",
            "state": "RUNNING" if state.enabled and state.pwm_percent else "READY",
            "pwm_percent": state.pwm_percent,
            "direction": state.direction.value,
            "faults": ["EMERGENCY_STOP"] if state.emergency_stop else [],
            "source": "SIMULATION",
        }

    def read_measurements(self) -> dict:
        self._require_connection()
        telemetry = self.controller.telemetry()
        self.sequence += 1
        return {
            "sequence": self.sequence,
            "motor_voltage_v": telemetry.voltage,
            "motor_current_a": telemetry.current,
            "temperature_c": telemetry.temperature,
            "rpm": None,
            "source": "SIMULATION",
        }

    def heartbeat(self) -> dict:
        self._require_connection()
        return {"alive": True, "source": "SIMULATION"}

    def execute(self, command: str, arguments: dict | None = None) -> dict:
        self._require_connection()
        command_name = CommandName(command)
        arguments = arguments or {}
        if command_name is CommandName.GET_STATUS:
            return self.status()
        if command_name is CommandName.GET_CAPABILITIES:
            capabilities = self.capabilities()
            return {
                "device_id": capabilities.device_id,
                "measurement_types": list(capabilities.measurement_types),
                "commands": list(capabilities.commands),
                "firmware_version": capabilities.firmware_version,
            }
        if command_name is CommandName.READ_MEASUREMENTS:
            return self.read_measurements()
        if command_name is CommandName.GET_FAULTS:
            return {"faults": self.status()["faults"]}
        if command_name is CommandName.SET_PWM:
            acknowledgment = self.controller.command(
                "sim-set-pwm", "set_pwm", arguments.get("pwm_percent")
            )
        elif command_name is CommandName.SET_DIRECTION:
            acknowledgment = self.controller.command(
                "sim-set-direction", "set_direction", arguments.get("direction")
            )
        elif command_name in {CommandName.STOP_MOTOR, CommandName.STOP_TEST}:
            acknowledgment = self.controller.command("sim-stop", "disable")
        elif command_name is CommandName.START_TEST:
            acknowledgment = self.controller.command("sim-start", "enable")
        else:
            raise DeviceResponseError(f"UNSUPPORTED_COMMAND: {command_name.value}")
        if not acknowledgment.accepted:
            raise DeviceResponseError(f"COMMAND_REJECTED: {acknowledgment.message}")
        return {"accepted": True, "message": acknowledgment.message}

    def _require_connection(self) -> None:
        if not self.connected:
            raise ConnectionError("Simulated STM32 is not connected")
