"""The patient's first name is read from the letter's "Patient:" line, in code, and never guessed."""

from pathlib import Path

import pytest

from app.ingestion import pipeline
from app.ingestion.patient_name import read_first_name
from app.ingestion.pdf_processor import extract_text
from app.models.recovery_model import RecoveryState


LETTER = Path("tests/fixtures/letter1_margaret_knee_replacement_SYNTHETIC.pdf")


def test_demo_letter_gives_margaret():
    pages = extract_text(LETTER.read_bytes())

    assert read_first_name(pipeline.combine_pages(pages)) == "Margaret"


@pytest.mark.parametrize("text, name", [
    ("Patient:\nMargaret Ellis\nDate of birth:\n3 March 1958", "Margaret"),
    ("Patient: Margaret Ellis", "Margaret"),
    ("Patient name: Mrs Margaret Ellis", "Margaret"),
    ("Name: ELLIS, Margaret", "Margaret"),
    ("Name of patient: MARGARET ELLIS", "Margaret"),
    ("Patient:\n\nMr. Ahmed Khan", "Ahmed"),
    ("Patient: Mary-Jane O'Neil", "Mary-Jane"),
    # A table: the label alone on its line, no colon, the name on the next line.
    ("Discharge letter for Margaret Ellis (synthetic).\nPatient\nMargaret Ellis\nDate of birth\n12 March 1958", "Margaret"),
    ("Patient name\nMr Ahmed Khan\nHospital no.\nSYN-000001", "Ahmed"),
])
def test_reads_the_labelled_name(text, name):
    assert read_first_name(text) == name


@pytest.mark.parametrize("text", [
    "",
    "DISCHARGE LETTER\nRight total knee replacement.",
    # A label with no name after it, an ID, an initial, or a sentence: no name.
    "Patient:\nPatient ID:\nSYN-0001",
    "Patient ID: SYN-0001",
    "Patient: M Ellis",
    # A bare label followed by another label or an ID, and "patient" inside a sentence.
    "Patient\nHospital no.\nSYN-000001",
    "Patient\nDate of birth\n12 March 1958",
    "The patient should rest.\nWalk twice a day.",
    "Patient\nWard 7\n",
    "Name\nConsultant\nMr D. Hartley",
    "Patient: please see the attached sheet for your exercises and medicines today thank you",
    # Other people in the letter are never the patient.
    "Consultant:\nDr R. Sample, Orthopaedic Surgeon\nSigned: Dr R. Sample",
])
def test_no_clear_name_means_no_name(text):
    assert read_first_name(text) is None


def test_the_plan_carries_the_first_name(monkeypatch):
    def plan(extracted, patient_id, document_id):
        return RecoveryState(patient_id=patient_id, document_id=document_id)

    monkeypatch.setattr(pipeline, "validate_discharge_document", lambda text: None)
    monkeypatch.setattr(pipeline, "invoke_extraction_model", lambda text: {})
    monkeypatch.setattr(pipeline, "normalize_recovery_plan", plan)
    monkeypatch.setattr(pipeline, "validate_recovery_plan", lambda state, document_text: state)

    state = pipeline.process_text("[Page 1]\nPatient:\nMargaret Ellis\nDischarged:\nFriday 16 October 2026", "p", "d")
    assert state.first_name == "Margaret"

    state = pipeline.process_text("[Page 1]\nDischarged:\nFriday 16 October 2026", "p", "d")
    assert state.first_name is None
