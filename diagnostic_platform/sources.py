from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod

from .models import MotorMeasurement, MotorProfile


class MeasurementSource(ABC):
    def connect(self) -> None:
        """Open the source. Hardware implementations can override this."""

    def disconnect(self) -> None:
        """Close the source. Hardware implementations can override this."""

    @abstractmethod
    def read(self) -> MotorMeasurement:
        """Return one calibrated measurement frame."""


class SimulatedMotorSource(MeasurementSource):
    SCENARIOS = {
        "healthy": (1.00, 0.92, 0.96, 0.52),
        "overloaded": (0.98, 1.35, 0.70, 0.78),
        "undervoltage": (0.75, 0.86, 0.68, 0.48),
        "overheating": (1.00, 1.08, 0.91, 1.08),
        "stalled": (1.00, 1.60, 0.00, 0.75),
        "sensor_failure": (1.00, 0.92, 0.96, 0.52),
        "communication_loss": (1.00, 0.92, 0.96, 0.52),
    }

    def __init__(
        self, profile: MotorProfile, scenario: str = "healthy", seed: int | None = None
    ) -> None:
        if scenario not in self.SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        self.profile = profile
        self.scenario = scenario
        self.random = random.Random(seed)
        self.connected = False
        self.sequence = 0
        self.started_at = 0.0

    def connect(self) -> None:
        self.connected = True
        self.sequence = 0
        self.started_at = time.monotonic()

    def disconnect(self) -> None:
        self.connected = False

    def _jitter(self, value: float, fraction: float = 0.015) -> float:
        return max(0.0, value * (1 + self.random.uniform(-fraction, fraction)))

    def read(self) -> MotorMeasurement:
        if not self.connected:
            raise ConnectionError("Measurement source is not connected")
        self.sequence += 1
        if self.scenario == "communication_loss" and self.sequence >= 4:
            raise TimeoutError("Simulated STM32 communication timeout")
        voltage, current, rpm, temperature = self.SCENARIOS[self.scenario]
        # Simulate an initial current surge and motor acceleration.
        if self.sequence <= 2 and self.scenario not in {"stalled", "sensor_failure"}:
            current *= 1.35
            rpm *= 0.45 + (self.sequence - 1) * 0.25
        return MotorMeasurement(
            voltage=self._jitter(self.profile.rated_voltage * voltage),
            current=None if self.scenario == "sensor_failure" else self._jitter(self.profile.rated_current * current),
            rpm=0.0 if rpm == 0 else self._jitter(self.profile.rated_rpm * rpm),
            temperature=self._jitter(self.profile.max_temperature * temperature),
            resistance=self._jitter(self.profile.winding_resistance),
            vibration_rms=self._jitter(0.18 if self.scenario == "healthy" else 0.65),
            sequence=self.sequence,
        )
