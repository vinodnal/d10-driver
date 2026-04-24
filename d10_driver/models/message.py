"""
Domain data models for the D10 driver.

This module defines the four core entities extracted from an ASTM E1394
message:

- :class:`PatientRecord`  — patient demographics (ASTM record type ``P``).
- :class:`OrderRecord`    — test order (ASTM record type ``O``).
- :class:`ResultRecord`   — individual analyte result (ASTM record type ``R``).
- :class:`ASTMMessage`    — container holding all records from one transmission.

All models are plain Python dataclasses with no external dependencies, making
them easy to serialise, test, and reuse by other instrument drivers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Patient record (ASTM E1394 §8.5 — Record Type P)
# ---------------------------------------------------------------------------


@dataclass
class PatientRecord:
    """Represents one ASTM ``P`` (patient information) record.

    Fields correspond to the standard ASTM E1394 patient record positions.
    All fields are optional because some analysers omit non-essential data.
    """

    #: Sequence number of this patient within the message (field 2).
    sequence_number: int = 1

    #: Practice-assigned patient ID (field 3).
    practice_patient_id: Optional[str] = None

    #: Laboratory-assigned patient ID (field 4).
    laboratory_patient_id: Optional[str] = None

    #: Patient name as "Last^First^Middle" (field 6).
    patient_name: Optional[str] = None

    #: Mother's maiden name (field 7).
    mothers_maiden_name: Optional[str] = None

    #: Date of birth in ``YYYYMMDD`` format (field 8).
    birthdate: Optional[str] = None

    #: Patient sex: ``"M"`` (male), ``"F"`` (female), ``"U"`` (unknown) (field 9).
    sex: Optional[str] = None

    #: Race/ethnic origin (field 10).
    race: Optional[str] = None

    #: Patient address as "Street^City^State^Zip^Country" (field 11).
    address: Optional[str] = None

    #: Telephone number (field 13).
    telephone: Optional[str] = None

    #: Attending physician ID (field 14).
    attending_physician_id: Optional[str] = None

    #: Special field — instrument-specific patient comments (field 19).
    comment: Optional[str] = None

    @property
    def last_name(self) -> Optional[str]:
        """Return the patient's last name extracted from *patient_name*."""
        if self.patient_name:
            return self.patient_name.split("^")[0] or None
        return None

    @property
    def first_name(self) -> Optional[str]:
        """Return the patient's first name extracted from *patient_name*."""
        if self.patient_name:
            parts = self.patient_name.split("^")
            return parts[1] if len(parts) > 1 else None
        return None

    def __repr__(self) -> str:
        return (
            f"<PatientRecord id={self.practice_patient_id!r} "
            f"name={self.patient_name!r}>"
        )


# ---------------------------------------------------------------------------
# Order record (ASTM E1394 §8.6 — Record Type O)
# ---------------------------------------------------------------------------


@dataclass
class OrderRecord:
    """Represents one ASTM ``O`` (test order) record.

    The order record links a patient to the tests that were requested and
    stores timing information about specimen collection.
    """

    #: Sequence number of this order within the patient section (field 2).
    sequence_number: int = 1

    #: Specimen ID / sample ID assigned by the practice (field 3).
    specimen_id: Optional[str] = None

    #: Instrument-assigned specimen ID (field 4).
    instrument_specimen_id: Optional[str] = None

    #: Universal test identifier in "^^^<testname>" format (field 5).
    universal_test_id: Optional[str] = None

    #: Priority code (field 6): ``"R"`` routine, ``"S"`` stat, etc.
    priority: Optional[str] = None

    #: Date/time the order was requested (field 7), ASTM format ``YYYYMMDDHHMMSS``.
    requested_at: Optional[str] = None

    #: Date/time of specimen collection (field 8).
    collected_at: Optional[str] = None

    #: Collection end time (field 9).
    collection_end_time: Optional[str] = None

    #: Action code (field 11): ``"A"`` add, ``"N"`` new, ``"Q"`` query, etc.
    action_code: Optional[str] = None

    #: Danger code for hazardous specimens (field 12).
    danger_code: Optional[str] = None

    #: Relevant clinical information (field 13).
    relevant_clinical_info: Optional[str] = None

    #: Date/time the specimen was received by the lab (field 14).
    specimen_received_at: Optional[str] = None

    #: Specimen descriptor (field 15): e.g. ``"^^WB"`` (whole blood).
    specimen_descriptor: Optional[str] = None

    #: Ordering physician (field 16).
    ordering_physician: Optional[str] = None

    #: Report type (field 26): ``"O"`` order, ``"C"`` correction, etc.
    report_type: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"<OrderRecord specimen={self.specimen_id!r} "
            f"test={self.universal_test_id!r}>"
        )


