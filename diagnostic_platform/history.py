"""Conservative, offline CSV ingestion. Never opens a serial device or actuates hardware."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import statistics
from datetime import datetime


FIELDS = {
    "voltage": ("voltage", "voltage_v", "motor_voltage_v", "motor_voltage_V"),
    "current": ("current", "current_a", "motor_current_a", "motor_current_A"),
    "rpm": ("rpm", "motor_rpm"),
    "temperature": ("temperature", "temperature_c", "motor_temperature_C"),
    "recorded_power": ("power", "power_w", "motor_power_W"),
    "encoder_counts": ("encoder_counts",),
}
PATTERNS = {
    "voltage": r"\bVoltage:\s*([-+\d.eE]+)\s*V\b",
    "current": r"\bCurrent:\s*([-+\d.eE]+)\s*A\b",
    "recorded_power": r"\bPower:\s*([-+\d.eE]+)\s*W\b",
    "rpm": r"\bMotor RPM:\s*([-+\d.eE]+)\b",
    "temperature": r"\bTemperature:\s*([-+\d.eE]+)\s*(?:°?C)\b",
    "encoder_counts": r"\bEncoder Counts:\s*([-+\d.eE]+)\b",
}


def parse_csv(content: str, metadata: dict) -> dict:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("CSV requires unique column headers")
    if not ({"raw_message", "raw_serial_message", "serial_message"} | {a for aliases in FIELDS.values() for a in aliases}) & set(reader.fieldnames):
        raise ValueError("No supported measurement or raw_message column")
    samples, warnings, events = [], [], []
    state, segment, last_time = "BEFORE_START", 0, None
    seen = set()
    seen_rows = set()
    for line, row in enumerate(reader, 2):
        if line > 100002:
            raise ValueError("CSV exceeds 100000 rows")
        issues = []
        raw = row.get("raw_message") or row.get("raw_serial_message") or row.get("serial_message") or ""
        if (row.get("mode") or "MOTOR").strip().upper() != "MOTOR":
            warnings.append({"line": line, "code": "NON_MOTOR_ROW_EXCLUDED"})
            continue
        signature = tuple((str(k), repr(v)) for k, v in row.items())
        if signature in seen_rows:
            if row.get("timestamp") or row.get("time") or row.get("received_at"):
                warnings.append({"line": line, "code": "DUPLICATE_ROW"})
                continue
            issues.append("POSSIBLE_DUPLICATE_WITHOUT_TIMESTAMP")
        seen_rows.add(signature)
        if None in row or any(v is None for v in row.values()):
            issues.append("MALFORMED_CSV_ROW")
        timestamp = row.get("timestamp") or row.get("time") or row.get("received_at") or ""
        instant = None
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                issues.append("TIMESTAMP_TIMEZONE_UNKNOWN")
            else:
                instant = parsed.timestamp()
        except ValueError:
            issues.append("TIMESTAMP_UNPARSED")
        if instant is not None and last_time is not None:
            if instant < last_time:
                issues.append("TIME_REVERSED")
                state, segment = "UNKNOWN", segment + 1
            elif instant - last_time > 5:
                issues.append("COMMUNICATION_GAP")
                state, segment = "UNKNOWN", segment + 1
            elif instant == last_time:
                issues.append("SAME_TIMESTAMP_POSSIBLE_UART_BURST")
            elif instant - last_time < 0.001:
                issues.append("SUB_MILLISECOND_RECEIVE_BURST")
        if instant is not None:
            last_time = instant
        tokens = re.findall(r"\bMOTOR_(?:START|STOP)\b", raw)
        if re.search(r"\b(?:reset|reboot|booting)\b", raw, re.I):
            state, segment = "UNKNOWN", segment + 1
            issues.append("DEVICE_RESET")
        if len(tokens) > 1:
            state = "UNKNOWN"
            issues.append("AMBIGUOUS_EVENTS")
        elif tokens:
            if tokens[0] == "MOTOR_START":
                segment += 1
                state = "RUNNING"
            else:
                state = "AFTER_STOP"
            events.append({"line": line, "timestamp": timestamp, "event": tokens[0], "segment": segment})
        if re.search(r"error|fail|disconnect|timeout|not detected|no presence pulse", raw, re.I):
            issues.append("SENSOR_OR_COMMUNICATION_MESSAGE")
        direction = (row.get("motor_direction") or row.get("direction") or "").strip().upper()
        if direction and direction not in {"FORWARD", "REVERSE", "STOPPED", "UNKNOWN"}:
            issues.append("INVALID_DIRECTION")
            direction = "UNKNOWN"
        values = {}
        for field, aliases in FIELDS.items():
            candidates = [row[a].strip() for a in aliases if (row.get(a) or "").strip()]
            matches = re.findall(PATTERNS[field], raw, re.I)
            if re.search({"voltage": r"\bVoltage:", "current": r"\bCurrent:",
                          "recorded_power": r"\bPower:", "rpm": r"\bMotor RPM:",
                          "temperature": r"\bTemperature:", "encoder_counts": r"\bEncoder Counts:"}[field], raw, re.I) and not matches:
                issues.append(f"MALFORMED_{field.upper()}_MESSAGE")
            candidates += matches
            value = None
            if candidates:
                try:
                    numbers = [float(v) for v in candidates]
                    if any(not math.isfinite(v) or (v < 0 and field not in {"temperature", "rpm", "encoder_counts"}) for v in numbers):
                        raise ValueError()
                    if any(v != numbers[0] for v in numbers[1:]) or len(matches) > 1:
                        issues.append(f"AMBIGUOUS_{field.upper()}")
                    else:
                        value = numbers[0]
                        if value < 0 and field in {"rpm", "encoder_counts"}:
                            issues.append("SIGNED_ENCODER_CONVENTION_UNVERIFIED")
                except ValueError:
                    issues.append(f"INVALID_{field.upper()}")
            values[field] = value
        identity = (timestamp, raw, direction, tuple(values.values()))
        duplicate = bool(timestamp) and identity in seen
        seen.add(identity)
        if duplicate:
            issues.append("DUPLICATE_ROW")
        present = sum(values[k] is not None for k in ("voltage", "current", "rpm", "temperature"))
        if direction or any(v is not None for v in values.values()):
            issues.append("CALIBRATION_UNVERIFIED")
            if present < 4:
                issues.append("PARTIAL_SAMPLE_NO_CROSS_ROW_JOIN")
            power = None
            # Only explicit same-row numerical channels justify computed input power.
            if raw and values["voltage"] is not None and values["current"] is not None:
                issues.append("RAW_CHANNEL_ASSOCIATION_UNVERIFIED")
            elif values["voltage"] is not None and values["current"] is not None:
                power = values["voltage"] * values["current"]
                if not math.isfinite(power):
                    power = None
                    issues.append('INVALID_COMPUTED_POWER')
            samples.append({"sequence": len(samples) + 1, "line": line, "timestamp": timestamp,
                            "phase": state, "segment": segment, **values,
                            "direction": direction or None,
                            "input_power": power, "duplicate": duplicate, "warnings": issues.copy()})
        if raw and not tokens and not any(v is not None for v in values.values()) and not issues:
            issues.append("UNRECOGNIZED_MESSAGE")
        warnings.extend({"line": line, "code": code} for code in issues)
    running = [s for s in samples if s["phase"] == "RUNNING" and not s["duplicate"]]
    def summarize(rows):
        features = {}
        for field in ("voltage", "current", "rpm", "temperature", "input_power", "recorded_power"):
            vals = [s[field] for s in rows if s[field] is not None and not s['duplicate']]
            features[field] = {"count": len(vals), "mean": statistics.fmean(vals) if vals else None,
                               "min": min(vals) if vals else None, "max": max(vals) if vals else None,
                               "std": statistics.pstdev(vals) if vals else None}
        return features
    features = summarize(running)
    return {"source": "HISTORICAL_CSV", "parser_version": "2", "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "metadata": metadata, "samples": samples, "events": events, "warnings": warnings,
            "features": features, "running_samples": len(running),
            "recorded_features": summarize(samples),
            "timestamp_basis": "HOST_RECEIVE_TIME" if 'received_at' in reader.fieldnames else "RECORDED_TIMESTAMP_UNVERIFIED",
            "completeness": {field: {"present": sum(s[field] is not None for s in running),
                                       "total": len(running)}
                             for field in ("voltage", "current", "rpm", "temperature")},
            "analysis_status": "INSUFFICIENT_CALIBRATION",
            "limitations": ["Original rows retained; adjacent raw messages are not assumed simultaneous.",
                "START/STOP are recorded events, not confirmed command or shaft-state timestamps.",
                "RPM counting method and calibration are unverified; no gram, torque, ML or health prediction.",
                "Electrical channels describe motor-branch/driver input, not motor-terminal measurements.",
                "Startup duration, steady-state baseline and temperature change require validated time/phase association."]}
