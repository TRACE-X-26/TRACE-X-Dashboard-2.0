from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    mode: str
    database_path: Path
    allowed_origins: tuple[str, ...]
    log_level: str
    serial_port: str
    serial_baud: int
    serial_read_timeout: float
    serial_command_timeout: float
    hardware_control_enabled: bool = False
    hardware_profile_path: str = ""

    @classmethod
    def from_environment(cls, root: Path) -> "Settings":
        mode = os.getenv("ADS_MODE", "simulation").strip().lower()
        if mode not in {"simulation", "replay", "hardware"}:
            raise ValueError("ADS_MODE must be simulation, replay, or hardware")
        enabled_value = os.getenv("ADS_HARDWARE_CONTROL_ENABLED", "false").strip().lower()
        if enabled_value not in {"true", "false"}:
            raise ValueError("ADS_HARDWARE_CONTROL_ENABLED must be true or false")
        hardware_enabled = enabled_value == "true"
        hardware_profile = os.getenv("ADS_AUTOMATION_HARDWARE_PROFILE", "").strip()
        if hardware_profile:
            profile_path = Path(hardware_profile).expanduser()
            hardware_profile = str(profile_path if profile_path.is_absolute() else root / profile_path)
        if mode == "hardware" and not hardware_enabled:
            raise RuntimeError("Hardware mode is disabled: explicit ADS_HARDWARE_CONTROL_ENABLED=true required")
        if mode == "replay":
            raise RuntimeError(
                f"{mode.title()} mode is disabled until its runtime adapter is configured and verified"
            )
        if hardware_enabled:
            from .automated_engine import load_hardware_profile
            try:
                load_hardware_profile(hardware_profile, require_motor_protection=False)
            except (OSError, ValueError) as exc:
                raise RuntimeError("Hardware runtime profile rejected: " + str(exc)) from exc
        database_value = os.getenv("ADS_DATABASE_PATH", "diagnostics.db").strip()
        database_path = Path(database_value)
        if not database_path.is_absolute():
            database_path = root / database_path
        origins_value = os.getenv(
            "ADS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        allowed_origins = tuple(
            origin.strip() for origin in origins_value.split(",") if origin.strip()
        )
        if not allowed_origins:
            raise ValueError("ADS_ALLOWED_ORIGINS must contain at least one origin")
        log_level = os.getenv("ADS_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("ADS_LOG_LEVEL is invalid")
        serial_port = os.getenv("ADS_SERIAL_PORT", "/dev/ttyACM0").strip()
        if not serial_port:
            raise ValueError("ADS_SERIAL_PORT cannot be empty")
        try:
            serial_baud = int(os.getenv("ADS_SERIAL_BAUD", "115200"))
            serial_read_timeout = float(os.getenv("ADS_SERIAL_READ_TIMEOUT", "0.25"))
            serial_command_timeout = float(os.getenv("ADS_SERIAL_COMMAND_TIMEOUT", "1.5"))
        except ValueError as exc:
            raise ValueError("Serial settings must be numeric") from exc
        if serial_baud <= 0 or serial_read_timeout <= 0 or serial_command_timeout <= 0:
            raise ValueError("Serial settings must be positive")
        return cls(
            mode,
            database_path,
            allowed_origins,
            log_level,
            serial_port,
            serial_baud,
            serial_read_timeout,
            serial_command_timeout,
            hardware_enabled,
            hardware_profile,
        )
