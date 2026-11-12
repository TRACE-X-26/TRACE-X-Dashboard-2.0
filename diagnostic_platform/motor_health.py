"""Trace X motor diagnostics. Python 3.9+, standard library only."""

import argparse
import csv
import io
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from zipfile import ZipFile

VOLTAGE = "motor_voltage_V"
CURRENT = "motor_current_A"
POWER = "motor_power_W"
RPM = "motor_rpm"
TEMP = "motor_temperature_C"
METRICS = (VOLTAGE, CURRENT, RPM)
CONTEXT_FIELDS = ("asset_id", "pwm_percent", "load_id", "direction", "calibration_id")
WINDOW_START_MS = 3000
WINDOW_END_MS = 13000
MAX_GAP_MS = 2500
MIN_SAMPLES = 8
MIN_BASELINE_RUNS = 5
SCHEMA_VERSION = 1
TEST_CATALOG = {
    1: ("Safe Idle", 0),
    2: ("10% PWM", 10),
    3: ("25% PWM", 25),
    4: ("50% PWM", 50),
    5: ("75% PWM", 75),
    6: ("100% PWM", 100),
    7: ("Minimum Starting PWM", None),
    8: ("Steady-State RPM", None),
    9: ("Voltage Stability", None),
    10: ("Startup Current", None),
    11: ("Power Consumption", None),
    12: ("Weight / Load Testing", None),
    13: ("Excessive Friction", None),
}

