from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .control import CommandAcknowledgment, MotorControlState, MotorTelemetry
from .models import MotorMeasurement
from .sources import MeasurementSource


@dataclass(frozen=True)
class DeviceCapabilities:
    device_id: str
    measurement_types: tuple[str, ...]
    commands: tuple[str, ...]
    firmware_version: str | None = None


@runtime_checkable
class DeviceConnection(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def capabilities(self) -> DeviceCapabilities: ...
    def status(self) -> dict: ...
    def read_measurements(self) -> dict: ...
    def execute(self, command: str, arguments: dict | None = None) -> dict: ...


@runtime_checkable
class MotorController(Protocol):
    def snapshot(self) -> MotorControlState: ...
    def telemetry(self) -> MotorTelemetry: ...
    def command(
        self, command_id: str, action: str, value: int | str | None = None
    ) -> CommandAcknowledgment: ...


class ReplayMeasurementSource(MeasurementSource):
    """Finite, deterministic source for replaying stored or fixture measurements."""

    def __init__(self, measurements: Iterable[MotorMeasurement]) -> None:
        self._measurements = tuple(measurements)
        self._iterator = iter(())
        self.connected = False

    def connect(self) -> None:
        self._iterator = iter(self._measurements)
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def read(self) -> MotorMeasurement:
        if not self.connected:
            raise ConnectionError("Replay source is not connected")
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise EOFError("Replay source is exhausted") from exc
