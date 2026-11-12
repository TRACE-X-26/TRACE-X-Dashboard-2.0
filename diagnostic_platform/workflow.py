from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .diagnostics import MotorDiagnosticEngine
from .models import DiagnosticReport, MotorMeasurement, MotorProfile
from .sources import MeasurementSource
from .storage import DiagnosticStore


class TestState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    SAFETY_CHECK = "SAFETY_CHECK"
    ACQUIRING = "ACQUIRING"
    ANALYZING = "ANALYZING"
    COMPLETE = "COMPLETE"
    COMMUNICATION_FAULT = "COMMUNICATION_FAULT"
    SENSOR_FAULT = "SENSOR_FAULT"
    SAFETY_TRIP = "SAFETY_TRIP"
    TEST_ABORTED = "TEST_ABORTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TestSample:
    measurement: MotorMeasurement
    report: DiagnosticReport


class TestStoppedError(RuntimeError):
    def __init__(self, state: TestState, message: str, sample: TestSample) -> None:
        super().__init__(message)
        self.state = state
        self.sample = sample


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MotorTestSession:
    """Single test lifecycle shared by the CLI, Streamlit, and FastAPI adapters."""

    def __init__(self, source: MeasurementSource, store: DiagnosticStore) -> None:
        self.source = source
        self.store = store
        self.engine = MotorDiagnosticEngine()
        self.state = TestState.IDLE
        self.session_id: int | None = None
        self.profile: MotorProfile | None = None
        self.baseline = None
        self.last_sample: TestSample | None = None
        self.connected = False

    def start(self, profile: MotorProfile, scenario: str) -> int:
        if self.state is not TestState.IDLE:
            raise RuntimeError("Test session has already started")
        self.profile = profile
        self.session_id = self.store.start_session(profile, scenario, utc_now())
        self.baseline = self.store.get_baseline(profile.device_id)
        try:
            self.state = TestState.CONNECTING
            self.source.connect()
            self.connected = True
            self.state = TestState.SAFETY_CHECK
            # Simulation readiness is implicit. Hardware adapters must provide a
            # real readiness gate before they may enter ACQUIRING.
            self.state = TestState.ACQUIRING
            return self.session_id
        except Exception:
            self.fail(TestState.COMMUNICATION_FAULT)
            raise

    def acquire(self) -> TestSample:
        if self.state is not TestState.ACQUIRING or self.profile is None:
            raise RuntimeError(f"Cannot acquire a sample while state is {self.state.value}")
        try:
            measurement = self.source.read()
        except TimeoutError:
            self.fail(TestState.COMMUNICATION_FAULT)
            raise
        assert self.session_id is not None
        self.store.add_measurement(self.session_id, measurement)
        self.state = TestState.ANALYZING
        report = self.engine.analyze(self.profile, measurement, self.baseline)
        self.last_sample = TestSample(measurement, report)
        return self.last_sample

    def enforce_safety(self, sample: TestSample) -> None:
        if any(f.code == "SENSOR_DATA_MISSING" for f in sample.report.findings):
            self.fail(TestState.SENSOR_FAULT)
            raise TestStoppedError(
                TestState.SENSOR_FAULT, "Required sensor data is missing", sample
            )
        if sample.measurement.sequence > 2 and any(
            finding.severity.value == "CRITICAL" for finding in sample.report.findings
        ):
            self.fail(TestState.SAFETY_TRIP)
            raise TestStoppedError(
                TestState.SAFETY_TRIP,
                "Critical diagnostic limit triggered the safety stop",
                sample,
            )
        self.state = TestState.ACQUIRING

    def complete(self) -> DiagnosticReport:
        if self.last_sample is None or self.session_id is None:
            raise RuntimeError("Cannot complete a test without measurements")
        self.state = TestState.COMPLETE
        self.store.complete_session(self.session_id, self.last_sample.report, utc_now())
        return self.last_sample.report

    def fail(self, state: TestState) -> None:
        self.state = state
        if self.session_id is not None:
            self.store.fail_session(self.session_id, state.value, utc_now())

    def close(self) -> None:
        if self.connected:
            self.source.disconnect()
            self.connected = False


class MotorTestRunner:
    def __init__(self, source: MeasurementSource, store: DiagnosticStore) -> None:
        self.session = MotorTestSession(source, store)

    @property
    def state(self) -> TestState:
        return self.session.state

    def run(
        self,
        profile: MotorProfile,
        scenario: str,
        samples: int,
        on_sample: Callable[[MotorMeasurement, DiagnosticReport, int], None] | None = None,
    ) -> tuple[int, DiagnosticReport]:
        if samples < 1:
            raise ValueError("samples must be positive")
        try:
            session_id = self.session.start(profile, scenario)
            for _ in range(samples):
                sample = self.session.acquire()
                if on_sample is not None:
                    on_sample(sample.measurement, sample.report, samples)
                self.session.enforce_safety(sample)
            return session_id, self.session.complete()
        finally:
            self.session.close()