NUMBER = r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))"
LEGACY_FIELDS = {
    re.compile(rf"Voltage: {NUMBER} V"): VOLTAGE,
    re.compile(rf"Current: {NUMBER} A"): CURRENT,
    re.compile(rf"Power: {NUMBER} W"): POWER,
    re.compile(rf"Motor RPM: {NUMBER}"): RPM,
    re.compile(rf"Motor Temperature: {NUMBER} C"): TEMP,
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def measurements(values):
    return {
        name: {"median": median(samples), "min": min(samples),
               "max": max(samples), "samples": len(samples)}
        for name, samples in values.items() if samples
    }


def serial_message(row):
    return (row.get("raw_message") or row.get("serial_message")
            or row.get("raw_serial_message") or "").strip()


def replay_csv(rows, test_number=None):
    """Extract observations from an archived capture without assigning health."""
    values = {name: [] for name in (*METRICS, POWER)}
    events = Counter()
    target_pwm = set()
    electrical = {}
    rpm_by_phase = Counter()
    last_voltage_at = None
    raw_voltage_samples = 0
    rows = list(rows)
    has_start = any(serial_message(row) == "MOTOR_START" for row in rows)
    capture_phase = "before_start" if has_start else "unmarked"
    for row in rows:
        pwm = number(row.get("target_pwm_percent") or row.get("target_pwm")
                     or row.get("pwm_percent"))
        if pwm is not None:
            target_pwm.add(pwm)
        message = serial_message(row)
        if message in ("MOTOR_START", "MOTOR_STOP"):
            capture_phase = "running" if message == "MOTOR_START" else "stopped"
            electrical.clear()
            events[message] += 1
        if message == "INA219 INITIALIZED":
            events["ina219_initialization_message"] += 1
        if message.startswith("{"):
            try:
                frame = json.loads(message)
            except ValueError:
                events["invalid_serial_json"] += 1
            else:
                if (isinstance(frame, dict) and isinstance(frame.get("payload"), dict)
                        and frame["payload"].get("code") == "MALFORMED_FRAME"):
                    events["stm32_rejected_malformed_frame"] += 1
        if message.startswith("Voltage: "):
            raw_voltage_samples += 1
            try:
                received = datetime.fromisoformat(row.get("received_at") or "")
                if last_voltage_at and 0 <= (received - last_voltage_at).total_seconds() < 0.05:
                    events["voltage_receive_intervals_under_50ms"] += 1
                last_voltage_at = received
            except (ValueError, TypeError):
                last_voltage_at = None
        rpm = re.fullmatch(rf"Motor RPM: {NUMBER}", message)
        if rpm and number(rpm.group(1)) == 0:
            rpm_by_phase[capture_phase] += 1
        if "NO PULSES DETECTED" in message:
            events["no_encoder_pulses_reported"] += 1
        if message in ("TEMPERATURE SENSOR: NOT DETECTED", "TEMP ERROR: NO PRESENCE PULSE"):
            events["temperature_sensor_error"] += 1
        if message in ("INA219 NOT DETECTED", "INA219: NOT DETECTED"):
            events["ina219_not_detected"] += 1
        if capture_phase in ("before_start", "stopped"):
            continue
        for pattern, field in LEGACY_FIELDS.items():
            match = pattern.fullmatch(message)
            if not match:
                continue
            value = number(match.group(1))
            if value is None:
                break
            if field == TEMP:
                continue
            if field == POWER:
                values[POWER].append(value)
                electrical.clear()
            else:
                values[field].append(value)
                if field == VOLTAGE:
                    electrical = {VOLTAGE: value}
                elif field == CURRENT and set(electrical) == {VOLTAGE}:
                    electrical[CURRENT] = value
                else:
                    electrical.clear()
            break
        else:
            electrical.clear()

    summary = measurements(values)
    reasons = [
        "legacy_capture_has_no_verified_operating_context",
        "reported_rpm_requires_encoder_calibration_verification",
        "actual_pwm_and_direction_unverified",
    ] if summary else ["no_motor_measurements"]
    name, planned_pwm = TEST_CATALOG.get(test_number, (None, None))
    if planned_pwm is not None and target_pwm and target_pwm != {planned_pwm}:
        reasons.append("logged_target_pwm_differs_from_test_plan")
    if test_number == 1 and any(row.get("hardware_control") == "False" for row in rows):
        reasons.append("software_idle_check_only")
    if events["stm32_rejected_malformed_frame"]:
        reasons.append("stm32_rejected_at_least_one_command_frame")
    if raw_voltage_samples and not events["MOTOR_START"]:
        reasons.append("start_marker_missing")
    return {"schema_version": SCHEMA_VERSION, "status": "not_assessed",
            "test_number": test_number, "test_name": name,
            "planned_pwm_percent": planned_pwm,
            "target_pwm_percent": sorted(target_pwm), "metrics": summary,
            "events": {name: count for name, count in events.items() if count},
            "zero_rpm_samples_by_phase": dict(rpm_by_phase),
            "reasons": reasons}


def capture_context(context):
    result = {field: context.get(field) for field in CONTEXT_FIELDS}
    pwm = number(result["pwm_percent"])
    for field in ("asset_id", "load_id", "calibration_id"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError(f"{field} must be specified")
    if result["direction"] not in ("forward", "reverse"):
        raise ValueError("direction must be forward or reverse")
    if pwm is None or not 0 < pwm <= 100:
        raise ValueError("pwm_percent must be greater than zero and at most 100")
    result["pwm_percent"] = pwm
    return result


def summarize_run(rows, context):
    """Check the agreed running window and summarize canonical STM32 samples."""
    values = {name: [] for name in (*METRICS, POWER)}
    reasons = []
    directions = Counter()
    timestamps = []
    valid_times = []
    previous = -1
    rejected = 0
    for row in rows:
        elapsed = number(row.get("elapsed_ms"))
        if elapsed is None or elapsed < 0 or elapsed <= previous:
            reasons.append("missing_or_non_increasing_elapsed_ms")
            break
        previous = elapsed
        if not WINDOW_START_MS <= elapsed <= WINDOW_END_MS:
            continue
        timestamps.append(elapsed)
        pwm = number(row.get("reported_pwm_percent"))
        if pwm is None or not math.isclose(pwm, context["pwm_percent"], abs_tol=0.01):
            reasons.append("reported_pwm_does_not_match_test")
            continue
        sample = {field: number(row.get(field)) for field in METRICS}
        direction = row.get("motor_direction")
        if (any(value is None for value in sample.values())
                or sample[VOLTAGE] < 0
                or direction not in ("forward", "reverse", "stopped")
                or (direction == "stopped") != (sample[RPM] == 0)):
            rejected += 1
            continue
        product = sample[VOLTAGE] * sample[CURRENT]
        if not math.isfinite(product):
            rejected += 1
            continue
        valid_times.append(elapsed)
        directions[direction] += 1
        sample[RPM] = abs(sample[RPM])
        sample[POWER] = product
        for field, value in sample.items():
            values[field].append(value)

    checkpoints = [WINDOW_START_MS, *valid_times, WINDOW_END_MS]
    if (previous < WINDOW_END_MS or len(valid_times) < MIN_SAMPLES
            or any(b - a > MAX_GAP_MS for a, b in zip(checkpoints, checkpoints[1:]))):
        reasons.append("insufficient_steady_state_telemetry")
    if timestamps and rejected / len(timestamps) > 0.1:
        reasons.append("too_many_invalid_sensor_samples")

    return measurements(values), directions, list(dict.fromkeys(reasons))


def preflight(context):
    if context.get("calibration_verified") is not True:
        return ["measurement_calibration_unverified"]
    if context.get("capture_complete") is not True:
        return ["test_capture_not_confirmed_complete"]
    return []


def fit_baseline(runs, tolerances):
    """Fit one condition from independently collected, operator-labeled healthy runs."""
    if len(runs) < MIN_BASELINE_RUNS:
        raise ValueError(f"at least {MIN_BASELINE_RUNS} known-good runs are required")
    context = capture_context(runs[0]["context"])
    features = {name: [] for name in METRICS}
    seen = set()
    for run in runs:
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip() or run_id in seen:
            raise ValueError("each baseline run must have a unique run_id")
        seen.add(run_id)
        if run.get("known_good") is not True:
            raise ValueError(f"{run_id}: known_good must be explicitly confirmed")
        if capture_context(run["context"]) != context:
            raise ValueError(f"{run_id}: operating context differs from baseline")
        metrics, directions, reasons = summarize_run(run["samples"], context)
        reasons = preflight(run["context"]) + reasons
        if set(directions) != {context["direction"]}:
            reasons.append("commanded_motion_not_confirmed")
        if reasons:
            raise ValueError(f"{run_id}: invalid baseline capture ({', '.join(reasons)})")
        for name in METRICS:
            features[name].append(metrics[name]["median"])

    limits = {}
    for name, samples in features.items():
        floor = number(tolerances.get(name))
        if floor is None or floor <= 0:
            raise ValueError(f"provide a positive tolerance in native units for {name}")
        center = median(samples)
        mad = median(abs(sample - center) for sample in samples)
        width = max(floor, 4 * 1.4826 * mad)
        low, high = center - width, center + width
        if not all(math.isfinite(value) for value in (low, high)):
            raise ValueError(f"non-finite baseline bounds for {name}")
        limits[name] = {"median": center, "lower": low, "upper": high}
    return {"schema_version": SCHEMA_VERSION, "context": context,
            "run_ids": sorted(seen), "limits": limits}


def score_run(rows, context, baseline=None):
    """Return dashboard JSON for a completed diagnostic run."""
    try:
        condition = capture_context(context)
    except ValueError as exc:
        return {"schema_version": SCHEMA_VERSION, "status": "not_assessed",
                "reasons": ["invalid_operating_context"], "detail": str(exc),
                "metrics": {}, "findings": []}
    metrics, directions, reasons = summarize_run(rows, condition)
    reasons = preflight(context) + reasons
    findings = []
    if baseline is None:
        reasons.append("known_good_baseline_required")
    elif baseline.get("schema_version") != SCHEMA_VERSION or baseline.get("context") != condition:
        reasons.append("baseline_does_not_match_operating_context")
    else:
        limits = baseline.get("limits")
        if not isinstance(limits, dict):
            reasons.append("invalid_baseline_limits")
        else:
            for field in METRICS:
                band = limits.get(field)
                low = number(band.get("lower")) if isinstance(band, dict) else None
                high = number(band.get("upper")) if isinstance(band, dict) else None
                if low is None or high is None or low >= high:
                    reasons.append("invalid_baseline_limits")
                    break
                if field not in metrics:
                    continue
                value = metrics[field]["median"]
                metrics[field]["baseline_range"] = [low, high]
                if not low <= value <= high:
                    findings.append({"code": "above_baseline" if value > high else "below_baseline",
                                     "metric": field, "observed": value, "range": [low, high]})
    if directions.get("stopped", 0):
        findings.append({"code": "zero_rpm_reported", "samples": directions["stopped"]})
    other_direction = "reverse" if condition["direction"] == "forward" else "forward"
    if directions.get(other_direction, 0):
        findings.append({"code": "unexpected_direction", "samples": directions[other_direction]})
    status = "not_assessed" if reasons else ("deviation_detected" if findings else "within_baseline")
    return {"schema_version": SCHEMA_VERSION, "status": status, "context": condition,
            "reasons": reasons, "metrics": metrics, "findings": findings,
            "direction_samples": dict(directions)}


def replay_archive(path):
    runs = {}
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".csv"):
                continue
            match = re.search(r"/test_(\d+)/", name)
            rows = list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))
            test_id = int(match.group(1)) if match else number(rows[0].get("test")) if rows else None
            runs[name] = replay_csv(rows, int(test_id) if test_id is not None else None)
    present = {run["test_number"] for run in runs.values()}
    return {"test_catalog": {
        test_id: {"name": name, "planned_pwm_percent": pwm, "present_in_archive": test_id in present}
        for test_id, (name, pwm) in TEST_CATALOG.items()
    }, "runs": runs}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("replay", help="extract observations from an archived ZIP")
    replay.add_argument("archive")
    fit = commands.add_parser("fit", help="calibrate from explicitly labeled known-good JSON runs")
    fit.add_argument("manifest", help="JSON containing runs and tolerances")
    score = commands.add_parser("score", help="assess one canonical JSON run")
    score.add_argument("run")
    score.add_argument("--baseline")
    args = parser.parse_args()
    try:
        if args.command == "replay":
            result = replay_archive(args.archive)
        elif args.command == "fit":
            manifest = load_json(args.manifest)
            result = fit_baseline(manifest["runs"], manifest["tolerances"])
        else:
            run = load_json(args.run)
            result = score_run(run["samples"], run["context"],
                               load_json(args.baseline) if args.baseline else None)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
