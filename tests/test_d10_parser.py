"""
Tests for the D10 parser (:class:`D10Parser`).

Covers:
- Header record parsing.
- Patient record parsing (all key fields).
- Order record parsing.
- Result record parsing (analyte extraction, numeric value).
- Terminator record parsing.
- Full message assembly from a sequence of records.
- Edge cases: missing fields, empty records, unknown record types.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from d10_driver.models.message import ASTMMessage, PatientRecord, OrderRecord, ResultRecord
from d10_driver.parsers.d10_parser import D10Parser


class TestD10ParserHeader(unittest.TestCase):
    """Tests for Header (``H``) record parsing."""

    def setUp(self):
        self.parser = D10Parser()

    def test_sender_name_extracted(self):
        records = ["H|\\^&|||D-10 Dual|||||||P|1|20240424120000", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(msg.sender_name, "D-10 Dual")

    def test_processing_id_extracted(self):
        records = ["H|\\^&|||D-10|||||||P|1|20240424", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(msg.processing_id, "P")

    def test_version_extracted(self):
        records = ["H|\\^&|||D-10|||||||P|1|20240424", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(msg.version, "1")

    def test_missing_sender_name(self):
        """Empty sender field results in None."""
        records = ["H|\\^&|||||||||P|1|20240424", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertIsNone(msg.sender_name)


class TestD10ParserPatient(unittest.TestCase):
    """Tests for Patient (``P``) record parsing."""

    def setUp(self):
        self.parser = D10Parser()

    def _parse(self, p_record: str) -> PatientRecord:
        records = ["H|\\^&|||D-10", p_record, "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(len(msg.patients), 1)
        return msg.patients[0]

    def test_practice_patient_id(self):
        patient = self._parse("P|1|PAT001|LAB001||DOE^JOHN||19800101|M")
        self.assertEqual(patient.practice_patient_id, "PAT001")

    def test_laboratory_patient_id(self):
        patient = self._parse("P|1|PAT001|LAB001||DOE^JOHN||19800101|M")
        self.assertEqual(patient.laboratory_patient_id, "LAB001")

    def test_patient_name(self):
        patient = self._parse("P|1|PAT001||  |DOE^JOHN^MIDDLE||19800101|M")
        self.assertEqual(patient.patient_name, "DOE^JOHN^MIDDLE")

    def test_last_name_property(self):
        patient = self._parse("P|1|||  |DOE^JOHN||19800101|M")
        self.assertEqual(patient.last_name, "DOE")

    def test_first_name_property(self):
        patient = self._parse("P|1|||  |DOE^JOHN||19800101|M")
        self.assertEqual(patient.first_name, "JOHN")

    def test_birthdate(self):
        patient = self._parse("P|1|PAT001||||  |19800115|M")
        self.assertEqual(patient.birthdate, "19800115")

    def test_sex(self):
        # ASTM P record 0-indexed: 0=P,1=seq,2=practice_id,3=lab_id,
        # 4=third_party,5=name,6=maiden,7=birthdate,8=sex
        patient = self._parse("P|1|PAT001|||||19800101|F")
        self.assertEqual(patient.sex, "F")

    def test_sequence_number(self):
        patient = self._parse("P|3|PAT001")
        self.assertEqual(patient.sequence_number, 3)

    def test_sequence_number_defaults_to_one_on_invalid(self):
        patient = self._parse("P|X|PAT001")
        self.assertEqual(patient.sequence_number, 1)

    def test_no_name_returns_none(self):
        patient = self._parse("P|1|PAT001")
        self.assertIsNone(patient.patient_name)
        self.assertIsNone(patient.last_name)
        self.assertIsNone(patient.first_name)


class TestD10ParserOrder(unittest.TestCase):
    """Tests for Order (``O``) record parsing."""

    def setUp(self):
        self.parser = D10Parser()

    def _parse(self, o_record: str) -> OrderRecord:
        records = ["H|\\^&|||D-10", "P|1|PAT001", o_record, "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(len(msg.orders), 1)
        return msg.orders[0]

    def test_specimen_id(self):
        order = self._parse("O|1|SPEC001||^^^HBA1C|R|20240424120000")
        self.assertEqual(order.specimen_id, "SPEC001")

    def test_universal_test_id(self):
        order = self._parse("O|1|SPEC001||^^^HBA1C|R")
        self.assertEqual(order.universal_test_id, "^^^HBA1C")

    def test_priority(self):
        order = self._parse("O|1|SPEC001||^^^HBA1C|S")
        self.assertEqual(order.priority, "S")

    def test_collected_at(self):
        # ASTM O record 0-indexed: 6=requested_at, 7=collected_at
        # Put the collection date at index 7
        order = self._parse("O|1|SPEC001||^^^HBA1C|R||20240424|20240424093000")
        self.assertEqual(order.collected_at, "20240424")

    def test_action_code(self):
        # ASTM O record 0-indexed: 11=action_code (ASTM field 12)
        # Record: O|seq|specimen|instr|test|priority|req|coll|coll_end|vol|collector_id|action_code
        order = self._parse("O|1|SPEC001||^^^HBA1C|R|20240424|20240424||1||N")
        self.assertEqual(order.action_code, "N")


class TestD10ParserResult(unittest.TestCase):
    """Tests for Result (``R``) record parsing."""

    def setUp(self):
        self.parser = D10Parser()

    def _parse(self, r_record: str) -> ResultRecord:
        records = [
            "H|\\^&|||D-10",
            "P|1|PAT001",
            "O|1|SPEC001||^^^HBA1C",
            r_record,
            "L|1|N",
        ]
        msg = self.parser.parse_message(records)
        self.assertEqual(len(msg.results), 1)
        return msg.results[0]

    def test_universal_test_id(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F|||20240424|D10")
        self.assertEqual(result.universal_test_id, "^^^HBA1C")

    def test_analyte_name_from_universal_test_id(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F")
        self.assertEqual(result.analyte_name, "HBA1C")

    def test_value(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%")
        self.assertEqual(result.value, "6.7")

    def test_numeric_value(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%")
        self.assertAlmostEqual(result.numeric_value, 6.7)

    def test_units(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%")
        self.assertEqual(result.units, "%")

    def test_reference_ranges(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0")
        self.assertEqual(result.reference_ranges, "4.0-6.0")

    def test_abnormal_flag_high(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0|H")
        self.assertEqual(result.abnormal_flags, "H")

    def test_result_status_final(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F")
        self.assertEqual(result.result_status, "F")

    def test_instrument_field(self):
        result = self._parse("R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F|||20240424|D10-001")
        self.assertEqual(result.instrument, "D10-001")

    def test_numeric_value_none_on_non_numeric(self):
        result = self._parse("R|1|^^^HBA1C|POSITIVE|%")
        self.assertIsNone(result.numeric_value)

    def test_analyte_name_fallback_to_first_component(self):
        """If the 4th component is empty, fall back to the first non-empty."""
        result = self._parse("R|1|HBA1C|||%")
        self.assertEqual(result.analyte_name, "HBA1C")


class TestD10ParserTerminator(unittest.TestCase):
    """Tests for Terminator (``L``) record parsing."""

    def setUp(self):
        self.parser = D10Parser()

    def test_completion_code_normal(self):
        records = ["H|\\^&|||D-10", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertEqual(msg.completion_code, "N")

    def test_is_complete_true(self):
        records = ["H|\\^&|||D-10", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertTrue(msg.is_complete)

    def test_is_complete_false_without_terminator(self):
        records = ["H|\\^&|||D-10", "R|1|^^^HBA1C|6.7|%"]
        msg = self.parser.parse_message(records)
        self.assertFalse(msg.is_complete)


class TestD10ParserFullMessage(unittest.TestCase):
    """Integration tests: parse a realistic full D-10 message."""

    FULL_MESSAGE = [
        "H|\\^&|||D-10 Dual|||||||P|1|20240424120000",
        "P|1|PAT001|LAB001||DOE^JOHN||19800115|M",
        "O|1|SPEC001||^^^HBA1C|R|20240424120000|20240424090000",
        "R|1|^^^HBA1C|6.7|%|4.0-6.0|H||F|||20240424120000|D10-001",
        "R|2|^^^A0|92.1|%|||N||F|||20240424120000|D10-001",
        "R|3|^^^A2|3.2|%|2.0-3.5||N||F|||20240424120000|D10-001",
        "L|1|N",
    ]

    def setUp(self):
        self.parser = D10Parser()
        self.message = self.parser.parse_message(self.FULL_MESSAGE)

    def test_message_is_complete(self):
        self.assertTrue(self.message.is_complete)

    def test_patient_count(self):
        self.assertEqual(len(self.message.patients), 1)

    def test_order_count(self):
        self.assertEqual(len(self.message.orders), 1)

    def test_result_count(self):
        self.assertEqual(len(self.message.results), 3)

    def test_patient_name(self):
        self.assertEqual(self.message.patients[0].patient_name, "DOE^JOHN")

    def test_hba1c_value(self):
        hba1c = next(
            r for r in self.message.results if r.analyte_name == "HBA1C"
        )
        self.assertAlmostEqual(hba1c.numeric_value, 6.7)
        self.assertEqual(hba1c.abnormal_flags, "H")
        self.assertEqual(hba1c.units, "%")

    def test_message_summary_contains_counts(self):
        summary = self.message.summary()
        self.assertIn("Patients:", summary)
        self.assertIn("Results:", summary)

    def test_repr_format(self):
        self.assertIn("ASTMMessage", repr(self.message))


class TestD10ParserEdgeCases(unittest.TestCase):
    """Edge cases and robustness tests."""

    def setUp(self):
        self.parser = D10Parser()

    def test_empty_record_list(self):
        msg = self.parser.parse_message([])
        self.assertFalse(msg.is_complete)
        self.assertEqual(len(msg.patients), 0)

    def test_whitespace_only_records_ignored(self):
        msg = self.parser.parse_message(["   ", "\t", ""])
        self.assertFalse(msg.is_complete)

    def test_unknown_record_type_is_skipped(self):
        records = ["H|\\^&|||D-10", "X|custom|data", "L|1|N"]
        msg = self.parser.parse_message(records)
        self.assertTrue(msg.is_complete)

    def test_multiple_result_records_in_order(self):
        records = [
            "H|\\^&|||D-10",
            "R|1|^^^HBA1C|6.7|%",
            "R|2|^^^A0|92.1|%",
            "R|3|^^^A2|3.2|%",
            "L|1|N",
        ]
        msg = self.parser.parse_message(records)
        self.assertEqual(len(msg.results), 3)
        self.assertEqual(msg.results[0].analyte_name, "HBA1C")
        self.assertEqual(msg.results[1].analyte_name, "A0")
        self.assertEqual(msg.results[2].analyte_name, "A2")


if __name__ == "__main__":
    unittest.main()
