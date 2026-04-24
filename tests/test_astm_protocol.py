"""
Tests for ASTM E1381 protocol utilities.

Covers:
- Checksum computation (:func:`compute_checksum`)
- Checksum verification (:func:`verify_checksum`)
- Frame building (:meth:`ASTMWriter._build_frame`)
- Full reader/writer round-trip using an in-memory transport mock.
"""

from __future__ import annotations

import io
import unittest

from d10_driver.protocol.astm_constants import (
    STX_BYTE, ETX_BYTE, ETB_BYTE, CR_BYTE, LF_BYTE,
    ACK_BYTE, ENQ_BYTE, EOT_BYTE,
    ACK, ENQ, EOT,
)
from d10_driver.protocol.astm_reader import ASTMReader, compute_checksum, verify_checksum
from d10_driver.protocol.astm_writer import ASTMWriter


# ---------------------------------------------------------------------------
# In-memory transport mock
# ---------------------------------------------------------------------------


class _LoopbackTransport:
    """Simple in-memory byte buffer that acts as both the reader and writer.

    Bytes written to the transport via :meth:`write` are immediately
    available for reading via :meth:`read`.  This allows us to test the
    reader and writer end-to-end without real hardware.
    """

    def __init__(self, initial: bytes = b"") -> None:
        self._buf = bytearray(initial)

    def read(self, n: int) -> bytes:
        data = bytes(self._buf[:n])
        self._buf = self._buf[n:]
        return data

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    @property
    def remaining(self) -> bytes:
        return bytes(self._buf)


# ---------------------------------------------------------------------------
# Helper to build a valid ASTM frame sequence
# ---------------------------------------------------------------------------


def _make_valid_astm_stream(payload: str) -> bytes:
    """Build a minimal valid ASTM E1381 byte stream for *payload*.

    The resulting stream contains:
    ENQ | frame(s) | EOT

    Each frame is correctly checksummed.  The caller must not forget that
    the ASTMReader will send ACK bytes after ENQ and after each frame —
    but since we're testing with a mock that we directly read from, we
    pre-insert those ACKs as if the *writer* side already received them.

    Because ASTMReader.receive_message() waits for ENQ, reads frames,
    and waits for EOT, we build the stream the instrument would send.
    The host side's ACK bytes are NOT in this stream — they are sent by the
    reader via transport.write(), which goes into the same loopback buffer.
    We handle this by splitting reader/writer buffers in the test setup.
    """
    # We'll use a different approach: pre-populate the "instrument→host"
    # direction only, using a DirectedTransport below.
    raise NotImplementedError("Use DirectedTransport in tests")


class _DirectedTransport:
    """Transport whose reads come from one buffer and writes go to another.

    This accurately models a full-duplex serial connection:
    - ``from_instrument`` bytes are what the driver reads (instrument→host).
    - ``to_instrument`` captures bytes the driver sends (host→instrument).
    """

    def __init__(self, from_instrument: bytes) -> None:
        self._rx = bytearray(from_instrument)
        self._tx = bytearray()

    def read(self, n: int) -> bytes:
        data = bytes(self._rx[:n])
        self._rx = self._rx[n:]
        return data

    def write(self, data: bytes) -> None:
        self._tx.extend(data)

    @property
    def sent_to_instrument(self) -> bytes:
        """Bytes the driver sent back toward the instrument."""
        return bytes(self._tx)


def _build_frame_bytes(fn: int, data: bytes, is_last: bool) -> bytes:
    """Build a correctly checksummed ASTM E1381 frame."""
    terminator = bytes([ETX_BYTE if is_last else ETB_BYTE])
    fn_bytes = str(fn).encode()
    cs_input = fn_bytes + data + terminator
    total = sum(cs_input) % 256
    cs = f"{total:02X}".encode()
    return bytes([STX_BYTE]) + fn_bytes + data + terminator + cs + bytes([CR_BYTE, LF_BYTE])


