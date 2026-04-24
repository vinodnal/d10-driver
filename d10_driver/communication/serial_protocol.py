"""
RS-232 serial transport for ASTM E1381 communication.

This module provides :class:`SerialProtocol`, a concrete implementation of
:class:`~d10_driver.communication.base_protocol.BaseProtocol` that communicates
over a physical RS-232 serial port using the *pyserial* library.

The Bio-Rad D-10 default serial settings are:

====== =====
Parameter Value
====== =====
Baud rate 9600
Data bits 8
Parity None
Stop bits 1
Flow control None
====== =====

Usage
-----
::

    from d10_driver.communication.serial_protocol import SerialProtocol

    transport = SerialProtocol(
        port="/dev/ttyUSB0",
        baud_rate=9600,
        timeout=5,
    )
    with transport:
        # transport.read(1) / transport.write(b"\\x06") etc.
        …
"""

from __future__ import annotations

from d10_driver.communication.base_protocol import BaseProtocol
from d10_driver.logging_utils.logger import get_logger

log = get_logger(__name__)


class SerialProtocol(BaseProtocol):
    """RS-232 serial transport implementing :class:`BaseProtocol`.

    Parameters
    ----------
    port:
        Serial device path (e.g. ``"/dev/ttyUSB0"`` or ``"COM3"``).
    baud_rate:
        Communication speed in bits per second (default: 9600).
    data_bits:
        Number of data bits per byte (default: 8).
    parity:
        Parity checking: ``"N"`` (none), ``"E"`` (even), ``"O"`` (odd).
    stop_bits:
        Number of stop bits: 1 or 2.
    timeout:
        Read timeout in seconds.  A value of ``None`` makes reads block
        indefinitely.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        *,
        baud_rate: int = 9600,
        data_bits: int = 8,
        parity: str = "N",
        stop_bits: int = 1,
        timeout: float = 5.0,
    ) -> None:
        super().__init__(name=f"serial:{port}")
        self._port = port
        self._baud_rate = baud_rate
        self._data_bits = data_bits
        self._parity = parity
        self._stop_bits = stop_bits
        self._timeout = timeout
        self._serial = None  # set in open()

    # ------------------------------------------------------------------
    # BaseProtocol implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port.

        Raises
        ------
        serial.SerialException
            If the port cannot be opened (e.g. device not found, permission
            denied).
        """
        import serial  # imported lazily so pyserial is optional in test envs

        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
        }
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            2: serial.STOPBITS_TWO,
        }

        log.info(
            "Opening serial port %s @ %d baud (%dN%d)",
            self._port, self._baud_rate, self._data_bits, self._stop_bits,
        )
        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baud_rate,
            bytesize=self._data_bits,
            parity=parity_map.get(self._parity.upper(), serial.PARITY_NONE),
            stopbits=stopbits_map.get(self._stop_bits, serial.STOPBITS_ONE),
            timeout=self._timeout,
        )
        self._connected = True
        log.info("Serial port %s opened successfully.", self._port)

    def close(self) -> None:
        """Close the serial port and release the device."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            log.info("Serial port %s closed.", self._port)
        self._connected = False
        self._serial = None

    def read(self, n: int) -> bytes:
        """Read up to *n* bytes from the serial port.

        Parameters
        ----------
        n:
            Maximum number of bytes to read.

        Returns
        -------
        bytes
            Bytes read; may be fewer than *n* or empty on timeout.
        """
        if not self._serial or not self._serial.is_open:
            raise IOError("Serial port is not open.")
        data = self._serial.read(n)
        if data:
            log.debug("RX(%d): %s", len(data), data.hex(" ").upper())
        return data

    def write(self, data: bytes) -> None:
        """Write *data* to the serial port.

        Parameters
        ----------
        data:
            Bytes to transmit.
        """
        if not self._serial or not self._serial.is_open:
            raise IOError("Serial port is not open.")
        log.debug("TX(%d): %s", len(data), data.hex(" ").upper())
        self._serial.write(data)
        self._serial.flush()

    # ------------------------------------------------------------------
    # Additional helpers
    # ------------------------------------------------------------------

    @property
    def port(self) -> str:
        """The serial port device path."""
        return self._port

    @property
    def baud_rate(self) -> int:
        """The configured baud rate."""
        return self._baud_rate

    def flush_input(self) -> None:
        """Discard any bytes waiting in the input buffer."""
        if self._serial and self._serial.is_open:
            self._serial.reset_input_buffer()
            log.debug("Input buffer flushed on %s", self._port)
