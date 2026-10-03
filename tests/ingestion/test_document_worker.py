"""Test Lambda batch handling and retry behavior when indexing or the final state save fails."""

from lambdas.document_processor.handler import (
    lambda_handler,
)

def test_handler_accepts_empty_event():

    result = lambda_handler(
        {
            "Records": []
        },
        None,
    )

    assert result == {
        "batchItemFailures": []
    }

def test_indexing_failure_retries_until_ready_then_skips():
    import json
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.ingestion import document_service as service

    stored = {}
    statuses = []

    def save(state):
        stored.update(patient_id=state.patient_id, document_id=state.document_id,
                      ingestion_status=state.ingestion_status)
        statuses.append(state.ingestion_status)

    event = {"Records": [{"messageId": "retry-test", "body": json.dumps({
        "Records": [{"s3": {"object": {"key": "patients/patient/documents/doc.pdf"}}}]
    })}]}
    pages = [{"page": 1, "text": "Synthetic instructions"}]
    with patch.object(service, "get_recovery_state", side_effect=lambda _: dict(stored)), \
         patch.object(service, "download_document", return_value=b"pdf"), \
         patch.object(service, "process_document_with_pages", side_effect=lambda **_: (
             SimpleNamespace(patient_id="patient", document_id="doc", ingestion_status="ready"), pages
         )) as process, \
         patch.object(service, "save_recovery_state", side_effect=save), \
         patch.object(service, "index_document_pages", side_effect=[RuntimeError("index unavailable"), 1]) as index:
        assert lambda_handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "retry-test"}]}
        assert stored["ingestion_status"] == "indexing"
        assert lambda_handler(event, None) == {"batchItemFailures": []}
        assert stored["ingestion_status"] == "ready"
        assert statuses == ["indexing", "indexing", "ready"]
        assert lambda_handler(event, None) == {"batchItemFailures": []}
        assert process.call_count == 2
        assert index.call_count == 2


def test_final_save_failure_leaves_persisted_state_retryable():
    import pytest
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.ingestion import document_service as service

    persisted_statuses = []

    def save(state):
        if state.ingestion_status == "ready":
            raise RuntimeError("DynamoDB unavailable")
        persisted_statuses.append(state.ingestion_status)

    record = {"s3": {"object": {"key": "patients/patient/documents/doc.pdf"}}}
    with patch.object(service, "get_recovery_state", return_value=None), \
         patch.object(service, "download_document", return_value=b"pdf"), \
         patch.object(service, "process_document_with_pages", return_value=(
             SimpleNamespace(ingestion_status="ready"), [{"page": 1, "text": "Example"}]
         )), \
         patch.object(service, "save_recovery_state", side_effect=save), \
         patch.object(service, "index_document_pages", return_value=1):
        with pytest.raises(RuntimeError, match="DynamoDB unavailable"):
            service._process_s3_record(record)
    assert persisted_statuses == ["indexing"]
