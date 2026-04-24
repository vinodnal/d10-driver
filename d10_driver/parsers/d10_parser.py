"""
Bio-Rad D-10 specific ASTM E1394 message parser.

This module provides :class:`D10Parser`, a concrete implementation of
:class:`~d10_driver.parsers.base_parser.BaseParser` tuned to the exact
field layout produced by the Bio-Rad D-10 hemoglobin analyzer.

The D-10 transmits one ASTM message per patient run, typically consisting of:

1. **H** — Header (instrument ID, processing ID, datetime).
2. **P** — Patient demographics.
3. **O** — Specimen/order information.
4. **R** (×N) — One result record per haemoglobin fraction.
5. **L** — Message terminator.

Field positions documented here are 1-based (as per the ASTM standard) but
the implementation uses 0-based indexing via :meth:`~BaseParser.parse_field`.

References
----------
- Bio-Rad D-10 LIS Interface Specification (available from Bio-Rad support).
- ASTM E1394-97(2011) record type definitions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from d10_driver.logging_utils.logger import get_logger
from d10_driver.models.message import ASTMMessage, OrderRecord, PatientRecord, ResultRecord
from d10_driver.parsers.base_parser import BaseParser
from d10_driver.protocol.astm_constants import (
    FIELD_DELIMITER,
    RECORD_HEADER,
    RECORD_ORDER,
    RECORD_PATIENT,
    RECORD_RESULT,
    RECORD_TERMINATOR,
)

log = get_logger(__name__)


class D10Parser(BaseParser):
    """ASTM E1394 parser for the Bio-Rad D-10 hemoglobin analyzer.

    Converts a sequence of raw record strings (as delivered by
    :class:`~d10_driver.protocol.astm_reader.ASTMReader`) into a structured
    :class:`~d10_driver.models.message.ASTMMessage`.

    Usage
    -----
    ::

        parser = D10Parser()
        message = parser.parse_message(reader.receive_message())
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse_message(self, records: Iterable[str]) -> ASTMMessage:
        """Parse an iterable of ASTM record strings into an :class:`ASTMMessage`.

        Parameters
        ----------
        records:
            Iterable of stripped ASCII ASTM record strings produced by the
            :class:`~d10_driver.protocol.astm_reader.ASTMReader`.

        Returns
        -------
        ASTMMessage
            Fully populated message model with all extracted data.
        """
        message = ASTMMessage()
        current_patient: Optional[PatientRecord] = None
        current_order: Optional[OrderRecord] = None

        for raw_record in records:
            if not raw_record:
                continue

            record_type = raw_record[0]
            log.debug("Parsing record type '%s': %r", record_type, raw_record[:80])

            if record_type == RECORD_HEADER:
                self._parse_header(raw_record, message)

            elif record_type == RECORD_PATIENT:
                current_patient = self._parse_patient(raw_record)
                message.patients.append(current_patient)
                log.info("Patient parsed: %s", current_patient)

            elif record_type == RECORD_ORDER:
                current_order = self._parse_order(raw_record)
                message.orders.append(current_order)
                log.info("Order parsed: %s", current_order)

            elif record_type == RECORD_RESULT:
                result = self._parse_result(raw_record)
                message.results.append(result)
                log.info("Result parsed: %s", result)

            elif record_type == RECORD_TERMINATOR:
                self._parse_terminator(raw_record, message)
                log.info("Message terminator received — complete=%s", message.is_complete)

            else:
                log.debug("Skipping unknown record type '%s'", record_type)

        log.info(
            "Message parsed — patients=%d orders=%d results=%d complete=%s",
            len(message.patients),
            len(message.orders),
            len(message.results),
            message.is_complete,
        )
        return message

    # ------------------------------------------------------------------
    # Private record parsers
    # ------------------------------------------------------------------

    def _parse_header(self, record: str, message: ASTMMessage) -> None:
        """Parse an ASTM ``H`` (Header) record into *message*.

        ASTM E1394 Header record field layout (1-based):

        =====  ==============================================
        Field  Description
        =====  ==============================================
        1      Record type ID (``H``)
        2      Field delimiter + special characters
        3      Message control ID
        4      Access password (ignored)
        5      Sender name / instrument ID
        6      Sender street address
        7      Reserved
        8      Sender telephone
        9      Sender characteristics (ignored)
        10     Receiver ID
        11     Comment / free text
        12     Processing ID (``P`` production, ``Q`` QC)
        13     ASTM version number
        14     Date/time of message
        =====  ==============================================
        """
        f = lambda i: self.parse_field(record, i, FIELD_DELIMITER)

        message.sender_name = f(4) or None
        message.processing_id = f(11) or None
        message.version = f(12) or None
        message.message_control_id = f(13) or None
        log.debug(
            "Header: sender=%s processing_id=%s version=%s",
            message.sender_name,
            message.processing_id,
            message.version,
        )

    def _parse_patient(self, record: str) -> PatientRecord:
        """Parse an ASTM ``P`` (Patient) record into a :class:`PatientRecord`.

        ASTM E1394 Patient record field layout (1-based):

        =====  ==============================================================
        Field  Description
        =====  ==============================================================
        1      Record type ID (``P``)
        2      Sequence number
        3      Practice-assigned patient ID
        4      Laboratory-assigned patient ID
        5      Third-party patient ID
        6      Patient name (``Last^First^Middle``)
        7      Mother's maiden name
        8      Birthdate (YYYYMMDD)
        9      Patient sex (``M``, ``F``, ``U``)
        10     Race / ethnic origin
        11     Patient address
        12     Reserved
        13     Patient telephone number
        14     Attending physician ID
        …
        19     Comment / free text
        =====  ==============================================================
        """
        f = lambda i: self.parse_field(record, i, FIELD_DELIMITER)

        return PatientRecord(
            sequence_number=int(f(1)) if f(1).isdigit() else 1,
            practice_patient_id=f(2) or None,
            laboratory_patient_id=f(3) or None,
            patient_name=f(5) or None,
            mothers_maiden_name=f(6) or None,
            birthdate=f(7) or None,
            sex=f(8) or None,
            race=f(9) or None,
            address=f(10) or None,
            telephone=f(12) or None,
            attending_physician_id=f(13) or None,
            comment=f(18) or None,
        )

    def _parse_order(self, record: str) -> OrderRecord:
        """Parse an ASTM ``O`` (Order) record into an :class:`OrderRecord`.

        ASTM E1394 Order record field layout (1-based):

        =====  ==============================================================
        Field  Description
        =====  ==============================================================
        1      Record type ID (``O``)
        2      Sequence number
        3      Specimen ID (practice)
        4      Instrument specimen ID
        5      Universal test ID (``^^^<test_name>``)
        6      Priority (``R`` routine, ``S`` stat)
        7      Requested date/time (YYYYMMDDHHMMSS)
        8      Collection date/time
        9      Collection end time
        10     Collection volume
        11     Collector ID
        12     Action code
        13     Danger code
        14     Relevant clinical information
        15     Date/time specimen received
        16     Specimen descriptor
        17     Ordering physician
        …
        26     Report type
        =====  ==============================================================
        """
        f = lambda i: self.parse_field(record, i, FIELD_DELIMITER)

        return OrderRecord(
            sequence_number=int(f(1)) if f(1).isdigit() else 1,
            specimen_id=f(2) or None,
            instrument_specimen_id=f(3) or None,
            universal_test_id=f(4) or None,
            priority=f(5) or None,
            requested_at=f(6) or None,
            collected_at=f(7) or None,
            collection_end_time=f(8) or None,
            action_code=f(11) or None,
            danger_code=f(12) or None,
            relevant_clinical_info=f(13) or None,
            specimen_received_at=f(14) or None,
            specimen_descriptor=f(15) or None,
            ordering_physician=f(16) or None,
            report_type=f(25) or None,
        )

    def _parse_result(self, record: str) -> ResultRecord:
        """Parse an ASTM ``R`` (Result) record into a :class:`ResultRecord`.

        ASTM E1394 Result record field layout (1-based):

        =====  ==============================================================
        Field  Description
        =====  ==============================================================
        1      Record type ID (``R``)
        2      Sequence number
        3      Universal test ID (``^^^<analyte>``)
        4      Data or measurement value
        5      Units (e.g. ``%`` or ``g/dL``)
        6      Reference ranges (e.g. ``4.0-6.0``)
        7      Abnormal flags (``H``, ``L``, ``HH``, ``LL``, ``N``)
        8      Nature of abnormality testing
        9      Result status (``F`` final, ``C`` corrected, ``P`` preliminary)
        10     Date of change
        11     Operator ID
        12     Date/time results started
        13     Instrument ID
        =====  ==============================================================
        """
        f = lambda i: self.parse_field(record, i, FIELD_DELIMITER)

        return ResultRecord(
            sequence_number=int(f(1)) if f(1).isdigit() else 1,
            universal_test_id=f(2) or None,
            value=f(3) or None,
            units=f(4) or None,
            reference_ranges=f(5) or None,
            abnormal_flags=f(6) or None,
            nature_of_abnormality=f(7) or None,
            result_status=f(8) or None,
            result_date=f(11) or None,
            instrument=f(12) or None,
        )

    def _parse_terminator(self, record: str, message: ASTMMessage) -> None:
        """Parse the ASTM ``L`` (Terminator) record and update *message*.

        Field layout:

        =====  ========================
        Field  Description
        =====  ========================
        1      Record type ID (``L``)
        2      Sequence number
        3      Termination code (``N`` normal, ``E`` error, ``Q`` not found)
        =====  ========================
        """
        f = lambda i: self.parse_field(record, i, FIELD_DELIMITER)
        message.completion_code = f(2) or "N"
