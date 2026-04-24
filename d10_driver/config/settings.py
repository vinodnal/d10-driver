"""
Configuration management for the D10 driver.

This module loads, validates, and exposes all driver settings from a YAML
configuration file (default: ``config.yaml`` in the working directory).
Settings can be overridden by environment variables.

Configuration sections
----------------------
``serial``
    RS-232 port settings for communicating with the instrument.
``database``
    MySQL connection parameters.
``logging``
    Log-level and log-directory overrides.
``driver``
    General driver behaviour flags.

Usage
-----
::

    from d10_driver.config.settings import get_settings

    cfg = get_settings()
    print(cfg.serial.port)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "serial": {
        "port": "/dev/ttyUSB0",
        "baud_rate": 9600,
        "data_bits": 8,
        "parity": "N",
        "stop_bits": 1,
        "timeout": 5,
        "read_timeout": 30,
    },
    "database": {
        "host": "localhost",
        "port": 3306,
        "user": "d10driver",
        "password": "",
        "database": "d10_results",
        "pool_size": 5,
    },
    "logging": {
        "level": "DEBUG",
        "console_level": "INFO",
        "log_dir": "logs",
    },
    "driver": {
        "instrument_id": "D10-001",
        "auto_commit": True,
        "retry_attempts": 3,
        "retry_delay": 2,
        "ack_timeout": 10,
    },
}

# ---------------------------------------------------------------------------
# Dataclass models for each config section
# ---------------------------------------------------------------------------


@dataclass
class SerialConfig:
    """RS-232 serial port settings (ASTM E1381 physical layer)."""

    #: Serial port device path (e.g. ``/dev/ttyUSB0`` or ``COM3``).
    port: str = "/dev/ttyUSB0"
    #: Baud rate. The D-10 defaults to 9 600 bps.
    baud_rate: int = 9600
    #: Number of data bits (must be 8 for ASTM compliance).
    data_bits: int = 8
    #: Parity: ``"N"`` (none), ``"E"`` (even), ``"O"`` (odd).
    parity: str = "N"
    #: Stop bits (1 or 2).
    stop_bits: int = 1
    #: pyserial read timeout in seconds for individual byte reads.
    timeout: int = 5
    #: Maximum seconds to wait for a complete ASTM message.
    read_timeout: int = 30


@dataclass
class DatabaseConfig:
    """MySQL database connection settings."""

    host: str = "localhost"
    port: int = 3306
    user: str = "d10driver"
    password: str = ""
    database: str = "d10_results"
    pool_size: int = 5


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "DEBUG"
    console_level: str = "INFO"
    log_dir: str = "logs"


@dataclass
class DriverConfig:
    """General driver behaviour settings."""

    #: Human-readable identifier for this instrument instance.
    instrument_id: str = "D10-001"
    #: If ``True``, results are automatically written to the database.
    auto_commit: bool = True
    #: Number of ASTM retransmission attempts on NAK.
    retry_attempts: int = 3
    #: Seconds to wait between retransmission attempts.
    retry_delay: int = 2
    #: Seconds to wait for an ACK/NAK from the remote.
    ack_timeout: int = 10


@dataclass
class Settings:
    """Root settings object aggregating all configuration sections."""

    serial: SerialConfig = field(default_factory=SerialConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    driver: DriverConfig = field(default_factory=DriverConfig)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None
_config_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from *config_path* (YAML) and apply environment overrides.

    Parameters
    ----------
    config_path:
        Path to a YAML configuration file.  If ``None``, the driver looks
        for ``config.yaml`` in the current working directory.  If the file
        is not found, built-in defaults are used.

    Returns
    -------
    Settings
        Populated settings object.

    Environment overrides
    ---------------------
    Any setting can be overridden by setting an environment variable named
    ``D10_<SECTION>_<KEY>`` (all uppercase).  For example::

        D10_SERIAL_PORT=/dev/ttyS0
        D10_DATABASE_PASSWORD=secret
    """
    global _settings, _config_path

    path = Path(config_path) if config_path else Path("config.yaml")
    _config_path = path

    raw: dict = dict(_DEFAULTS)

    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            file_data = yaml.safe_load(fh) or {}
        # Deep-merge file_data into raw defaults
        for section, values in file_data.items():
            if section in raw and isinstance(values, dict):
                raw[section].update(values)
            else:
                raw[section] = values

    # Apply environment variable overrides (D10_SECTION_KEY=value)
    _apply_env_overrides(raw)

    _settings = Settings(
        serial=SerialConfig(**raw.get("serial", {})),
        database=DatabaseConfig(**raw.get("database", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
        driver=DriverConfig(**raw.get("driver", {})),
    )
    return _settings


def get_settings() -> Settings:
    """Return the current settings, loading defaults if not yet initialised.

    Returns
    -------
    Settings
        The global settings singleton.
    """
    if _settings is None:
        load_settings()
    return _settings  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_env_overrides(raw: dict) -> None:
    """Mutate *raw* based on ``D10_<SECTION>_<KEY>`` environment variables."""
    prefix = "D10_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        # e.g.  D10_SERIAL_PORT → section=serial, key=port
        parts = env_key[len(prefix):].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, key = parts
        if section in raw and isinstance(raw[section], dict):
            # Attempt type coercion based on the default value
            default = raw[section].get(key)
            raw[section][key] = _coerce(env_val, default)


def _coerce(value: str, reference) -> object:
    """Coerce *value* (string from env) to the type of *reference*."""
    if reference is None:
        return value
    if isinstance(reference, bool):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(reference, int):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value
