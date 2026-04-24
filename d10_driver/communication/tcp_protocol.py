"""
TCP/IP transport for ASTM communication.

This module provides :class:`TCPProtocol`, a concrete implementation of
:class:`~d10_driver.communication.base_protocol.BaseProtocol` that communicates
over a TCP/IP socket.  Some modern laboratory analysers (including certain
Bio-Rad models with optional Ethernet interfaces) expose an ASTM stream over
a plain TCP socket, making this transport a drop-in replacement for the serial
variant.

Usage
-----
::

    from d10_driver.communication.tcp_protocol import TCPProtocol

    transport = TCPProtocol(host="192.168.1.50", port=5000, timeout=10)
    with transport:
        reader = ASTMReader(transport)
        …
"""

from __future__ import annotations

import socket

from d10_driver.communication.base_protocol import BaseProtocol
from d10_driver.logging_utils.logger import get_logger

log = get_logger(__name__)

#: Default TCP receive buffer size in bytes.
_RECV_BUFFER = 4096


class TCPProtocol(BaseProtocol):
    """TCP/IP transport implementing :class:`BaseProtocol`.

    Parameters
    ----------
    host:
        Hostname or IP address of the instrument or middleware server.
    port:
        TCP port number.
    timeout:
        Socket operation timeout in seconds (default: 10).
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(name=f"tcp:{host}:{port}")
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._recv_buffer: bytes = b""

    # ------------------------------------------------------------------
    # BaseProtocol implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Connect to the remote host.

        Raises
        ------
        ConnectionRefusedError
            If the remote host actively refuses the connection.
        OSError
            For any other socket-level error.
        """
        log.info("Connecting TCP transport to %s:%d…", self._host, self._port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)
        self._sock.connect((self._host, self._port))
        self._connected = True
        log.info("TCP connection to %s:%d established.", self._host, self._port)

    def close(self) -> None:
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # already closed or not connected
            self._sock.close()
            log.info("TCP connection to %s:%d closed.", self._host, self._port)
        self._sock = None
        self._connected = False
        self._recv_buffer = b""

    def read(self, n: int) -> bytes:
        """Read up to *n* bytes from the TCP stream.

        Uses an internal byte buffer to satisfy short reads without
        additional round-trips to the kernel.

        Parameters
        ----------
        n:
            Maximum number of bytes to return.

        Returns
        -------
        bytes
            Between 0 and *n* bytes; empty on timeout.
        """
        if not self._sock:
            raise IOError("TCP socket is not connected.")

        # Serve from internal buffer first
        if len(self._recv_buffer) >= n:
            data, self._recv_buffer = self._recv_buffer[:n], self._recv_buffer[n:]
            log.debug("RX(%d) [buffered]: %s", len(data), data.hex(" ").upper())
            return data

        try:
            chunk = self._sock.recv(_RECV_BUFFER)
        except socket.timeout:
            return b""
        except OSError as exc:
            log.error("TCP read error: %s", exc)
            return b""

        self._recv_buffer += chunk
        data, self._recv_buffer = (
            self._recv_buffer[:n],
            self._recv_buffer[n:],
        )
        if data:
            log.debug("RX(%d): %s", len(data), data.hex(" ").upper())
        return data

    def write(self, data: bytes) -> None:
        """Send *data* over the TCP connection.

        Parameters
        ----------
        data:
            Bytes to transmit.

        Raises
        ------
        IOError
            If the socket is not connected.
        """
        if not self._sock:
            raise IOError("TCP socket is not connected.")
        log.debug("TX(%d): %s", len(data), data.hex(" ").upper())
        self._sock.sendall(data)

    # ------------------------------------------------------------------
    # Additional properties
    # ------------------------------------------------------------------

    @property
    def host(self) -> str:
        """Remote host address."""
        return self._host

    @property
    def port_number(self) -> int:
        """Remote TCP port."""
        return self._port
