"""
AWS Lambda entry point for Afterward document ingestion.

This handler intentionally contains very little business
logic.

Actual processing lives in:

    app.ingestion.document_service
"""

from app.ingestion.document_service import (
    process_sqs_record,
)
from app.observability.log import reset_request_id, service_log, set_request_id


log = service_log("document_lambda")


def lambda_handler(
    event: dict,
    context,
) -> dict:
    """
    Process SQS messages delivered by AWS Lambda.

    When an individual SQS record fails, return its
    messageId through batchItemFailures.

    This allows Lambda/SQS to retry only failed records.
    """

    failures = []

    # Lambda's event contains one or more SQS messages.
    for record in event.get("Records", []):

        message_id = record.get("messageId")

        # The SQS message id is this upload's request id in every log line.
        token = set_request_id(message_id)

        try:
            process_sqs_record(record)

        except Exception as exc:
            # The error TYPE only: a message can quote letter text.
            log("document_failed", level="error", error=exc, stage="failed")

            # Tell Lambda: "This exact SQS message failed."
            failures.append({"itemIdentifier": message_id})

        finally:
            reset_request_id(token)

    return {"batchItemFailures": failures}