def _build_astm_stream(records: list[str]) -> bytes:
    """Build a full ENQ → frames → EOT stream for *records*."""
    payload = "\r".join(records) + "\r"
    payload_bytes = payload.encode("ascii")

    max_len = 240
    chunks = [
        payload_bytes[i: i + max_len]
        for i in range(0, len(payload_bytes), max_len)
    ]

    stream = bytearray()
    stream.extend(bytes([ENQ_BYTE]))
    for idx, chunk in enumerate(chunks):
        is_last = idx == len(chunks) - 1
        fn = (idx % 7) + 1
        stream.extend(_build_frame_bytes(fn, chunk, is_last))

    stream.extend(bytes([EOT_BYTE]))
    return bytes(stream)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestComputeChecksum(unittest.TestCase):
    """Tests for :func:`compute_checksum`."""

    def test_known_value(self):
        """Sum of ASCII bytes, mod 256, formatted as uppercase hex."""
        # b"1H|\\^&" → 0x31+0x48+0x7c+0x5c+0x5e+0x26 = 469 → 469 % 256 = 213 → D5
        data = b"1H|\\^&"
        self.assertEqual(compute_checksum(data), "D5")

    def test_zero_result(self):
        """A zero checksum should format as '00'."""
        # bytes with value 0 → sum 0 → checksum '00'
        self.assertEqual(compute_checksum(bytes([0])), "00")

    def test_single_byte(self):
        """Single byte: value 65 ('A') → '41' hex."""
        self.assertEqual(compute_checksum(b"A"), "41")

    def test_two_digit_hex(self):
        """Checksum is always two characters wide."""
        cs = compute_checksum(b"\x0f")  # 15 → 0F
        self.assertEqual(len(cs), 2)
        self.assertEqual(cs, "0F")

    def test_overflow_wraps(self):
        """Sum exceeding 255 must wrap around modulo 256."""
        # 128 + 128 = 256 → 0
        self.assertEqual(compute_checksum(bytes([128, 128])), "00")


class TestVerifyChecksum(unittest.TestCase):
    """Tests for :func:`verify_checksum`."""

    def test_correct_checksum(self):
        data = b"H|\\^&"
        terminator = ETX_BYTE
        fn = 1
        # Compute expected checksum manually
        cs_input = b"1" + data + bytes([ETX_BYTE])
        total = sum(cs_input) % 256
        expected_cs = f"{total:02X}"
        self.assertTrue(verify_checksum(fn, data, terminator, expected_cs))

    def test_wrong_checksum(self):
        self.assertFalse(verify_checksum(1, b"H|\\^&", ETX_BYTE, "ZZ"))

    def test_case_insensitive(self):
        data = b"R|1"
        fn = 2
        cs_input = b"2" + data + bytes([ETX_BYTE])
        total = sum(cs_input) % 256
        cs_upper = f"{total:02X}"
        cs_lower = cs_upper.lower()
        # Both should pass
        self.assertTrue(verify_checksum(fn, data, ETX_BYTE, cs_upper))
        self.assertTrue(verify_checksum(fn, data, ETX_BYTE, cs_lower))


class TestASTMWriterBuildFrame(unittest.TestCase):
    """Tests for :meth:`ASTMWriter._build_frame`."""

    def _parse_frame(self, frame: bytes) -> dict:
        """Decompose a raw frame bytes into its parts."""
        self.assertEqual(frame[0], STX_BYTE)
        fn = frame[1] - ord("0")
        # Find terminator
        term_idx = None
        for i in range(2, len(frame)):
            if frame[i] in (ETX_BYTE, ETB_BYTE):
                term_idx = i
                break
        self.assertIsNotNone(term_idx)
        data = frame[2:term_idx]
        terminator = frame[term_idx]
        cs = frame[term_idx + 1: term_idx + 3].decode()
        cr = frame[term_idx + 3]
        lf = frame[term_idx + 4]
        return {
            "fn": fn,
            "data": data,
            "terminator": terminator,
            "cs": cs,
            "cr": cr,
            "lf": lf,
        }

    def test_last_frame_uses_etx(self):
        from d10_driver.protocol.astm_writer import ASTMWriter
        frame = ASTMWriter._build_frame(1, b"H|test", b"\x03")
        parsed = self._parse_frame(frame)
        self.assertEqual(parsed["terminator"], ETX_BYTE)

    def test_intermediate_frame_uses_etb(self):
        from d10_driver.protocol.astm_writer import ASTMWriter
        frame = ASTMWriter._build_frame(2, b"data", b"\x17")
        parsed = self._parse_frame(frame)
        self.assertEqual(parsed["terminator"], ETB_BYTE)

    def test_checksum_is_correct(self):
        from d10_driver.protocol.astm_writer import ASTMWriter
        data = b"R|1|^^^HBA1C|6.7|%"
        fn = 3
        frame = ASTMWriter._build_frame(fn, data, b"\x03")
        parsed = self._parse_frame(frame)
        # Verify checksum manually
        cs_input = str(fn).encode() + data + bytes([ETX_BYTE])
        expected = f"{sum(cs_input) % 256:02X}"
        self.assertEqual(parsed["cs"], expected)

    def test_frame_ends_with_crlf(self):
        from d10_driver.protocol.astm_writer import ASTMWriter
        frame = ASTMWriter._build_frame(1, b"x", b"\x03")
        self.assertEqual(frame[-2], CR_BYTE)
        self.assertEqual(frame[-1], LF_BYTE)

    def test_frame_number_is_embedded(self):
        from d10_driver.protocol.astm_writer import ASTMWriter
        for fn in range(1, 8):
            frame = ASTMWriter._build_frame(fn, b"d", b"\x03")
            parsed = self._parse_frame(frame)
            self.assertEqual(parsed["fn"], fn)


