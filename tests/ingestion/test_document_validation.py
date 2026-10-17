"""Document rejection is performed before model calls, persistence and indexing."""
from unittest.mock import patch

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge
from app.ingestion import pipeline, document_service
from app.ingestion.document_validation import (
    WRONG_DOCUMENT_MESSAGE, WrongDocumentError, validate_discharge_document,
)


@pytest.mark.parametrize('text', [
    '', 'Invoice from hospital. Total due £240.',
    'CV: I worked at a hospital and administered medications.',
    'Appointment letter. Attend the orthopaedic clinic on Monday.',
    'My essay about the discharge of electrical energy.',
    'DISCHARGE LETTER',
])
def test_wrong_document_rejected_before_model(text):
    with patch.object(pipeline, 'invoke_extraction_model') as extract:
        with pytest.raises(WrongDocumentError, match='Wrong document'):
            pipeline.process_text(text, 'patient', 'document')
        extract.assert_not_called()


@pytest.mark.parametrize('text', [
    'Hospital discharge letter. MEDICINES: Take paracetamol as directed.',
    'Discharge summary. Diagnosis: knee replacement. Follow-up in six weeks.',
    'You were discharged home today. Keep your wound dressing clean.',
    'DATE OF DISCHARGE: 16 October. Recovery exercises three times daily.',
])
def test_discharge_documents_accepted(text):
    validate_discharge_document(text)


@pytest.mark.parametrize('text,accepted', [
    ('Invoice: hospital services, total £250.', False),
    ('Discharge summary. Take medications as prescribed.', True),
    ('', False),
])
def test_bridge_preflight(text, accepted, monkeypatch):
    monkeypatch.setattr(web_bridge, 'extract_pdf_text', lambda _, **limits: [{'page': 1, 'text': text}])
    result = TestClient(web_bridge.app).post('/documents/validate', content=b'%PDF-test')
    assert result.status_code == (200 if accepted else 422)
    assert result.json() == ({'accepted': True} if accepted else {'error': WRONG_DOCUMENT_MESSAGE})


def test_invalid_pdf_rejected():
    result = TestClient(web_bridge.app).post('/documents/validate', content=b'not a pdf')
    assert result.status_code == 422
    assert result.json()['error'] == WRONG_DOCUMENT_MESSAGE


def test_corrupt_pdf_rejected(monkeypatch):
    def broken(_): raise ValueError('invalid pdf')
    monkeypatch.setattr(web_bridge, 'extract_pdf_text', broken)
    assert TestClient(web_bridge.app).post('/documents/validate', content=b'%PDF-corrupt').status_code == 422


def test_worker_rejects_without_changing_plan_or_indexing():
    record = {'s3': {'object': {'key': 'patients/patient/documents/wrong.pdf'}}}
    with patch.object(document_service, 'get_recovery_state', return_value={'document_id': 'good', 'ingestion_status': 'ready'}), \
         patch.object(document_service, 'download_document', return_value=b'pdf'), \
         patch.object(document_service, 'process_document_with_pages', side_effect=WrongDocumentError()), \
         patch.object(document_service, 'save_recovery_state') as save, \
         patch.object(document_service, 'index_document_pages') as index:
        document_service._process_s3_record(record)
        save.assert_not_called()
        index.assert_not_called()
