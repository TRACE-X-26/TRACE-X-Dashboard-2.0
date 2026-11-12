from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Literal


class ProfilePayload(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    rated_voltage: float = Field(gt=0)
    rated_current: float = Field(gt=0)
    rated_rpm: float = Field(gt=0)
    winding_resistance: float = Field(gt=0)
    max_current: float = Field(gt=0)
    max_temperature: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_current_limits(self):
        if self.max_current < self.rated_current:
            raise ValueError("max_current cannot be below rated_current")
        return self


class TestRequest(BaseModel):
    device_id: str
    scenario: str = "healthy"
    samples: int = Field(default=25, ge=5, le=500)
    interval_ms: int = Field(default=100, ge=0, le=5000)


class MotorCommandPayload(BaseModel):
    command_id: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=40)
    value: int | str | None = None


class CircuitRunPayload(BaseModel):
    profile_id: str
    mode: str = "DIAGNOSE"
    scenario: str = "healthy"


class STM32CommandPayload(BaseModel):
    command: str = Field(min_length=1, max_length=40)
    arguments: dict = Field(default_factory=dict)


class HistoricalImportPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=2_000_000)
    device_id: str = Field(min_length=1, max_length=80)
    condition: str = Field(default="UNKNOWN", max_length=120)
    attached_mass_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fixture_description: str = Field(default="", max_length=2000)
    target_pwm_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class PhysicalCircuitPoint(BaseModel):
    point_id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=100)
    instruction: str = Field(min_length=1, max_length=500)
    channel: Literal['test_point_voltage', 'circuit_supply_voltage', 'circuit_current', 'circuit_power']
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)

    @model_validator(mode='after')
    def interval(self):
        if self.minimum > self.maximum:
            raise ValueError('Minimum cannot exceed maximum')
        return self


class PhysicalCircuitAsset(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    supply_voltage: float = Field(gt=0, allow_inf_nan=False)
    components: str = Field(min_length=1, max_length=3000)
    connections: str = Field(min_length=1, max_length=3000)
    test_points: list[PhysicalCircuitPoint] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique_points(self):
        ids = [p.point_id for p in self.test_points]
        if len(ids) != len(set(ids)):
            raise ValueError('Test-point IDs must be unique')
        return self


class PhysicalCircuitStart(BaseModel):
    asset_id: str
    conditions_confirmed: bool = False


class PhysicalCircuitArm(BaseModel):
    point_id: str
    probe_confirmed: Literal[True]

class AutomatedRunPayload(BaseModel):
    load_id: str = Field(default='UNKNOWN', min_length=1, max_length=120)
    condition: str = Field(default='UNKNOWN', min_length=1, max_length=200)
    attached_mass_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fixture_notes: str = Field(default='', max_length=2000)
    mode: Literal['simulation','hardware'] = 'simulation'
    device_id: str = Field(default='MOTOR-001',min_length=1,max_length=80)
    tests: list[str] = Field(default_factory=list,max_length=20)
    run_all: bool = False
    duration_ms: int = Field(default=30000,ge=100,le=30000)
    scenario: Literal['healthy','overloaded','undervoltage','overheating','stalled','sensor_failure','communication_loss'] = 'healthy'
    operator_authorized: bool = False
    supervised_confirmed: bool = Field(default=False,strict=True)


class BranchSelectionPayload(BaseModel):
    branch: Literal['MOTOR', 'CIRCUIT']


class CircuitPowerPayload(BaseModel):
    on: bool = Field(strict=True)
    duration_ms: int = Field(default=30000, ge=100, le=30000, strict=True)
    supervised_confirmed: bool = Field(default=False, strict=True)
