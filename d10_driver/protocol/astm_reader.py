"""
ASTM E1381 frame reader.

This module implements the low-level ASTM E1381 receive state-machine that
reassembles frames received over a byte-stream transport (serial or TCP).

Frame format (ASTM E1381 §4)
-----------------------------
::

    <STX> <FN> <data...> <ETX|ETB> <CS_hi> <CS_lo> <CR> <LF>

Where:

- ``STX``   — 0x02, marks the start of a frame.
- ``FN``    — ASCII digit 1–7 (frame sequence number, cycling).
- ``data``  — up to 240 ASCII characters of record content.
- ``ETX``   — 0x03, end of the *last* frame in a logical record.
- ``ETB``   — 0x17, end of an *intermediate* frame (more frames follow).
- ``CS``    — two ASCII uppercase hex characters.  The checksum is the
              sum (mod 256) of all bytes from ``FN`` through ``ETX``/``ETB``
              inclusive.
- ``CR LF`` — frame terminator.

Inter-frame handshake
---------------------
After each frame the host must send ``ACK`` (0x06) or ``NAK`` (0x15).

Usage
-----
::

    reader = ASTMReader(transport)
    for record in reader.receive_message():
        print(record)
"""

from __future__ import annotations

import time
from typing import Generator, Optional

from d10_driver.logging_utils.logger import get_logger
from d10_driver.protocol.astm_constants import (
    ACK, NAK,
    STX_BYTE, ETX_BYTE, ETB_BYTE, EOT_BYTE, ENQ_BYTE, CR_BYTE, LF_BYTE,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Checksum helper
# ---------------------------------------------------------------------------


def compute_checksum(data: bytes) -> str:
    """Return the ASTM E1381 checksum for *data* as two uppercase hex digits.

    The checksum is the arithmetic sum of all byte values modulo 256, expressed
    as exactly two uppercase hexadecimal characters (e.g. ``"4E"``).

    Parameters
    ----------
    data:
        Bytes from the frame number (``FN``) up to and including ``ETX``
        or ``ETB`` (per ASTM E1381 §7.2).

    Returns
    -------
    str
        Two-character uppercase hex checksum string.
    """
    total = sum(data) % 256
    return f"{total:02X}"


def verify_checksum(frame_number: int, data: bytes, terminator: int,
                    received_cs: str) -> bool:
    """Verify the checksum of a received frame.

    Parameters
    ----------
    frame_number:
        The numeric frame sequence number (1–7).
    data:
        Raw data bytes of the frame (between ``FN`` and the terminator).
    terminator:
        The terminator byte value (``ETX_BYTE`` or ``ETB_BYTE``).
    received_cs:
        The two-character checksum string received in the frame.

    Returns
    -------
    bool
        ``True`` if the computed checksum matches *received_cs*.
    """
    checksum_input = (
        bytes([ord(str(frame_number))]) + data + bytes([terminator])
    )
    expected = compute_checksum(checksum_input)
    ok = expected == received_cs.upper()
    if not ok:
        log.warning(
            "Checksum mismatch: expected %s, received %s", expected, received_cs
        )
    return ok


# ---------------------------------------------------------------------------
# Main reader class
# ---------------------------------------------------------------------------


class ASTMReader:
    """ASTM E1381 message reader.

    Reads a complete ASTM *message* (one or more frames) from the underlying
    *transport*, validates checksums, handles retransmission, and yields the
    decoded text records.

    Parameters
    ----------
    transport:
        Any object that exposes ``read(n: int) -> bytes`` and
        ``write(data: bytes) -> None`` methods — typically a
        :class:`~d10_driver.communication.serial_protocol.SerialProtocol` or
        :class:`~d10_driver.communication.tcp_protocol.TCPProtocol` instance.
    max_retries:
        Number of NAK retransmission attempts per frame before giving up.
    ack_timeout:
        Seconds to wait for the instrument to send the next byte before
        raising :exc:`TimeoutError`.
    """

    def __init__(
        self,
        transport,
        *,
        max_retries: int = 3,
        ack_timeout: float = 10.0,
    ) -> None:
        self._transport = transport
        self._max_retries = max_retries
        self._ack_timeout = ack_timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def receive_message(self) -> Generator[str, None, None]:
        """Block until a full ASTM message is received, then yield records.

        The generator yields one string per ASTM logical record (e.g. the
        text content of an ``H``, ``P``, ``O``, ``R``, or ``L`` record).
        Records that span multiple frames are reassembled transparently.

        Yields
        ------
        str
            Decoded ASCII text of each logical ASTM record.

        Raises
        ------
        TimeoutError
            If no byte arrives within *ack_timeout* seconds.
        ValueError
            If an unrecoverable protocol error occurs (e.g. too many NAKs).
        """
        log.debug("Waiting for ENQ from instrument…")
        self._wait_for_enq()

        log.debug("ENQ received — sending ACK")
        self._transport.write(ACK)

        message_buffer: list[str] = []
        expected_frame = 1

        while True:
            frame_text, is_last, ok = self._read_frame(expected_frame)
            if not ok:
                # Unrecoverable after max retries
                raise ValueError(
                    "Unrecoverable ASTM framing error after retransmissions."
                )

            # Acknowledge the frame
            self._transport.write(ACK)
            log.debug("Frame %d received (%d bytes)", expected_frame, len(frame_text))

            message_buffer.append(frame_text)

            if is_last:
                # Reassemble and split into logical records at <CR>
                full_text = "".join(message_buffer)
                for record in full_text.split("\r"):
                    stripped = record.strip()
                    if stripped:
                        yield stripped
                message_buffer.clear()
                log.debug("End of ASTM message (ETX received).")
                break

            # Advance frame number (cycles 1–7)
            expected_frame = (expected_frame % 7) + 1

        # Wait for EOT
        self._wait_for_eot()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _wait_for_enq(self) -> None:
        """Block until an ENQ byte is received from the instrument."""
        deadline = time.monotonic() + self._ack_timeout
        while True:
            byte = self._transport.read(1)
            if byte and byte[0] == ENQ_BYTE:
                return
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Timeout waiting for ENQ from instrument."
                )

    def _wait_for_eot(self) -> None:
        """Block until an EOT byte is received."""
        deadline = time.monotonic() + self._ack_timeout
        while True:
            byte = self._transport.read(1)
            if byte and byte[0] == EOT_BYTE:
                log.debug("EOT received — transmission complete.")
                return
            if time.monotonic() > deadline:
                log.warning("Timeout waiting for EOT; continuing anyway.")
                return

    def _read_frame(
        self, expected_fn: int
    ) -> tuple[str, bool, bool]:
        """Read and validate a single ASTM E1381 frame.

        Parameters
        ----------
        expected_fn:
            The expected frame sequence number (1–7).

        Returns
        -------
        tuple[str, bool, bool]
            ``(text, is_last_frame, checksum_ok)`` where *text* is the
            decoded frame payload, *is_last_frame* is ``True`` when the frame
            ended with ``ETX``, and *checksum_ok* indicates whether the
            checksum was valid after up to *max_retries* attempts.
        """
        for attempt in range(self._max_retries + 1):
            try:
                text, is_last, cs_ok = self._parse_one_frame(expected_fn)
                if cs_ok:
                    return text, is_last, True
                # Checksum error — request retransmission
                log.warning("Checksum error on attempt %d — sending NAK", attempt + 1)
                self._transport.write(NAK)
            except TimeoutError:
                log.error("Timeout reading frame — sending NAK")
                self._transport.write(NAK)

        return "", False, False

    def _parse_one_frame(self, expected_fn: int) -> tuple[str, bool, bool]:
        """Parse the next frame from the transport byte stream.

        Returns
        -------
        tuple[str, bool, bool]
            ``(text, is_last, checksum_ok)``

        Raises
        ------
        TimeoutError
            If a byte is not received within the timeout.
        """
        deadline = time.monotonic() + self._ack_timeout

        # Wait for STX
        while True:
            b = self._read_byte(deadline)
            if b == STX_BYTE:
                break

        # Read frame number
        fn_byte = self._read_byte(deadline)
        fn_char = chr(fn_byte)

        # Read data until ETX or ETB
        raw_data = bytearray()
        terminator: Optional[int] = None
        while True:
            b = self._read_byte(deadline)
            if b in (ETX_BYTE, ETB_BYTE):
                terminator = b
                break
            raw_data.append(b)

        is_last = (terminator == ETX_BYTE)

        # Read two checksum characters
        cs_hi = chr(self._read_byte(deadline))
        cs_lo = chr(self._read_byte(deadline))
        received_cs = cs_hi + cs_lo

        # Read CR LF
        self._read_byte(deadline)  # CR
        self._read_byte(deadline)  # LF

        # Validate frame number
        try:
            fn = int(fn_char)
        except ValueError:
            log.warning("Invalid frame number character: %r", fn_char)
            return "", is_last, False

        if fn != expected_fn:
            log.warning("Frame number mismatch: expected %d, got %d", expected_fn, fn)

        # Validate checksum
        cs_ok = verify_checksum(fn, bytes(raw_data), terminator, received_cs)

        text = raw_data.decode("ascii", errors="replace")
        return text, is_last, cs_ok

    def _read_byte(self, deadline: float) -> int:
        """Read exactly one byte from the transport, respecting *deadline*.

        Parameters
        ----------
        deadline:
            ``time.monotonic()`` value at which to raise :exc:`TimeoutError`.

        Returns
        -------
        int
            The byte value (0–255).

        Raises
        ------
        TimeoutError
            If no byte arrives before *deadline*.
        """
        while True:
            chunk = self._transport.read(1)
            if chunk:
                return chunk[0]
            if time.monotonic() > deadline:
                raise TimeoutError("Timeout reading from transport.")
