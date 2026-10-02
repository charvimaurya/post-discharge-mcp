from unittest.mock import patch, sentinel

import pytest

from app.ingestion import pipeline


@pytest.mark.parametrize("filename", ["document.pdf", "document.PDF"])
def test_pdf_dispatch(filename):
    with patch.object(pipeline, "process_pdf", return_value=sentinel.state) as pdf, patch.object(pipeline, "process_image") as image:
        assert pipeline.process_document(b"pdf", filename, "patient", "document") is sentinel.state
        pdf.assert_called_once_with(file_bytes=b"pdf", patient_id="patient", document_id="document")
        image.assert_not_called()


@pytest.mark.parametrize("filename", ["note.jpg", "note.jpeg", "note.png", "note.PNG"])
def test_image_dispatch(filename):
    with patch.object(pipeline, "process_image", return_value=sentinel.state) as image, patch.object(pipeline, "process_pdf") as pdf:
        assert pipeline.process_document(b"image", filename, "patient", "document") is sentinel.state
        image.assert_called_once_with(file_bytes=b"image", filename=filename, patient_id="patient", document_id="document")
        pdf.assert_not_called()


@pytest.mark.parametrize("filename", ["note.txt", "note", "note.webp"])
def test_unsupported_type(filename):
    with patch.object(pipeline, "process_pdf") as pdf, patch.object(pipeline, "process_image") as image:
        with pytest.raises(ValueError, match="Unsupported document type:"):
            pipeline.process_document(b"data", filename, "patient", "document")
        pdf.assert_not_called()
        image.assert_not_called()


def test_worker_uses_shared_entry_point_and_saves_result():
    with patch("boto3.client"), patch("boto3.resource"):
        from app.aws import document_worker as worker
    record = {"s3": {"bucket": {"name": "test"}, "object": {
        "key": "patients/patient/documents/note.PNG",
    }}}
    with patch.object(worker, "get_recovery_state", return_value=None), patch.object(worker, "download_document", return_value=b"image"), patch.object(worker, "process_document", return_value=sentinel.state) as process, patch.object(worker, "save_recovery_state") as save:
        worker._process_s3_record(record)
        process.assert_called_once_with(file_bytes=b"image", filename="note.png", patient_id="patient", document_id="note")
        save.assert_called_once_with(sentinel.state)
