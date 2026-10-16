"""A missing bucket setting fails with a clear message when S3 is used, not at import."""

import pytest

from app import config
from app.aws import s3_service
from app.rag import vector_store


class NoS3:
    """Fails the test if any S3 call is made."""

    def __getattr__(self, name):
        raise AssertionError(f"S3 was called ({name}) without a bucket")


@pytest.fixture
def no_document_bucket(monkeypatch):
    monkeypatch.setattr(config, "DOCUMENT_BUCKET", "")
    monkeypatch.setattr(s3_service, "s3", NoS3())


def test_module_loads_without_a_bucket(no_document_bucket):
    # Importing worked above even though no bucket is set; only using S3 needs one.
    assert s3_service.MISSING_BUCKET_MESSAGE.startswith("DOCUMENT_BUCKET")


def test_upload_without_document_bucket_names_the_setting(no_document_bucket, tmp_path):
    letter = tmp_path / "letter.pdf"
    letter.write_bytes(b"%PDF-1.4 synthetic")

    with pytest.raises(RuntimeError, match="DOCUMENT_BUCKET"):
        s3_service.upload_document(str(letter), "demo_patient_001", "doc_test")


def test_download_without_document_bucket_names_the_setting(no_document_bucket):
    with pytest.raises(RuntimeError, match="DOCUMENT_BUCKET"):
        s3_service.download_document("patients/demo_patient_001/documents/doc_test.pdf")


def test_vector_search_without_vector_bucket_names_the_setting(monkeypatch):
    monkeypatch.setattr(config, "S3_VECTOR_BUCKET", "")
    monkeypatch.setattr(vector_store, "s3vectors", NoS3())

    with pytest.raises(RuntimeError, match="S3_VECTOR_BUCKET"):
        vector_store.query_chunks(query_embedding=[0.0] * config.EMBEDDING_DIMENSIONS, patient_id="demo_patient_001", document_id="doc_test")
