"""
Tests for data models (:mod:`d10_driver.models.message`).

Covers:
- PatientRecord property helpers (last_name, first_name).
- ResultRecord property helpers (analyte_name, numeric_value).
- ASTMMessage.is_complete flag and summary() output.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from d10_driver.models.message import ASTMMessage, OrderRecord, PatientRecord, ResultRecord


class TestPatientRecord(unittest.TestCase):
    def test_last_name_extracted(self):
        p = PatientRecord(patient_name="SMITH^JOHN^MICHAEL")
        self.assertEqual(p.last_name, "SMITH")

    def test_first_name_extracted(self):
        p = PatientRecord(patient_name="SMITH^JOHN^MICHAEL")
        self.assertEqual(p.first_name, "JOHN")

    def test_no_name_returns_none(self):
        p = PatientRecord()
        self.assertIsNone(p.last_name)
        self.assertIsNone(p.first_name)

    def test_name_without_caret_returns_only_last(self):
        p = PatientRecord(patient_name="SMITH")
        self.assertEqual(p.last_name, "SMITH")
        self.assertIsNone(p.first_name)

    def test_repr_contains_id_and_name(self):
        p = PatientRecord(practice_patient_id="PAT001", patient_name="DOE^JOHN")
        self.assertIn("PAT001", repr(p))
        self.assertIn("DOE^JOHN", repr(p))


class TestResultRecord(unittest.TestCase):
    def test_analyte_name_from_fourth_component(self):
        r = ResultRecord(universal_test_id="^^^HBA1C")
        self.assertEqual(r.analyte_name, "HBA1C")

    def test_analyte_name_fallback_to_first(self):
        r = ResultRecord(universal_test_id="HBA1C")
        self.assertEqual(r.analyte_name, "HBA1C")

    def test_analyte_name_none_without_test_id(self):
        r = ResultRecord()
        self.assertIsNone(r.analyte_name)

    def test_numeric_value_float(self):
        r = ResultRecord(value="6.7")
        self.assertAlmostEqual(r.numeric_value, 6.7)

    def test_numeric_value_int(self):
        r = ResultRecord(value="10")
        self.assertAlmostEqual(r.numeric_value, 10.0)

    def test_numeric_value_none_on_text(self):
        r = ResultRecord(value="POSITIVE")
        self.assertIsNone(r.numeric_value)

    def test_numeric_value_none_on_no_value(self):
        r = ResultRecord()
        self.assertIsNone(r.numeric_value)

    def test_repr_format(self):
        r = ResultRecord(universal_test_id="^^^HBA1C", value="6.7", units="%", result_status="F")
        text = repr(r)
        self.assertIn("HBA1C", text)
        self.assertIn("6.7", text)
        self.assertIn("%", text)


class TestASTMMessage(unittest.TestCase):
    def test_is_complete_false_by_default(self):
        msg = ASTMMessage()
        self.assertFalse(msg.is_complete)

    def test_is_complete_true_with_completion_code(self):
        msg = ASTMMessage(completion_code="N")
        self.assertTrue(msg.is_complete)

    def test_summary_contains_key_fields(self):
        msg = ASTMMessage(
            sender_name="D-10",
            completion_code="N",
        )
        msg.patients.append(PatientRecord())
        msg.results.append(ResultRecord())
        summary = msg.summary()
        self.assertIn("Sender", summary)
        self.assertIn("Patients", summary)
        self.assertIn("Results", summary)

    def test_repr_format(self):
        msg = ASTMMessage(sender_name="D-10")
        self.assertIn("ASTMMessage", repr(msg))
        self.assertIn("D-10", repr(msg))

    def test_received_at_defaults_to_now(self):
        from datetime import timezone
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        msg = ASTMMessage()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertGreaterEqual(msg.received_at, before)
        self.assertLessEqual(msg.received_at, after)


class TestOrderRecord(unittest.TestCase):
    def test_repr_format(self):
        o = OrderRecord(specimen_id="SPEC001", universal_test_id="^^^HBA1C")
        self.assertIn("SPEC001", repr(o))
        self.assertIn("HBA1C", repr(o))

    def test_default_sequence_number(self):
        o = OrderRecord()
        self.assertEqual(o.sequence_number, 1)


if __name__ == "__main__":
    unittest.main()
