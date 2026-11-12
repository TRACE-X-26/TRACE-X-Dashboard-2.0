from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum

from .models import MotorMeasurement


class MeasurementQuality(str, Enum):
    GOOD = "GOOD"
    STALE = "STALE"
    MISSING = "MISSING"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNCALIBRATED = "UNCALIBRATED"


class DataSource(str, Enum):
    SIMULATION = "SIMULATION"
    REPLAY = "REPLAY"
    HARDWARE = "HARDWARE"


@dataclass(frozen=True)
class MeasurementEnvelope:
    timestamp: datetime
    device_id: str
    sensor_id: str
    measurement_type: str
    value: float | None
    unit: str
    quality: MeasurementQuality
    source: DataSource
    calibration_version: str | None
    session_id: int | None
    sequence: int

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        payload["quality"] = self.quality.value
        payload["source"] = self.source.value
        return payload


MOTOR_CHANNELS = {
    "voltage": ("motor-voltage", "V"),
    "current": ("motor-current", "A"),
    "rpm": ("motor-speed", "RPM"),
    "temperature": ("motor-temperature", "°C"),
    "resistance": ("motor-resistance", "Ω"),
    "vibration_rms": ("motor-vibration", "g RMS"),
}


def motor_measurement_envelopes(
    measurement: MotorMeasurement,
    *,
    device_id: str,
    source: DataSource,
    session_id: int | None,
    calibration_version: str | None = None,
) -> tuple[MeasurementEnvelope, ...]:
    envelopes = []
    for measurement_type, (sensor_id, unit) in MOTOR_CHANNELS.items():
        value = getattr(measurement, measurement_type)
        quality = MeasurementQuality.MISSING if value is None else (
            MeasurementQuality.UNCALIBRATED
            if source is DataSource.HARDWARE and calibration_version is None
            else MeasurementQuality.GOOD
        )
        envelopes.append(
            MeasurementEnvelope(
                timestamp=measurement.timestamp,
                device_id=device_id,
                sensor_id=sensor_id,
                measurement_type=measurement_type,
                value=value,
                unit=unit,
                quality=quality,
                source=source,
                calibration_version=calibration_version,
                session_id=session_id,
                sequence=measurement.sequence,
            )
        )
    return tuple(envelopes)
