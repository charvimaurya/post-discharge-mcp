"""
Helpers for interacting with the CareLoop document-processing SQS queue.

S3 sends an event to this queue whenever a new discharge document
is uploaded.

Later, AWS Lambda will consume these messages automatically.

For now, these helpers let us:
1. read messages manually during development,
2. extract the S3 bucket/key from them,
3. delete successfully processed messages.
"""

import json
from urllib.parse import unquote_plus

import boto3

from app import config


# ---------------------------------------------------------
# SQS CLIENT
# ---------------------------------------------------------

# Create one reusable boto3 SQS client.
#
# It uses the same AWS region as the rest of CareLoop.
sqs = boto3.client(
    "sqs",
    region_name=config.REGION,
)


# ---------------------------------------------------------
# RECEIVE MESSAGES
# ---------------------------------------------------------

def receive_messages(
    max_messages: int = 1,
) -> list[dict]:
    """
    Read messages from the CareLoop document-processing queue.

    Parameters
    ----------
    max_messages:
        Number of messages to request from SQS.

        AWS allows a maximum of 10 messages in one ReceiveMessage call.

    Returns
    -------
    list[dict]
        Raw SQS messages.

        Returns an empty list if no messages are waiting.
    """

    # Protect against accidentally requesting an invalid amount.
    if max_messages < 1 or max_messages > 10:
        raise ValueError(
            "max_messages must be between 1 and 10"
        )

    response = sqs.receive_message(
        # Which queue we want to read from.
        QueueUrl=config.DOCUMENT_QUEUE_URL,

        # How many messages we want.
        MaxNumberOfMessages=max_messages,

        # Long polling.
        #
        # Instead of immediately saying:
        # "there are no messages",
        #
        # SQS waits up to 20 seconds in case one arrives.
        WaitTimeSeconds=20,
    )

    # If SQS returns no "Messages" field,
    # return an empty list instead.
    return response.get(
        "Messages",
        [],
    )


# ---------------------------------------------------------
# PARSE S3 EVENTS FROM AN SQS MESSAGE
# ---------------------------------------------------------

def parse_s3_events_from_message(
    message: dict,
) -> list[dict]:
    """
    Extract S3 upload information from an SQS message.

    Example flow:

        SQS message
            ↓
        message["Body"]
            ↓
        JSON S3 event
            ↓
        bucket name
        object key
        event name

    One SQS message can technically contain more than one
    S3 record, so this function returns a list.
    """

    # -----------------------------------------------------
    # STEP 1: Get the message body
    # -----------------------------------------------------

    if "Body" not in message:
        raise ValueError(
            "SQS message does not contain a Body"
        )

    # SQS stores the body as a STRING.
    #
    # Example:
    #
    # '{"Records": [{"s3": {...}}]}'
    #
    # json.loads turns the string into a Python dictionary.
    try:
        body = json.loads(
            message["Body"]
        )

    except json.JSONDecodeError as exc:
        raise ValueError(
            "SQS message body is not valid JSON"
        ) from exc


    # -----------------------------------------------------
    # STEP 2: Get S3 records
    # -----------------------------------------------------

    records = body.get(
        "Records",
        [],
    )

    if not records:
        raise ValueError(
            "SQS message contains no S3 Records"
        )


    # -----------------------------------------------------
    # STEP 3: Extract useful information from each record
    # -----------------------------------------------------

    events = []

    for record in records:

        try:
            # Example:
            #
            # ObjectCreated:Put
            event_name = record[
                "eventName"
            ]

            # Example:
            #
            # careloop-documents-992617582533-london
            bucket_name = (
                record["s3"]
                ["bucket"]
                ["name"]
            )

            # Example S3 event key:
            #
            # patients/demo_patient_001/documents/doc_001.pdf
            encoded_key = (
                record["s3"]
                ["object"]
                ["key"]
            )

        except KeyError as exc:
            raise ValueError(
                "S3 event record is missing required fields"
            ) from exc


        # -------------------------------------------------
        # S3 event keys can be URL encoded
        # -------------------------------------------------
        #
        # Example:
        #
        # "patient file.pdf"
        #
        # may arrive as:
        #
        # "patient+file.pdf"
        #
        # unquote_plus converts it back.
        object_key = unquote_plus(
            encoded_key
        )


        events.append(
            {
                "event_name": event_name,
                "bucket": bucket_name,
                "key": object_key,
            }
        )

    return events


# ---------------------------------------------------------
# DELETE MESSAGE
# ---------------------------------------------------------

def delete_message(
    receipt_handle: str,
) -> None:
    """
    Permanently remove a successfully processed message
    from SQS.

    Important:

    Receiving a message does NOT delete it.

    SQS temporarily hides it using the visibility timeout.

    If processing succeeds:
        delete_message()

    If processing fails:
        do NOT delete it

    Then the visibility timeout expires and SQS can retry it.
    """

    sqs.delete_message(
        QueueUrl=config.DOCUMENT_QUEUE_URL,
        ReceiptHandle=receipt_handle,
    )
