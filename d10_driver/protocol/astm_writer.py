"""
ASTM E1381 frame writer.

This module provides the :class:`ASTMWriter` class, which encodes Python
strings into ASTM E1381 framed byte sequences and transmits them over any
byte-stream transport.

Frame format (ASTM E1381 §4)
-----------------------------
::

    <STX> <FN> <data...> <ETX|ETB> <CS_hi> <CS_lo> <CR> <LF>

Large messages are automatically split into multiple frames of at most
:data:`~d10_driver.protocol.astm_constants.MAX_FRAME_DATA_LENGTH` bytes.

Usage
-----
::

    writer = ASTMWriter(transport)
    writer.send_message([header_record, patient_record, result_record])
"""

from __future__ import annotations

import time

from d10_driver.logging_utils.logger import get_logger
from d10_driver.protocol.astm_constants import (
    STX, ETX, ETB, EOT, ENQ, ACK, NAK, CR, LF,
    ACK_BYTE, NAK_BYTE,
    MAX_FRAME_DATA_LENGTH,
)

log = get_logger(__name__)


class ASTMWriter:
    """ASTM E1381 message writer.

    Encodes and transmits a list of ASTM records as a properly framed
    ASTM E1381 byte stream.

    Parameters
    ----------
    transport:
        Object with ``read(n: int) -> bytes`` and
        ``write(data: bytes) -> None`` methods.
    max_retries:
        Maximum number of retransmission attempts per frame when a NAK is
        received.
    ack_timeout:
        Seconds to wait for an ACK/NAK response after sending a frame.
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

    def send_message(self, records: list[str]) -> None:
        """Transmit *records* as a single ASTM message.

        Parameters
        ----------
        records:
            List of ASTM E1394 record strings (e.g. ``["H|…", "P|…", "L|1|N"]``).
            Each record is terminated with ``<CR>`` before transmission.

        Raises
        ------
        ValueError
            If the remote returns too many NAKs and the transmission cannot
            be completed.
        TimeoutError
            If no ACK/NAK is received within *ack_timeout* seconds.
        """
        # Join all records with <CR>
        payload = CR.decode() + CR.decode().join(records) + CR.decode()
        frames = self._split_into_frames(payload.encode("ascii"))

        log.debug("Sending ENQ to initiate transmission…")
        self._transport.write(ENQ)
        self._wait_for_ack("ENQ")

        frame_count = len(frames)
        for idx, (fn, data, is_last) in enumerate(frames):
            log.debug(
                "Sending frame %d/%d (seq=%d, last=%s)", idx + 1, frame_count, fn, is_last
            )
            self._send_frame(fn, data, is_last)

        log.debug("Sending EOT to finalise transmission.")
        self._transport.write(EOT)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _split_into_frames(
        self, payload: bytes
    ) -> list[tuple[int, bytes, bool]]:
        """Split *payload* into a list of ``(frame_number, data, is_last)`` tuples.

        Frame numbers cycle 1–7 per ASTM E1381 §4.1.4.
        """
        frames: list[tuple[int, bytes, bool]] = []
        offset = 0
        fn = 1
        while offset < len(payload):
            chunk = payload[offset: offset + MAX_FRAME_DATA_LENGTH]
            offset += MAX_FRAME_DATA_LENGTH
            is_last = offset >= len(payload)
            frames.append((fn, chunk, is_last))
            fn = (fn % 7) + 1
        return frames

    def _send_frame(self, fn: int, data: bytes, is_last: bool) -> None:
        """Build and transmit one frame, retrying on NAK.

        Parameters
        ----------
        fn:
            Frame sequence number (1–7).
        data:
            Raw data bytes for the frame body.
        is_last:
            If ``True``, the frame is terminated with ``ETX``; otherwise with
            ``ETB``.

        Raises
        ------
        ValueError
            After *max_retries* unsuccessful NAK responses.
        """
        terminator = ETX if is_last else ETB
        frame = self._build_frame(fn, data, terminator)

        for attempt in range(self._max_retries + 1):
            self._transport.write(frame)
            response = self._wait_for_ack(f"frame {fn} (attempt {attempt + 1})")
            if response == ACK_BYTE:
                return
            log.warning("NAK received for frame %d — retransmitting…", fn)

        raise ValueError(
            f"Frame {fn} was not acknowledged after {self._max_retries} retries."
        )

    @staticmethod
    def _build_frame(fn: int, data: bytes, terminator: bytes) -> bytes:
        """Construct the raw byte sequence for one ASTM E1381 frame.

        Parameters
        ----------
        fn:
            Frame sequence number (1–7).
        data:
            Frame data payload.
        terminator:
            Either ``ETX`` or ``ETB``.

        Returns
        -------
        bytes
            The complete frame including STX, FN, data, terminator,
            checksum, CR, and LF.
        """
        fn_byte = str(fn).encode("ascii")
        checksum_input = fn_byte + data + terminator
        total = sum(checksum_input) % 256
        cs = f"{total:02X}".encode("ascii")
        return STX + fn_byte + data + terminator + cs + CR + LF

    def _wait_for_ack(self, context: str) -> int:
        """Block until an ACK or NAK byte is received.

        Parameters
        ----------
        context:
            Human-readable label used in log messages.

        Returns
        -------
        int
            ``ACK_BYTE`` or ``NAK_BYTE``.

        Raises
        ------
        TimeoutError
            If no response arrives within *ack_timeout* seconds.
        """
        deadline = time.monotonic() + self._ack_timeout
        while True:
            chunk = self._transport.read(1)
            if chunk:
                b = chunk[0]
                if b in (ACK_BYTE, NAK_BYTE):
                    log.debug(
                        "Response to %s: %s",
                        context,
                        "ACK" if b == ACK_BYTE else "NAK",
                    )
                    return b
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Timeout waiting for ACK/NAK after sending {context}."
                )
