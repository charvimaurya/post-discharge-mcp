"""Test document routing and the order of state persistence and RAG indexing using mocks."""

from types import SimpleNamespace
from unittest.mock import Mock, call, patch, sentinel

import pytest

from app.ingestion import pipeline


@pytest.mark.parametrize("filename", ["document.pdf", "document.PDF"])
def test_pdf_dispatch(filename):
    pages = [{"page": 1, "text": "PDF instructions"}]
    with patch.object(pipeline, "extract_pdf_text", return_value=pages) as pdf, patch.object(pipeline, "process_text", return_value=sentinel.state) as process:
        assert pipeline.process_document(b"pdf", filename, "patient", "document") is sentinel.state
        pdf.assert_called_once_with(b"pdf")
        process.assert_called_once_with(text="[Page 1]\nPDF instructions", patient_id="patient", document_id="document")


@pytest.mark.parametrize("filename", ["note.jpg", "note.jpeg", "note.png", "note.PNG"])
def test_image_dispatch(filename):
    pages = [{"page": 1, "text": "Image instructions"}]
    with patch("app.ingestion.image_processor.extract_text_from_image", return_value=pages) as image, patch.object(pipeline, "extract_pdf_text") as pdf, patch.object(pipeline, "process_text", return_value=sentinel.state) as process:
        assert pipeline.process_document(b"image", filename, "patient", "document") is sentinel.state
        image.assert_called_once_with(file_bytes=b"image", filename=filename)
        pdf.assert_not_called()
        process.assert_called_once_with(text="[Page 1]\nImage instructions", patient_id="patient", document_id="document")


@pytest.mark.parametrize("filename", ["note.txt", "note", "note.webp"])
def test_unsupported_type(filename):
    with patch.object(pipeline, "extract_pdf_text") as pdf, patch("app.ingestion.image_processor.extract_text_from_image") as image:
        with pytest.raises(ValueError, match="Unsupported document type:"):
            pipeline.process_document(b"data", filename, "patient", "document")
        pdf.assert_not_called()
        image.assert_not_called()


def test_worker_saves_state_then_indexes_original_pages():
    with patch("boto3.client"), patch("boto3.resource"):
        from app.ingestion import document_service as worker
    record = {"s3": {"bucket": {"name": "test"}, "object": {
        "key": "patients/patient/documents/note.PNG",
    }}}
    state = SimpleNamespace(ingestion_status="processing")
    pages = [{"page": 1, "text": "Original image instructions"}]
    operations = Mock()
    with patch.object(worker, "get_recovery_state", return_value=None), patch.object(worker, "download_document", return_value=b"image"), patch.object(worker, "process_document_with_pages", return_value=(state, pages)) as process, patch.object(worker, "save_recovery_state") as save, patch.object(worker, "index_document_pages", return_value=1) as index:
        operations.attach_mock(save, "save")
        operations.attach_mock(index, "index")
        worker._process_s3_record(record)
        process.assert_called_once_with(file_bytes=b"image", filename="note.png", patient_id="patient", document_id="note")
        assert state.ingestion_status == "ready"
        assert operations.mock_calls == [
            call.save(state),
            call.index(patient_id="patient", document_id="note", pages=pages),
            call.save(state),
        ]
