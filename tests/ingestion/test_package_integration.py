"""Guard the application contracts across the external checker boundary."""

from dataclasses import asdict
import inspect
from pathlib import Path

import pytest
from discharge_letter_check import document_validation, models, validator
from discharge_letter_check.schema import load_schema

from app.ingestion import bedrock
from app.ingestion.document_validation import WrongDocumentError, validate_discharge_document
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan
from app.models import recovery_model


def test_instruction_types_preserve_package_identity():
    for name in (
        "Source", "Medication", "FollowOn", "Task", "Appointment",
        "Restriction", "Monitoring", "WarningSign", "DietAdvice",
    ):
        assert getattr(recovery_model, name) is getattr(models, name)
    assert validate_recovery_plan is validator.validate_recovery_plan
    assert WrongDocumentError is document_validation.WrongDocumentError
    with pytest.raises(WrongDocumentError):
        validate_discharge_document("An unrelated invoice")


def test_application_state_preserves_constructor_and_fields():
    assert recovery_model.RecoveryState is not models.RecoveryState
    assert inspect.signature(recovery_model.RecoveryState) == inspect.signature(models.RecoveryState)
    state = recovery_model.RecoveryState(
        "patient", "document", "2026-10-01", "Alex",
        pending_checkin={"kind": "task"}, timezone="America/New_York",
        last_updated="2026-10-01T12:00:00Z",
    )
    before = asdict(state)
    assert validate_recovery_plan(state) is state
    assert asdict(state) == {**before, "ingestion_status": "ready"}


def test_normalized_application_state_is_checked_in_place():
    state = normalize_recovery_plan(
        {"medications": [{"name": "Medicine [?]"}]}, "patient", "document",
    )
    assert isinstance(state, recovery_model.RecoveryState)
    assert isinstance(state.medications[0], models.Medication)
    assert validate_recovery_plan(state) is state
    assert state.medications[0].needs_confirmation
    assert state.ingestion_status == "ready"


def test_extraction_uses_the_package_schema_only():
    # One schema in one place: AfterWard keeps no local copy of the package's schema.
    assert not (Path(bedrock.__file__).parent / "schemas" / "discharge-extraction.schema.json").exists()
    schema = bedrock.load_extraction_schema()
    assert isinstance(schema, dict)
    assert schema == load_schema()
    schema.clear()
    assert bedrock.load_extraction_schema() == bedrock.EXTRACTION_SCHEMA