# ---------------------------------------------------------------------------
# Result record (ASTM E1394 §8.7 — Record Type R)
# ---------------------------------------------------------------------------


@dataclass
class ResultRecord:
    """Represents one ASTM ``R`` (result) record.

    Each ``R`` record contains a single analyte result from the analyser.
    The Bio-Rad D-10 emits one ``R`` record per haemoglobin fraction measured.
    """

    #: Sequence number of this result within the order section (field 2).
    sequence_number: int = 1

    #: Universal test ID identifying the analyte (field 3).
    #: Format: ``"^^^<analyte_name>"`` or ``"<LOINC>^^^<analyte>"``.
    universal_test_id: Optional[str] = None

    #: Measured value as a string (field 4).
    value: Optional[str] = None

    #: Unit of measure (field 5), e.g. ``"%"`` or ``"g/dL"``.
    units: Optional[str] = None

    #: Reference range string (field 6), e.g. ``"4.0-6.0"``.
    reference_ranges: Optional[str] = None

    #: Abnormal flag (field 7): ``"H"``, ``"L"``, ``"HH"``, ``"LL"``, ``"N"``, etc.
    abnormal_flags: Optional[str] = None

    #: Nature of abnormality (field 8).
    nature_of_abnormality: Optional[str] = None

    #: Result status (field 9): ``"F"`` final, ``"C"`` correction, ``"P"`` preliminary.
    result_status: Optional[str] = None

    #: Date/time the result was recorded (field 12), ASTM format ``YYYYMMDDHHMMSS``.
    result_date: Optional[str] = None

    #: Instrument that produced the result (field 13).
    instrument: Optional[str] = None

    @property
    def analyte_name(self) -> Optional[str]:
        """Extract the analyte name from the universal test ID.

        The ASTM universal test ID uses ``^`` as a component separator.
        The analyte short-name is typically in the fourth component
        (index 3) of the ``^^^<name>`` format.
        """
        if self.universal_test_id:
            parts = self.universal_test_id.split("^")
            # Try component[3] (index 3) first, then component[0]
            for idx in (3, 0):
                if len(parts) > idx and parts[idx]:
                    return parts[idx]
        return None

    @property
    def numeric_value(self) -> Optional[float]:
        """Return *value* as a ``float``, or ``None`` if conversion fails."""
        try:
            return float(self.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def __repr__(self) -> str:
        return (
            f"<ResultRecord analyte={self.analyte_name!r} "
            f"value={self.value!r} units={self.units!r} "
            f"status={self.result_status!r}>"
        )


# ---------------------------------------------------------------------------
# Complete ASTM message container
# ---------------------------------------------------------------------------


@dataclass
class ASTMMessage:
    """Container for a complete ASTM E1394 message received from the analyser.

    One message corresponds to one full transmission between ENQ and EOT,
    and may contain data for multiple patients (though the D-10 typically
    sends one patient per message).
    """

    #: Date/time this message was received by the driver (UTC).
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    #: Raw sending facility identifier from the Header record (field 4).
    sender_name: Optional[str] = None

    #: Message control ID / transmission sequence from the Header (field 13).
    message_control_id: Optional[str] = None

    #: Processing ID from the Header (field 12): ``"P"`` production, etc.
    processing_id: Optional[str] = None

    #: ASTM version number from the Header (field 12).
    version: Optional[str] = None

    #: All patient records in this message.
    patients: list[PatientRecord] = field(default_factory=list)

    #: All order records, keyed by patient sequence number.
    orders: list[OrderRecord] = field(default_factory=list)

    #: All result records, in order.
    results: list[ResultRecord] = field(default_factory=list)

    #: Terminator record completion code: ``"N"`` normal, ``"E"`` error, etc.
    completion_code: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """``True`` if the message contained a valid terminator record."""
        return self.completion_code is not None

    def summary(self) -> str:
        """Return a short human-readable summary of the message contents."""
        parts = [
            f"Received: {self.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Sender:   {self.sender_name or '—'}",
            f"Patients: {len(self.patients)}",
            f"Orders:   {len(self.orders)}",
            f"Results:  {len(self.results)}",
            f"Complete: {self.is_complete}",
        ]
        return "\n".join(parts)

    def __repr__(self) -> str:
        return (
            f"<ASTMMessage sender={self.sender_name!r} "
            f"patients={len(self.patients)} results={len(self.results)}>"
        )
