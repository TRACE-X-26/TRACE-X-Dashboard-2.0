from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Severity(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class MotorProfile:
    device_id: str
    rated_voltage: float
    rated_current: float
    rated_rpm: float
    winding_resistance: float
    max_current: float
    max_temperature: float

    def __post_init__(self) -> None:
        numeric = (
            self.rated_voltage,
            self.rated_current,
            self.rated_rpm,
            self.winding_resistance,
            self.max_current,
            self.max_temperature,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("Motor profile values must be positive")
        if self.max_current < self.rated_current:
            raise ValueError("max_current cannot be below rated_current")


@dataclass(frozen=True)
class MotorMeasurement:
    voltage: float | None
    current: float | None
    rpm: float | None
    temperature: float | None
    resistance: float | None
    vibration_rms: float | None = None
    sequence: int = 0
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        values = tuple(value for value in (
            self.voltage,
            self.current,
            self.rpm,
            self.temperature,
            self.resistance,
            self.vibration_rms,
        ) if value is not None)
        if any(value < 0 for value in values):
            raise ValueError("Measurements cannot be negative")
        if self.sequence < 0:
            raise ValueError("Measurement sequence cannot be negative")

    @property
    def input_power(self) -> float | None:
        if self.voltage is None or self.current is None:
            return None
        return self.voltage * self.current

    @property
    def copper_loss(self) -> float | None:
        if self.current is None or self.resistance is None:
            return None
        return self.current**2 * self.resistance


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    possible_causes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticReport:
    device_id: str
    health_score: int
    condition: str
    measurement: MotorMeasurement
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class MotorBaseline:
    device_id: str
    created_at: str
    sample_count: int
    voltage_mean: float
    current_mean: float
    rpm_mean: float
    temperature_mean: float
    current_std: float
    rpm_std: float

    def __post_init__(self) -> None:
        if self.sample_count < 1:
            raise ValueError("A baseline requires at least one sample")
