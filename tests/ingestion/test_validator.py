"""Test confirmation flags for canonical recovery fields without changing clinical text."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from app.ingestion.validator import validate_recovery_plan
from app.models.recovery_model import (
    Appointment, Medication, Monitoring, RecoveryState, Restriction, WarningSign, Task,
)


CASES = [
    ("medications", Medication("med", "Example"), ["name", "strength", "dose", "form", "site", "instructions", "duration_text", "as_needed_reason"]),
    ("tasks", Task("task", "Example"), ["description", "details", "duration_text"]),
    ("appointments", Appointment("appt", "Example"), ["title", "date", "time", "location"]),
    ("restrictions", Restriction("restriction", "Example"), ["text", "topic"]),
    ("monitoring", Monitoring("monitor", "Example"), ["what", "frequency_text", "threshold_text"]),
    ("warning_signs", WarningSign("warning", "Example", "Stated action"), ["text", "action"]),
]


@pytest.mark.parametrize("category,example,field", [
    (category, example, field) for category, example, fields in CASES for field in fields
])
@pytest.mark.parametrize("marker", ["[?uncertain?]", "[UNREADABLE]"])
def test_uncertainty_in_each_text_field_is_flagged_and_preserved(category, example, field, marker):
    item = deepcopy(example)
    setattr(item, field, marker)
    before = asdict(item)
    state = RecoveryState("patient", "document", **{category: [item]})
    assert validate_recovery_plan(state) is state
    assert state.ingestion_status == "ready"
    assert item.needs_confirmation is True
    assert asdict(item) == {**before, "needs_confirmation": True}


def test_missing_optional_medication_fields_are_not_errors():
    medication = Medication("med", "Example")
    state = RecoveryState("patient", "document", medications=[medication])
    validate_recovery_plan(state)
    assert medication.needs_confirmation is False
    medication.name = ""
    validate_recovery_plan(state)
    assert medication.needs_confirmation is True


def test_conflicting_dates_and_pending_status_are_preserved():
    appointment = Appointment("appt", "Review", date="2026-10-01", conflicting_dates=["2026-10-02"])
    state = RecoveryState("patient", "document", appointments=[appointment])
    validate_recovery_plan(state)
    assert appointment.needs_confirmation is True
    assert appointment.date == "2026-10-01"
    assert appointment.conflicting_dates == ["2026-10-02"]
    assert appointment.status == "pending"


@pytest.mark.parametrize("urgency,expected", [("contact_care_team", False), ("emergency", False), ("unknown", True), (None, True)])
def test_warning_urgency(urgency, expected):
    warning = WarningSign("warning", "Example", "Stated action", urgency=urgency)
    validate_recovery_plan(RecoveryState("patient", "document", warning_signs=[warning]))
    assert warning.needs_confirmation is expected
    assert warning.urgency == urgency


@pytest.mark.parametrize("missing", ["text", "action"])
def test_warning_requires_both_text_and_action(missing):
    warning = WarningSign("warning", "Example", "Stated action")
    setattr(warning, missing, "")
    validate_recovery_plan(RecoveryState("patient", "document", warning_signs=[warning]))
    assert warning.needs_confirmation is True


def test_existing_confirmation_flag_is_not_cleared():
    medication = Medication("med", "Example", needs_confirmation=True)
    validate_recovery_plan(RecoveryState("patient", "document", medications=[medication]))
    assert medication.needs_confirmation is True
