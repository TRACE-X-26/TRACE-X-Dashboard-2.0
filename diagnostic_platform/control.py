from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum


class MotorDirection(str, Enum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


@dataclass(frozen=True)
class MotorControlState:
    enabled: bool
    direction: MotorDirection
    pwm_percent: int
    emergency_stop: bool
    sequence: int
    updated_at: float


@dataclass(frozen=True)
class MotorTelemetry:
    voltage: float
    current: float
    rpm: float
    temperature: float
    power: float


@dataclass(frozen=True)
class CommandAcknowledgment:
    command_id: str
    accepted: bool
    message: str
    state: MotorControlState


@dataclass(frozen=True)
class MotorSequenceStatus:
    running: bool
    name: str | None
    step_index: int
    total_steps: int
    message: str


class SimulatedMotorController:
    """Safety-aware stand-in for the future STM32 motor controller."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._direction = MotorDirection.FORWARD
        self._pwm_percent = 0
        self._emergency_stop = False
        self._sequence = 0
        self._updated_at = time.time()
        self._temperature = 24.0
        self._last_tick = time.monotonic()

    def _state(self) -> MotorControlState:
        return MotorControlState(
            enabled=self._enabled,
            direction=self._direction,
            pwm_percent=self._pwm_percent,
            emergency_stop=self._emergency_stop,
            sequence=self._sequence,
            updated_at=self._updated_at,
        )

    def snapshot(self) -> MotorControlState:
        with self._lock:
            return self._state()

    def telemetry(self) -> MotorTelemetry:
        with self._lock:
            now = time.monotonic()
            elapsed = min(now - self._last_tick, 2.0)
            self._last_tick = now
            duty = self._pwm_percent / 100 if self._enabled else 0.0
            target_temperature = 24.0 + duty * 30.0
            self._temperature += (target_temperature - self._temperature) * min(elapsed * 0.12, 1.0)
            ripple = math.sin(now * 3.0) * 0.01 if duty else 0.0
            voltage = max(0.0, 12.0 * duty * (1 + ripple))
            current = max(0.0, (0.18 + 1.75 * duty) * duty * (1 + ripple))
            rpm = max(0.0, 2520.0 * duty * (1 + ripple))
            return MotorTelemetry(
                voltage=round(voltage, 3),
                current=round(current, 3),
                rpm=round(rpm, 1),
                temperature=round(self._temperature, 2),
                power=round(voltage * current, 3),
            )

    def command(
        self, command_id: str, action: str, value: int | str | None = None
    ) -> CommandAcknowledgment:
        with self._lock:
            accepted, message = self._apply(action, value)
            if accepted:
                self._sequence += 1
                self._updated_at = time.time()
            return CommandAcknowledgment(command_id, accepted, message, self._state())

    def _apply(self, action: str, value: int | str | None) -> tuple[bool, str]:
        if action == "emergency_stop":
            self._enabled = False
            self._pwm_percent = 0
            self._emergency_stop = True
            return True, "Emergency stop latched; motor output is off"

        if action == "reset_emergency_stop":
            if not self._emergency_stop:
                return False, "Emergency stop is not latched"
            self._emergency_stop = False
            return True, "Emergency stop reset; motor remains disabled"

        if action == "enable":
            if self._emergency_stop:
                return False, "Reset the emergency stop before enabling the motor"
            if self._enabled:
                return False, "Motor is already enabled"
            self._enabled = True
            return True, "Motor driver enabled at 0% PWM"

        if action == "disable":
            self._enabled = False
            self._pwm_percent = 0
            return True, "Motor output disabled"

        if action == "set_pwm":
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                return False, "PWM must be a whole number from 0 to 100"
            if self._emergency_stop:
                return False, "PWM rejected because the emergency stop is latched"
            if value > 0 and not self._enabled:
                return False, "Enable the motor driver before applying PWM"
            self._pwm_percent = value
            return True, f"PWM set to {value}%"

        if action == "set_direction":
            try:
                direction = MotorDirection(str(value).upper())
            except ValueError:
                return False, "Direction must be FORWARD or REVERSE"
            if self._enabled and self._pwm_percent > 0:
                return False, "Set PWM to 0% before changing direction"
            self._direction = direction
            return True, f"Direction set to {direction.value.lower()}"

        return False, f"Unknown motor command: {action}"


def serialize_control_state(state: MotorControlState) -> dict:
    result = asdict(state)
    result["direction"] = state.direction.value
    return result


class SimulatedMotorSequenceService:
    """Backend-owned bounded sequence; never represents verified hardware control."""

    RAMP_STEPS = (20, 40, 60, 80, 100, 80, 60, 40, 20, 0)

    def __init__(self, controller: SimulatedMotorController, interval_seconds: float = 0.7) -> None:
        self.controller = controller
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._running = False
        self._step_index = 0
        self._message = "No sequence has been run"
        self._thread: threading.Thread | None = None

    def status(self) -> MotorSequenceStatus:
        with self._lock:
            return MotorSequenceStatus(
                self._running,
                "PWM_RAMP" if self._running else None,
                self._step_index,
                len(self.RAMP_STEPS),
                self._message,
            )

    def start(self) -> tuple[bool, str]:
        with self._lock:
            state = self.controller.snapshot()
            if self._running:
                return False, "An automated sequence is already running"
            if state.emergency_stop:
                return False, "Reset the emergency stop before running a sequence"
            if state.enabled and state.pwm_percent > 0:
                return False, "Set PWM to 0% before starting an automated sequence"
            self._running = True
            self._step_index = 0
            self._message = "Automated PWM ramp started"
            self._cancel.clear()
            thread = threading.Thread(target=self._run, name="simulated-pwm-ramp", daemon=True)
            self._thread = thread
            thread.start()
            return True, self._message

    def cancel(self) -> tuple[bool, str]:
        with self._lock:
            was_running = self._running
            self._cancel.set()
            self._message = "Sequence cancelled; motor output disabled"
            thread = self._thread
        self.controller.command("sequence-cancel", "disable")
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.interval_seconds + 0.2)
        return was_running, "Sequence cancelled; motor output disabled"

    def _run(self) -> None:
        completed = False
        try:
            state = self.controller.snapshot()
            if not state.enabled:
                acknowledgment = self.controller.command("sequence-enable", "enable")
                if not acknowledgment.accepted:
                    with self._lock:
                        self._message = acknowledgment.message
                    return
            for index, pwm in enumerate(self.RAMP_STEPS, start=1):
                if self._cancel.is_set():
                    return
                acknowledgment = self.controller.command(
                    f"sequence-step-{index}", "set_pwm", pwm
                )
                with self._lock:
                    self._step_index = index
                    self._message = acknowledgment.message
                if not acknowledgment.accepted:
                    return
                if self._cancel.wait(self.interval_seconds):
                    return
            completed = True
        finally:
            self.controller.command("sequence-stop", "disable")
            with self._lock:
                self._running = False
                self._thread = None
                self._message = (
                    "Automated PWM ramp completed; motor output disabled"
                    if completed
                    else self._message
                )
