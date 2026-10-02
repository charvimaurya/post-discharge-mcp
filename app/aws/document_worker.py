"""
CareLoop asynchronous document-processing service.

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
process_document()
    ↓
save RecoveryState
"""

import json
import time

from urllib.parse import (
    unquote_plus,
)

from app.database.recovery_state import (
    get_recovery_state,
    save_recovery_state,
)

from app.ingestion.pipeline import (
    process_document,
)

from mcp_server.services.s3_service import (
    download_document,
    parse_document_key,
)

from urllib.parse import unquote_plus
import json

from app.ingestion.pipeline import (
    process_document,
)

from app.database.recovery_state import (
    save_recovery_state,
)

from mcp_server.services.s3_service import (
    download_document,
    parse_document_key,
)


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

    started_at = (
        time.perf_counter()
    )


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


    print(
        f"Processing "
        f"patient={patient_id} "
        f"document={document_id}"
    )


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

        print(
            f"Skipping duplicate "
            f"document={document_id}"
        )

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


    print(
        f"Downloaded "
        f"{len(file_bytes)} bytes"
    )


    # -----------------------------------------------------
    # 5. PROCESS DOCUMENT
    # -----------------------------------------------------

    # This is why you created process_document().
    #
    # Lambda does NOT need to know:
    #
    # PDF?
    # JPG?
    # PNG?
    #
    # process_document() decides.
    state = process_document(
        file_bytes=file_bytes,

        filename=filename,

        patient_id=patient_id,

        document_id=document_id,
    )


    # -----------------------------------------------------
    # 6. MARK PROCESSING SUCCESS
    # -----------------------------------------------------

    state.ingestion_status = (
        "ready"
    )


    # -----------------------------------------------------
    # 7. SAVE TO DYNAMODB
    # -----------------------------------------------------

    save_recovery_state(
        state
    )


    # -----------------------------------------------------
    # 8. LOG PROCESSING TIME
    # -----------------------------------------------------

    duration_ms = (
        (
            time.perf_counter()
            - started_at
        )
        * 1000
    )


    print(
        f"Processing completed "
        f"document={document_id} "
        f"duration_ms="
        f"{duration_ms:.2f}"
    )

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

def lambda_handler(
    event: dict,
    context,
) -> dict:
    """
    Entry point called by AWS Lambda.

    One Lambda invocation may contain multiple SQS messages.

    We process each message independently.

    If one message fails, return its message ID in
    batchItemFailures so Lambda retries only that message.
    """

    failures = []

    # Lambda sends SQS messages inside event["Records"].
    for sqs_record in event.get(
        "Records",
        [],
    ):

        message_id = sqs_record[
            "messageId"
        ]

        try:
            # One SQS message can contain one or more
            # S3 records.
            s3_records = (
                _extract_s3_events_from_sqs_record(
                    sqs_record
                )
            )

            for s3_record in s3_records:

                _process_s3_record(
                    s3_record
                )

        except Exception as exc:

            print(
                f"Failed message "
                f"{message_id}: "
                f"{exc}"
            )

            # Tell Lambda:
            #
            # retry this specific SQS message.
            failures.append(
                {
                    "itemIdentifier":
                        message_id
                }
            )

    # Lambda understands this response only when
    # ReportBatchItemFailures is enabled on the
    # SQS event source mapping.
    return {
        "batchItemFailures":
            failures
    }
