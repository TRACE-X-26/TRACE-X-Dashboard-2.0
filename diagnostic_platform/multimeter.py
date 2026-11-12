from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass

from .control import MotorControlState, MotorTelemetry


@dataclass(frozen=True)
class MeterChannel:
    channel: str
    label: str
    sensor: str
    value: float
    unit: str
    status: str = "OK"


class SimulatedMultimeter:
    """Produces calibrated values with the same channel names as planned hardware."""

    def read(
        self, motor_state: MotorControlState, motor: MotorTelemetry
    ) -> dict:
        now = time.time()
        ripple = math.sin(now * 2.1)
        circuit_voltage = 5.0 + ripple * 0.035
        circuit_current = 0.115 + ripple * 0.004
        probe_voltage = 12.05 + ripple * 0.045
        resistance = probe_voltage / max(circuit_current, 0.001)
        channels = (
            MeterChannel("motor_voltage", "Motor voltage", "INA219 #1", motor.voltage, "V"),
            MeterChannel("motor_current", "Motor current", "INA219 #1", motor.current, "A"),
            MeterChannel("motor_power", "Motor power", "INA219 #1", motor.power, "W"),
            MeterChannel("circuit_voltage", "Circuit voltage", "INA219 #2", circuit_voltage, "V"),
            MeterChannel("circuit_current", "Circuit current", "INA219 #2", circuit_current, "A"),
            MeterChannel("probe_voltage", "Voltage probe", "Divider + ADC", probe_voltage, "V"),
            MeterChannel("resistance", "Calculated resistance", "V/I calculation", resistance, "Ω"),
        )
        return {
            "timestamp": now,
            "sample_id": int(now * 10),
            "motor_enabled": motor_state.enabled,
            "channels": [asdict(channel) for channel in channels],
        }
