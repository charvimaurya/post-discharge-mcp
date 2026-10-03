"""Test normalization, validation, generated IDs, and confirmation flags using synthetic extraction data."""

from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


SAMPLE_EXTRACTION = {
    "discharge_date": "18 September 2026",
    "medications": [
        {
            "name": "Amoxicillin",
            "dose": "500 mg",
            "frequency": "three times daily",
            "duration": "7 days",
            "notes": None,
        }
    ],
    "tasks": [
        {
            "description": "Walk for 10 minutes",
            "timing": "twice daily",
        }
    ],
    "appointments": [
        {
            "with": "GP",
            "date": None,
            "time": None,
            "location": None,
            "status": "to_arrange",
            "notes": "Arrange within 7 days",
        }
    ],
    "restrictions": ["Do not drive for two weeks"],
    "monitoring": [
        {
            "what": "temperature",
            "how_often": "once daily",
            "threshold": None,
        }
    ],
    "warning_signs": [
        {
            "sign": "Chest pain",
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


def test_missing_dose():
    extracted = {
        **SAMPLE_EXTRACTION,
        "medications": [
            {
                "name": "Amoxicillin",
                "dose": None,
                "frequency": "three times daily",
                "duration": "7 days",
                "notes": None,
            }
        ],
    }
    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id="demo_patient_001",
        document_id="doc_002",
    )
    state = validate_recovery_plan(state)

    assert state.medications[0].needs_confirmation is True


def test_uncertainty_marker():
    extracted = {
        **SAMPLE_EXTRACTION,
        "tasks": [
            {
                "description": "Call [?111?] if symptoms worsen",
                "timing": None,
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
    test_missing_dose()
    test_uncertainty_marker()
    print("OK — all four Phase 4 tests passed.")
