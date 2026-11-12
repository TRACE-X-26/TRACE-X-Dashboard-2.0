"""Incremental, read-only decoder for existing STM32 human-readable telemetry.

A complete frame is a bounded, unique-field receive cycle, not evidence of
simultaneous sensor acquisition. No values/statuses carry into the next cycle.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


REQUIRED = ('encoder_status', 'motor_rpm', 'ina219_status', 'voltage', 'current', 'power')
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
NUMERIC = {
    'motor_rpm': ('Motor RPM:', re.compile(rf'Motor RPM:\s*({NUMBER})', re.I)),
    'voltage': ('Voltage:', re.compile(rf'Voltage:\s*({NUMBER})\s*V', re.I)),
    'current': ('Current:', re.compile(rf'Current:\s*({NUMBER})\s*A', re.I)),
    'power': ('Power:', re.compile(rf'Power:\s*({NUMBER})\s*W', re.I)),
}


@dataclass
class TextUpdate:
    recognized: bool = False
    changes: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    invalidate: bool = False
    sample: dict | None = None


class PlainTextMotorParser:
    def __init__(self, max_span_seconds: float = 3.0):
        self.max_span_seconds = max_span_seconds
        self.pending: dict = {}
        self.started: float | None = None
        self.first_timestamp: str | None = None

    @property
    def missing_fields(self):
        return [name for name in REQUIRED if name not in self.pending]

    def reset(self):
        self.pending.clear()
        self.started = None
        self.first_timestamp = None

    def feed(self, line: str, *, received: float | None = None, timestamp: str | None = None) -> TextUpdate:
        received = time.monotonic() if received is None else received
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        line = line.strip()
        update = TextUpdate()
        if self.started is not None and received - self.started > self.max_span_seconds:
            self.reset()
            update.warnings.append('INCOMPLETE_FRAME_TIMEOUT')
            update.invalidate = True
        if re.search(r'\b(?:reset|reboot|booting|MOTOR_START|MOTOR_STOP)\b', line, re.I):
            self.reset()
            update.invalidate = True
            return update  # Existing lifecycle parser retains event handling.
        if line.upper().startswith('TEMPERATURE SENSOR:'):
            status=line.split(':',1)[1].strip().upper()
            return TextUpdate(recognized=True,changes={'temperature_status':status},
                              warnings=[] if status=='CONNECTED' else ['TEMPERATURE_UNAVAILABLE'])
        if line.lower().startswith('motor temperature:'):
            match=re.fullmatch(rf'Motor Temperature:\s*({NUMBER})\s*(?:°?C)',line,re.I)
            value=float(match[1]) if match else None
            if value is None or not math.isfinite(value) or not -55<=value<=125:
                return TextUpdate(recognized=True,changes={'temperature_status':'INVALID'},warnings=['TEMPERATURE_UNAVAILABLE'])
            return TextUpdate(recognized=True,changes={'temperature':value,'temperature_status':'CONNECTED'})
        name, value = None, None
        if line.upper().startswith('ENCODER:'):
            name = 'encoder_status'
            value = line.split(':', 1)[1].strip().upper()
            update.recognized = True
            if value not in {'PULSES DETECTED', 'NO PULSES DETECTED'}:
                self.reset()
                update.changes[name] = value[:100] or 'UNKNOWN'
                update.invalidate = True
                update.warnings.append('ENCODER_UNAVAILABLE')
                return update
        elif line.upper().startswith('INA219:'):
            name = 'ina219_status'
            value = line.split(':', 1)[1].strip().upper()
            update.recognized = True
            if value != 'CONNECTED':
                self.reset()
                update.changes[name] = value[:100] or 'UNKNOWN'
                update.invalidate = True
                update.warnings.append('INA219_UNAVAILABLE')
                return update
        else:
            for channel, (prefix, pattern) in NUMERIC.items():
                if line.lower().startswith(prefix.lower()):
                    update.recognized = True
                    match = pattern.fullmatch(line)
                    if match:
                        value = float(match[1])
                    if not match or not math.isfinite(value) or (channel == 'voltage' and value < 0):
                        self.reset()
                        update.invalidate = True
                        update.warnings.append('MALFORMED_' + channel.upper())
                        return update
                    name = channel
                    break
        if name is None:
            return update
        if name in self.pending:
            # Repetition marks a new cycle; do not fill old gaps with new data.
            self.reset()
            update.warnings.append('INCOMPLETE_FRAME_RESTARTED')
        update.changes[name] = value
        if self.started is None:
            if name != 'encoder_status':
                update.warnings.append('WAITING_FOR_ENCODER_CYCLE')
                return update
            self.started, self.first_timestamp = received, timestamp
        self.pending[name] = value
        if not self.missing_fields:
            update.sample = {**self.pending, 'timestamp': timestamp,
                             'first_received_at': self.first_timestamp,
                             'frame_span_seconds': round(received - self.started, 6),
                             'timestamp_basis': 'HOST_RECEIVE_TIME', 'format': 'plain_text',
                             'source': 'stm32_serial', 'quality': 'UNCALIBRATED',
                             'power_origin': 'REPORTED_BY_STM32',
                             'association': 'BOUNDED_UNIQUE_FIELD_RECEIVE_CYCLE'}
            self.reset()
        return update


class SerialLineDecoder:
    """Preserve partial serial reads; bound lines and recover after corruption."""
    def __init__(self, limit=4096):
        self.limit = limit
        self.buffer = bytearray()
        self.dropping = False

    def reset(self):
        self.buffer.clear()
        self.dropping = False

    def feed(self, chunk: bytes):
        lines, errors = [], []
        for byte in chunk:
            if byte == 10:
                if self.dropping:
                    errors.append('FRAME_TOO_LARGE')
                elif self.buffer:
                    try:
                        lines.append(bytes(self.buffer).decode('utf-8').strip())
                    except UnicodeDecodeError:
                        errors.append('INVALID_UTF8')
                self.reset()
            elif not self.dropping:
                self.buffer.append(byte)
                if len(self.buffer) > self.limit:
                    self.buffer.clear()
                    self.dropping = True
        return lines, errors
