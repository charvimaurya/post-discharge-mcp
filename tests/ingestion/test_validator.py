"""Test that validation preserves extracted content and flags uncertainty without inventing provenance."""

import unittest
from dataclasses import asdict

from app.ingestion.validator import validate_recovery_plan
from models.recovery_model import Appointment, Medication, RecoveryState, Source, Task


class RecoveryStateValidationTests(unittest.TestCase):
    def make_plan(self):
        source = Source("discharge_photo_001", 1, "Example source evidence", "image")
        return RecoveryState(
            patient_id="patient_001",
            document_id="discharge_photo_001",
            medications=[
                Medication("med_001", "Amoxicillin", source=source),
                Medication(
                    "med_002", "Furosemide", dose="[UNREADABLE]",
                    source=source, needs_confirmation=True,
                ),
            ],
            tasks=[Task("task_001", "[UNREADABLE]", source=source, needs_confirmation=True)],
            appointments=[
                Appointment("appt_001", "GP appointment", source=source),
                Appointment(
                    "appt_002", "Follow-up", date="[UNREADABLE]",
                    source=source, needs_confirmation=True,
                ),
            ],
        )

    def test_uncertainty_is_valid_and_validation_preserves_items(self):
        plan = self.make_plan()
        before = asdict(plan)
        self.assertIs(validate_recovery_plan(plan), plan)
        self.assertEqual(plan.ingestion_status, "ready")
        after = asdict(plan)
        for category in ("medications", "tasks", "appointments"):
            self.assertEqual(len(after[category]), len(before[category]))
            for original, validated in zip(before[category], after[category]):
                # Validation can flag missing fields, but must preserve extracted
                # content, uncertainty markers, and source evidence.
                original.pop("needs_confirmation")
                validated.pop("needs_confirmation")
                self.assertEqual(validated, original)
        self.assertTrue(plan.medications[0].needs_confirmation)

    def test_validation_preserves_uncertainty_without_inventing_provenance(self):
        for category in ("medications", "tasks", "appointments"):
            with self.subTest(category=category):
                plan = self.make_plan()
                item = next(item for item in getattr(plan, category) if item.needs_confirmation)
                item.source = None
                self.assertIs(validate_recovery_plan(plan), plan)
                self.assertIsNone(item.source)
                self.assertTrue(item.needs_confirmation)


if __name__ == "__main__":
    unittest.main()
