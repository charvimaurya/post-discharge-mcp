import unittest
from dataclasses import asdict

from app.ingestion.validator import validate_recovery_plan
from models.recovery_model import Appointment, Medication, RecoveryPlan, Source, Task


class RecoveryPlanValidationTests(unittest.TestCase):
    def make_plan(self):
        source = Source("discharge_photo_001", 1, "Example source evidence", "image")
        return RecoveryPlan(
            patient_id="patient_001",
            recovery_status="active",
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
        self.assertEqual(validate_recovery_plan(plan), (True, []))
        self.assertEqual(asdict(plan), before)

    def test_uncertainty_does_not_bypass_required_provenance(self):
        for category in ("medications", "tasks", "appointments"):
            with self.subTest(category=category):
                plan = self.make_plan()
                item = next(item for item in getattr(plan, category) if item.needs_confirmation)
                item.source = None
                valid, errors = validate_recovery_plan(plan)
                self.assertFalse(valid)
                self.assertTrue(any("missing source provenance" in error for error in errors))
                self.assertTrue(item.needs_confirmation)


if __name__ == "__main__":
    unittest.main()
