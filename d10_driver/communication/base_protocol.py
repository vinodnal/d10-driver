"""
Abstract base class for communication transport protocols.

All concrete transport implementations (serial, TCP, …) must subclass
:class:`BaseProtocol` and implement the three abstract methods.

This abstraction ensures the rest of the driver is transport-agnostic and
new communication channels can be added without touching any other module.
"""

from __future__ import annotations

import abc
from typing import Optional

from d10_driver.logging_utils.logger import get_logger

log = get_logger(__name__)


class BaseProtocol(abc.ABC):
    """Abstract byte-stream transport for ASTM communication.

    Subclasses must implement:

    - :meth:`open` — open/connect the transport.
    - :meth:`close` — release resources.
    - :meth:`read` — read bytes from the transport.
    - :meth:`write` — write bytes to the transport.

    The class also implements the *context manager* protocol so transports can
    be used with ``with`` statements::

        with SerialProtocol(port="/dev/ttyUSB0") as transport:
            reader = ASTMReader(transport)
            …
    """

    def __init__(self, *, name: str = "transport") -> None:
        self._name = name
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def open(self) -> None:
        """Open the transport and prepare it for I/O."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the transport and release all resources."""

    @abc.abstractmethod
    def read(self, n: int) -> bytes:
        """Read up to *n* bytes from the transport.

        Parameters
        ----------
        n:
            Maximum number of bytes to read.

        Returns
        -------
        bytes
            The bytes read; may be fewer than *n* or empty on timeout.
        """

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Write *data* to the transport.

        Parameters
        ----------
        data:
            Raw bytes to transmit.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """``True`` if the transport is currently open."""
        return self._connected

    @property
    def name(self) -> str:
        """Human-readable name / identifier for this transport."""
        return self._name

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "BaseProtocol":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False  # do not suppress exceptions

    def __repr__(self) -> str:
        status = "open" if self._connected else "closed"
        return f"<{self.__class__.__name__} name={self._name!r} status={status}>"
