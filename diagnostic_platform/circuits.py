from __future__ import annotations

import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CircuitTestPoint:
    point_id: str
    label: str
    instruction: str
    sensor: str
    unit: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class CircuitProfile:
    profile_id: str
    name: str
    description: str
    test_points: tuple[CircuitTestPoint, ...]


class CircuitDiagnosticService:
    SCENARIOS = ("healthy", "blown_fuse", "open_load", "shorted_load", "supply_drop")

    def __init__(self) -> None:
        self.profiles = {
            "12V-LOAD": CircuitProfile(
                "12V-LOAD",
                "12 V protected load circuit",
                "Power supply, fuse, relay, and resistive load path from the capstone diagram.",
                (
                    CircuitTestPoint("TP1", "Supply input", "Place the voltage probe across the circuit supply input.", "Voltage probe", "V", 11.4, 12.6),
                    CircuitTestPoint("TP2", "After fuse", "Move the positive probe to the protected side of the fuse.", "Voltage probe", "V", 11.2, 12.6),
                    CircuitTestPoint("TP3", "Load current", "Close the simulated relay and capture circuit current.", "INA219 #2", "A", 0.08, 0.16),
                    CircuitTestPoint("TP4", "Load resistance", "Open the relay, remove power, then measure across the load.", "Calculated V/I", "Ω", 70.0, 130.0),
                ),
            )
        }
        self.learned: dict[str, dict[str, float]] = {}

    def list_profiles(self) -> list[dict]:
        return [
            {**asdict(profile), "test_points": [asdict(point) for point in profile.test_points]}
            for profile in self.profiles.values()
        ]

    def run(self, profile_id: str, mode: str, scenario: str) -> dict:
        if profile_id not in self.profiles:
            raise KeyError("Circuit profile not found")
        mode = mode.upper()
        if mode not in {"LEARN", "DIAGNOSE"}:
            raise ValueError("Mode must be LEARN or DIAGNOSE")
        if scenario not in self.SCENARIOS:
            raise ValueError("Unknown circuit scenario")
        if mode == "LEARN":
            scenario = "healthy"

        profile = self.profiles[profile_id]
        values = self._scenario_values(scenario)
        rng = random.Random(f"{profile_id}:{scenario}")
        steps = []
        learned_values: dict[str, float] = {}
        failures = []
        for point in profile.test_points:
            measured = values[point.point_id] * (1 + rng.uniform(-0.008, 0.008))
            learned_values[point.point_id] = measured
            baseline = self.learned.get(profile_id, {}).get(point.point_id)
            minimum, maximum = point.minimum, point.maximum
            if mode == "DIAGNOSE" and baseline is not None:
                tolerance = max(abs(baseline) * 0.12, (point.maximum - point.minimum) * 0.25)
                minimum, maximum = max(0, baseline - tolerance), baseline + tolerance
            passed = minimum <= measured <= maximum
            explanation = self._explanation(scenario, point.point_id, passed)
            if not passed:
                failures.append(explanation)
            steps.append({
                **asdict(point),
                "measured": round(measured, 3),
                "expected_min": round(minimum, 3),
                "expected_max": round(maximum, 3),
                "result": "LEARNED" if mode == "LEARN" else "PASS" if passed else "FAIL",
                "explanation": explanation,
            })

        if mode == "LEARN":
            self.learned[profile_id] = learned_values
            conclusion = "Healthy circuit behavior learned for future comparisons."
            condition = "LEARNED"
        elif failures:
            conclusion = failures[0]
            condition = "FAULT"
        else:
            conclusion = "All test points are within their expected ranges."
            condition = "HEALTHY"
        return {
            "profile_id": profile_id,
            "mode": mode,
            "scenario": scenario,
            "condition": condition,
            "conclusion": conclusion,
            "uses_learned_baseline": profile_id in self.learned and mode == "DIAGNOSE",
            "steps": steps,
        }

    @staticmethod
    def _scenario_values(scenario: str) -> dict[str, float]:
        return {
            "healthy": {"TP1": 12.05, "TP2": 11.96, "TP3": 0.115, "TP4": 104.0},
            "blown_fuse": {"TP1": 12.05, "TP2": 0.03, "TP3": 0.0, "TP4": 104.0},
            "open_load": {"TP1": 12.05, "TP2": 11.96, "TP3": 0.0, "TP4": 5000.0},
            "shorted_load": {"TP1": 12.05, "TP2": 11.7, "TP3": 2.4, "TP4": 3.2},
            "supply_drop": {"TP1": 8.4, "TP2": 8.2, "TP3": 0.075, "TP4": 104.0},
        }[scenario]

    @staticmethod
    def _explanation(scenario: str, point_id: str, passed: bool) -> str:
        if passed:
            return "Reading is within the expected range."
        explanations = {
            "blown_fuse": "Voltage is present before the fuse but missing after it; inspect or replace the fuse.",
            "open_load": "No load current and very high resistance indicate an open connection or disconnected load.",
            "shorted_load": "Excessive current and low resistance indicate a shorted load; keep the relay open.",
            "supply_drop": "Low input voltage indicates a weak supply, wiring loss, or incorrect supply setting.",
        }
        return explanations.get(scenario, f"{point_id} is outside its expected range.")
