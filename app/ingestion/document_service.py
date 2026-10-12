"""
Afterward asynchronous document-processing service.

This module contains the reusable application logic used
by the AWS Lambda worker.

Flow:

SQS record
    ↓
extract S3 event
    ↓
parse object key
    ↓
download file
    ↓
process_document_with_pages()
    ↓
save RecoveryState
    ↓
index original pages for RAG
"""

from app.ingestion.document_validation import WrongDocumentError

import json
from datetime import datetime

from urllib.parse import (
    unquote_plus,
)

from app.database.recovery_state import (
    get_recovery_state,
    save_recovery_state,
)

from app.ingestion.pipeline import (
    process_document_with_pages,
)
from app.rag.service import (
    index_document_pages,
)

from app.aws.s3_service import (
    download_document,
    parse_document_key,
)
from app.clock import system_now_utc
from app.observability.log import Timer, service_log


log = service_log("document_lambda")


def _ms_since_upload(s3_record: dict) -> int | None:
    """ms from the S3 upload event to now, or None if the event has no usable time."""

    try:
        uploaded = datetime.fromisoformat(str(s3_record["eventTime"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None

    return max(0, int((system_now_utc() - uploaded).total_seconds() * 1000))


def _counts(state) -> tuple[int, int]:
    """(items in the plan, items that need confirmation). Counts only."""

    groups = ("medications", "tasks", "appointments", "restrictions", "monitoring", "warning_signs", "diet_advice")
    items = [item for name in groups for item in getattr(state, name, None) or []]

    return len(items), sum(1 for item in items if getattr(item, "needs_confirmation", False))


def _extract_s3_records(
    sqs_record: dict,
) -> list[dict]:
    """
    Extract the original S3 event records from one
    Lambda SQS record.

    Lambda receives:

        event["Records"]
            ↓
        SQS record
            ↓
        record["body"]
            ↓
        original S3 event JSON
    """

    body_string = sqs_record.get(
        "body"
    )

    if not body_string:
        raise ValueError(
            "SQS record has no body"
        )

    try:
        body = json.loads(
            body_string
        )

    except json.JSONDecodeError as exc:
        raise ValueError(
            "SQS body is not valid JSON"
        ) from exc


    # AWS sends this when validating an S3 notification, not for an upload.
    if body.get("Event") == "s3:TestEvent":
        log("s3_test_event_ignored")
        return []

    records = body.get(
        "Records",
        [],
    )

    if not records:
        raise ValueError(
            "SQS message contains no S3 records"
        )

    return records


def _process_s3_record(
    s3_record: dict,
) -> None:
    """
    Process one S3 ObjectCreated event.
    """

    timer = Timer()


    # -----------------------------------------------------
    # 1. GET S3 OBJECT KEY
    # -----------------------------------------------------

    encoded_key = (
        s3_record[
            "s3"
        ][
            "object"
        ][
            "key"
        ]
    )

    key = unquote_plus(
        encoded_key
    )


    # -----------------------------------------------------
    # 2. PARSE PATIENT/DOCUMENT INFORMATION
    # -----------------------------------------------------

    document = (
        parse_document_key(
            key
        )
    )

    patient_id = (
        document[
            "patient_id"
        ]
    )

    document_id = (
        document[
            "document_id"
        ]
    )

    extension = (
        document[
            "extension"
        ]
    )

    filename = (
        f"{document_id}"
        f"{extension}"
    )


    log("ingest_stage", stage="received", patient_id=patient_id, document_id=document_id,
        ms=_ms_since_upload(s3_record))


    # -----------------------------------------------------
    # 3. SQS IDEMPOTENCY CHECK
    # -----------------------------------------------------

    # SQS is at-least-once delivery.
    #
    # That means the same event can arrive more than once.
    #
    # If this exact document already produced a READY
    # RecoveryState, don't spend money invoking Bedrock
    # again.
    existing = (
        get_recovery_state(
            patient_id
        )
    )


    if (
        existing
        and existing.get(
            "document_id"
        ) == document_id
        and existing.get(
            "ingestion_status"
        ) == "ready"
    ):

        log("ingest_skipped", document_id=document_id, reason="duplicate")

        return


    # -----------------------------------------------------
    # 4. DOWNLOAD DOCUMENT
    # -----------------------------------------------------

    file_bytes = (
        download_document(
            key
        )
    )


    if not file_bytes:
        raise ValueError(
            "Downloaded S3 object is empty"
        )


    log("ingest_stage", stage="downloaded", document_id=document_id, ms=timer.ms)


    # -----------------------------------------------------
    # 5. PROCESS DOCUMENT
    # -----------------------------------------------------

    # Preserve the original pages for RAG alongside the structured state.
    #
    # Lambda does NOT need to know:
    #
    # PDF?
    # JPG?
    # PNG?
    #
    # process_document_with_pages() decides.
    try:
        state, pages = process_document_with_pages(
            file_bytes=file_bytes,

            filename=filename,

            patient_id=patient_id,

            document_id=document_id,
        )
    except WrongDocumentError:
        # Permanent rejection: acknowledge SQS, preserve the current plan,
        # and do not index unrelated content into the patient's RAG store.
        log("ingest_skipped", level="warning", document_id=document_id, reason="wrong_document")
        return


    # -----------------------------------------------------
    # 6. KEEP THE DOCUMENT RETRYABLE UNTIL RAG INDEXING SUCCEEDS
    # -----------------------------------------------------

    state.ingestion_status = (
        "indexing"
    )


    # -----------------------------------------------------
    # 7. SAVE TO DYNAMODB
    # -----------------------------------------------------

    save_recovery_state(
        state
    )

    item_count, needs_confirmation_count = _counts(state)
    log("ingest_stage", stage="saved", document_id=document_id, ms=timer.ms,
        item_count=item_count, needs_confirmation_count=needs_confirmation_count)

    # -----------------------------------------------------
    # 8. INDEX ORIGINAL DOCUMENT FOR RAG
    # -----------------------------------------------------

    vector_count = index_document_pages(
        patient_id=patient_id,
        document_id=document_id,
        pages=pages,
    )
    log("ingest_stage", stage="indexed", document_id=document_id, ms=timer.ms, item_count=vector_count)

    # Only skip future deliveries once both persistence and indexing succeeded.
    # If indexing or this final save fails, SQS retries the full document flow.
    state.ingestion_status = "ready"
    save_recovery_state(state)

    # -----------------------------------------------------
    # 9. LOG PROCESSING TIME
    # -----------------------------------------------------

    # ms: this Lambda's own work. upload_to_ready_ms: from the S3 upload to a ready plan.
    log("ingest_ready", stage="ready", document_id=document_id, ms=timer.ms,
        item_count=item_count, needs_confirmation_count=needs_confirmation_count,
        upload_to_ready_ms=_ms_since_upload(s3_record))


def process_sqs_record(
    sqs_record: dict,
) -> None:
    """
    Process one SQS record received by Lambda.
    """

    s3_records = (
        _extract_s3_records(
            sqs_record
        )
    )

    for s3_record in s3_records:

        _process_s3_record(
            s3_record
        )
