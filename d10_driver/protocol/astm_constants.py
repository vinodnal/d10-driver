"""
ASTM E1381 / E1394 protocol constants.

This module defines every control character, delimiter, and record-type
identifier referenced by the ASTM E1381 (low-level framing) and
ASTM E1394 (high-level message content) standards.

References
----------
- ASTM E1381-02 "Standard Specification for Low-Level Protocol to Transfer
  Messages Between Clinical Laboratory Instruments and Computer Systems"
- ASTM E1394-97(2011) "Standard Specification for Transferring Information
  Between Clinical Instruments and Computer Systems"
"""

# ---------------------------------------------------------------------------
# Control characters (ASCII)
# ---------------------------------------------------------------------------

#: Start of Text — marks the beginning of an ASTM frame payload.
STX: bytes = b"\x02"

#: End of Text — marks the end of the last frame in an ASTM message.
ETX: bytes = b"\x03"

#: End of Transmission — signals that the sender has finished all messages.
EOT: bytes = b"\x04"

#: Enquiry — sent by the instrument to request the host's attention.
ENQ: bytes = b"\x05"

#: Acknowledge — positive response to a frame.
ACK: bytes = b"\x06"

#: Line Feed.
LF: bytes = b"\x0A"

#: Carriage Return — used as the record separator inside ASTM messages.
CR: bytes = b"\x0D"

#: End of Transmission Block — marks the end of an intermediate frame.
ETB: bytes = b"\x17"

#: Negative Acknowledge — signals a transmission error; requests resend.
NAK: bytes = b"\x15"

# ---------------------------------------------------------------------------
# Integer equivalents (useful for arithmetic operations)
# ---------------------------------------------------------------------------

STX_BYTE: int = 0x02
ETX_BYTE: int = 0x03
EOT_BYTE: int = 0x04
ENQ_BYTE: int = 0x05
ACK_BYTE: int = 0x06
LF_BYTE: int = 0x0A
CR_BYTE: int = 0x0D
ETB_BYTE: int = 0x17
NAK_BYTE: int = 0x15

# ---------------------------------------------------------------------------
# ASTM E1381 framing parameters
# ---------------------------------------------------------------------------

#: Maximum number of data characters per frame (excluding framing bytes).
MAX_FRAME_DATA_LENGTH: int = 240

#: Valid frame sequence numbers (1–7, cycling).
VALID_FRAME_NUMBERS: tuple = (1, 2, 3, 4, 5, 6, 7)

# ---------------------------------------------------------------------------
# ASTM E1394 field delimiters
# ---------------------------------------------------------------------------

#: Primary field delimiter.
FIELD_DELIMITER: str = "|"

#: Repeat field delimiter.
REPEAT_DELIMITER: str = "\\"

#: Component field delimiter.
COMPONENT_DELIMITER: str = "^"

#: Escape character.
ESCAPE_CHARACTER: str = "&"

# ---------------------------------------------------------------------------
# ASTM E1394 record type identifiers
# ---------------------------------------------------------------------------

#: Message Header record.
RECORD_HEADER: str = "H"

#: Patient Information record.
RECORD_PATIENT: str = "P"

#: Test Order record.
RECORD_ORDER: str = "O"

#: Result record.
RECORD_RESULT: str = "R"

#: Scientific record (instrument-specific data).
RECORD_SCIENTIFIC: str = "S"

#: Comment record.
RECORD_COMMENT: str = "C"

#: Query record.
RECORD_QUERY: str = "Q"

#: Manufacturer Information record.
RECORD_MANUFACTURER: str = "M"

#: Message Terminator record.
RECORD_TERMINATOR: str = "L"

# ---------------------------------------------------------------------------
# Processing IDs (ASTM E1394 §8.4.3)
# ---------------------------------------------------------------------------

#: Routine production order.
PROCESSING_ID_PRODUCTION: str = "P"

#: Quality control order.
PROCESSING_ID_QC: str = "Q"

#: Calibration order.
PROCESSING_ID_CALIBRATION: str = "C"

# ---------------------------------------------------------------------------
# Result status codes (ASTM E1394 §9.6.8)
# ---------------------------------------------------------------------------

#: Final result.
RESULT_STATUS_FINAL: str = "F"

#: Correction of previously transmitted result.
RESULT_STATUS_CORRECTION: str = "C"

#: Preliminary result (instrument still processing).
RESULT_STATUS_PRELIMINARY: str = "P"

#: Result deleted.
RESULT_STATUS_DELETED: str = "D"

#: Specimen in lab; results pending.
RESULT_STATUS_IN_LAB: str = "I"

#: Result entered — not yet verified.
RESULT_STATUS_NOT_VERIFIED: str = "S"

# ---------------------------------------------------------------------------
# Abnormal flag codes (ASTM E1394 §9.6.7)
# ---------------------------------------------------------------------------

#: Above high normal.
ABNORMAL_HIGH: str = "H"

#: Above panic high.
ABNORMAL_PANIC_HIGH: str = "HH"

#: Below low normal.
ABNORMAL_LOW: str = "L"

#: Below panic low.
ABNORMAL_PANIC_LOW: str = "LL"

#: Abnormal (no direction specified).
ABNORMAL_ABNORMAL: str = "A"

#: Normal.
ABNORMAL_NORMAL: str = "N"

# ---------------------------------------------------------------------------
# Bio-Rad D-10 specific test identifiers
# ---------------------------------------------------------------------------

#: Universal test identifier prefix for HbA1c (LOINC 59261-8).
D10_TEST_HBA1C: str = "HBA1C"

#: Haemoglobin variants reported by the D-10.
D10_ANALYTES: tuple = (
    "A0",        # HbA0 (unglycated haemoglobin)
    "A1c",       # HbA1c
    "A2",        # HbA2
    "F",         # HbF (foetal haemoglobin)
    "S",         # HbS (sickle cell trait)
    "C",         # HbC
    "Unknown",   # Unidentified peaks
)
