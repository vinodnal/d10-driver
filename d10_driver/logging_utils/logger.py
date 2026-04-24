"""
Logging utilities for the D10 driver.

This module provides a centralised logging configuration used by every
component of the driver.  It sets up:

- A rotating file handler that keeps a full trace of every session.
- A coloured console handler for human-readable, real-time feedback.
- A structured ``getLogger`` helper so each module can obtain its own
  child logger without duplicating setup code.

Usage
-----
From any module in the package::

    from d10_driver.logging_utils.logger import get_logger

    log = get_logger(__name__)
    log.info("Driver started")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

try:
    import colorlog  # optional coloured console output
    _HAS_COLORLOG = True
except ImportError:  # pragma: no cover
    _HAS_COLORLOG = False

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Default log directory (relative to the working directory, or overridable).
DEFAULT_LOG_DIR = Path("logs")

#: Maximum size of a single log file before rotation (bytes).
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

#: Number of rotated log files to keep.
LOG_FILE_BACKUP_COUNT = 5

#: Log format used by the file handler (includes all relevant context).
FILE_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-40s | "
    "%(funcName)-25s | %(lineno)4d | %(message)s"
)

#: Log format used by the console handler.
CONSOLE_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

#: Coloured log format (used when *colorlog* is available).
COLOUR_LOG_FORMAT = (
    "%(log_color)s%(asctime)s | %(levelname)-8s%(reset)s | "
    "%(name)s | %(message)s"
)

#: Colour mapping for log levels.
LOG_COLOURS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_configured: bool = False  # guard against double-initialisation


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def configure_logging(
    *,
    log_level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    log_dir: Path | str | None = None,
    log_filename: str = "d10_driver.log",
) -> None:
    """Configure the root logger for the driver.

    This function is idempotent — calling it more than once has no effect.

    Parameters
    ----------
    log_level:
        Minimum severity level written to the rotating **file** handler
        (default: ``DEBUG``).
    console_level:
        Minimum severity level printed to the **console** (default: ``INFO``).
    log_dir:
        Directory where log files are stored.  Defaults to
        :data:`DEFAULT_LOG_DIR` inside the current working directory.
    log_filename:
        Base name of the log file (default: ``"d10_driver.log"``).
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger("d10_driver")
    root.setLevel(logging.DEBUG)  # capture everything; handlers filter

    # ------------------------------------------------------------------ #
    # File handler — full debug trace with rotation                        #
    # ------------------------------------------------------------------ #
    _log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / log_filename

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT))
    root.addHandler(file_handler)

    # ------------------------------------------------------------------ #
    # Console handler — human-friendly, optionally coloured               #
    # ------------------------------------------------------------------ #
    if _HAS_COLORLOG:
        console_formatter = colorlog.ColoredFormatter(
            COLOUR_LOG_FORMAT,
            log_colors=LOG_COLOURS,
        )
    else:
        console_formatter = logging.Formatter(CONSOLE_LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)

    _configured = True
    root.debug("Logging initialised — file: %s", log_path.resolve())


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``d10_driver`` namespace.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.  If the name does not
        already start with ``"d10_driver"``, the prefix is prepended so that
        every logger appears in the same hierarchy.

    Returns
    -------
    logging.Logger
        Configured child logger.
    """
    if not name.startswith("d10_driver"):
        name = f"d10_driver.{name}"
    return logging.getLogger(name)
