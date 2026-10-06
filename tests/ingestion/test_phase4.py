"""Test normalization, validation, generated IDs, and confirmation flags using synthetic extraction data."""

from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


SAMPLE_EXTRACTION = {
    "discharge_date": "18 September 2026",
    "medications": [
        {
            "name": "Amoxicillin",
            "strength": "500 mg",
            "dose": "1 tablet",
            "times_per_day": 3,
            "duration_text": "7 days",
            "instructions": None,
        }
    ],
    "tasks": [
        {
            "description": "Walk for 10 minutes",
            "times_per_day": 2,
        }
    ],
    "appointments": [
        {
            "title": "GP",
            "date": None,
            "time": None,
            "location": None,
        }
    ],
    "restrictions": [{"text": "Do not drive for two weeks", "topic": "driving"}],
    "monitoring": [
        {
            "what": "temperature",
            "frequency_text": "once daily",
            "threshold_text": None,
        }
    ],
    "warning_signs": [
        {
            "text": "Chest pain",
            "action": "Call 999",
        }
    ],
}


def test_normalization():
    state = normalize_recovery_plan(
        extracted=SAMPLE_EXTRACTION,
        patient_id="demo_patient_001",
        document_id="doc_001",
    )

    assert state.patient_id == "demo_patient_001"
    assert state.document_id == "doc_001"
    assert len(state.medications) == 1
    assert state.medications[0].name == "Amoxicillin"
    assert state.medications[0].id is not None
    assert state.ingestion_status == "processing"
    assert state.pending_checkin is None


def test_validation():
    state = normalize_recovery_plan(
        extracted=SAMPLE_EXTRACTION,
        patient_id="demo_patient_001",
        document_id="doc_001",
    )
    state = validate_recovery_plan(state)

    assert state.ingestion_status == "ready"
    assert state.medications[0].needs_confirmation is False


def test_missing_dose_is_preserved_without_inventing_it():
    extracted = {
        **SAMPLE_EXTRACTION,
        "medications": [
            {
                "name": "Amoxicillin",
                "dose": None,
                "times_per_day": 3,
                "duration_text": "7 days",
                "instructions": None,
            }
        ],
    }
    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id="demo_patient_001",
        document_id="doc_002",
    )
    state = validate_recovery_plan(state)

    assert state.medications[0].dose is None
    assert state.medications[0].needs_confirmation is False


def test_uncertainty_marker():
    extracted = {
        **SAMPLE_EXTRACTION,
        "tasks": [
            {
                "description": "Call [?111?] if symptoms worsen",
                "details": None,
            }
        ],
    }
    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id="demo_patient_001",
        document_id="doc_003",
    )
    state = validate_recovery_plan(state)

    assert state.tasks[0].needs_confirmation is True


if __name__ == "__main__":
    test_normalization()
    test_validation()
    test_missing_dose_is_preserved_without_inventing_it()
    test_uncertainty_marker()
    print("OK — all four Phase 4 tests passed.")