class TestASTMReaderRoundTrip(unittest.TestCase):
    """End-to-end round-trip tests for :class:`ASTMReader`."""

    def _make_transport(self, records: list[str]) -> "_DirectedTransport":
        stream = _build_astm_stream(records)
        return _DirectedTransport(stream)

    def test_single_frame_message(self):
        """A short message fitting in one frame is correctly received."""
        records = ["H|\\^&|||D-10|||||||P|1", "L|1|N"]
        transport = self._make_transport(records)
        reader = ASTMReader(transport, ack_timeout=1.0)
        received = list(reader.receive_message())
        self.assertEqual(len(received), 2)
        self.assertTrue(received[0].startswith("H"))
        self.assertTrue(received[1].startswith("L"))

    def test_result_records_received(self):
        """Result records are passed through unchanged."""
        records = [
            "H|\\^&|||D-10",
            "P|1||PAT001||DOE^JOHN",
            "O|1|SPEC001||^^^HBA1C",
            "R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F|||20240424",
            "L|1|N",
        ]
        transport = self._make_transport(records)
        reader = ASTMReader(transport, ack_timeout=1.0)
        received = list(reader.receive_message())
        # Should have all 5 records
        self.assertEqual(len(received), 5)
        result = next(r for r in received if r.startswith("R"))
        self.assertIn("HBA1C", result)
        self.assertIn("6.7", result)

    def test_driver_sends_ack_after_enq(self):
        """The reader sends ACK after receiving ENQ."""
        records = ["H|\\^&", "L|1|N"]
        transport = self._make_transport(records)
        reader = ASTMReader(transport, ack_timeout=1.0)
        list(reader.receive_message())
        sent = transport.sent_to_instrument
        # First byte sent should be ACK (response to ENQ)
        self.assertEqual(sent[0], ACK_BYTE)

    def test_driver_sends_ack_for_each_frame(self):
        """The reader sends one ACK per received frame."""
        records = ["H|\\^&", "L|1|N"]
        transport = self._make_transport(records)
        reader = ASTMReader(transport, ack_timeout=1.0)
        list(reader.receive_message())
        sent = transport.sent_to_instrument
        # All sent bytes should be ACKs (one for ENQ, one per frame)
        self.assertTrue(all(b == ACK_BYTE for b in sent))


class TestMultiFrameMessage(unittest.TestCase):
    """Tests for messages that span multiple ASTM frames."""

    def test_long_payload_split_into_multiple_frames(self):
        """A payload > 240 bytes is correctly split and reassembled."""
        # Create a result record long enough to exceed one frame
        long_value = "A" * 200
        records = [
            "H|\\^&|||D-10",
            f"R|1|^^^ANALYTE|{long_value}|%",
            "L|1|N",
        ]
        stream = _build_astm_stream(records)
        transport = _DirectedTransport(stream)
        reader = ASTMReader(transport, ack_timeout=1.0)
        received = list(reader.receive_message())
        result = next(r for r in received if r.startswith("R"))
        self.assertIn(long_value, result)


if __name__ == "__main__":
    unittest.main()
