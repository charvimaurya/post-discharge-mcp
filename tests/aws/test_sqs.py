import pytest

from app.aws.sqs_service import (
    parse_s3_events_from_message,
)

from app.aws.s3_service import (
    parse_document_key,
)


# ---------------------------------------------------------
# TEST: NORMAL S3 EVENT
# ---------------------------------------------------------

def test_parse_s3_event():
    """
    Test that we can extract the bucket name and object key
    from a normal S3 → SQS event.

    This does NOT contact AWS.
    """

    fake_message = {
        "Body": """
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",

                    "s3": {
                        "bucket": {
                            "name": "afterward-test-bucket"
                        },

                        "object": {
                            "key": "patients/demo_patient_001/documents/doc_001.pdf"
                        }
                    }
                }
            ]
        }
        """
    }

    events = parse_s3_events_from_message(
        fake_message
    )

    # We expect exactly one S3 upload event.
    assert len(events) == 1

    event = events[0]

    assert (
        event["event_name"]
        == "ObjectCreated:Put"
    )

    assert (
        event["bucket"]
        == "afterward-test-bucket"
    )

    assert (
        event["key"]
        == "patients/demo_patient_001/documents/doc_001.pdf"
    )


# ---------------------------------------------------------
# TEST: SQS → S3 EVENT → AFTERWARD DOCUMENT DATA
# ---------------------------------------------------------

def test_sqs_event_to_document_metadata():
    """
    Test the complete parsing chain:

    SQS message
        ↓
    S3 event
        ↓
    object key
        ↓
    patient_id
    document_id
    extension
    """

    fake_message = {
        "Body": """
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",

                    "s3": {
                        "bucket": {
                            "name": "afterward-test-bucket"
                        },

                        "object": {
                            "key": "patients/demo_patient_001/documents/doc_001.pdf"
                        }
                    }
                }
            ]
        }
        """
    }

    # Extract the S3 information from the SQS message.
    events = parse_s3_events_from_message(
        fake_message
    )

    s3_event = events[0]


    # Extract Afterward-specific information
    # from our S3 object key.
    document = parse_document_key(
        s3_event["key"]
    )


    assert (
        document["patient_id"]
        == "demo_patient_001"
    )

    assert (
        document["document_id"]
        == "doc_001"
    )

    assert (
        document["extension"]
        == ".pdf"
    )


# ---------------------------------------------------------
# TEST: URL ENCODED S3 KEY
# ---------------------------------------------------------

def test_url_encoded_s3_key():
    """
    S3 can URL-encode object keys inside event messages.

    For example:

        "my document.pdf"

    can arrive as:

        "my+document.pdf"

    Make sure we correctly decode it.
    """

    fake_message = {
        "Body": """
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",

                    "s3": {
                        "bucket": {
                            "name": "afterward-test-bucket"
                        },

                        "object": {
                            "key": "patients/demo_patient_001/documents/my+document.pdf"
                        }
                    }
                }
            ]
        }
        """
    }

    events = parse_s3_events_from_message(
        fake_message
    )

    assert (
        events[0]["key"]
        == "patients/demo_patient_001/documents/my document.pdf"
    )


# ---------------------------------------------------------
# TEST: INVALID MESSAGE
# ---------------------------------------------------------

def test_invalid_sqs_message():
    """
    Invalid messages should fail clearly rather than
    causing confusing KeyErrors later.
    """

    fake_message = {
        "Body": "{}"
    }

    with pytest.raises(
        ValueError,
        match="contains no S3 Records",
    ):
        parse_s3_events_from_message(
            fake_message
        )

from app.aws.sqs_service import (
    receive_messages,
)


@pytest.mark.integration
def test_receive_real_s3_event_from_sqs():
    """
    Integration test.

    BEFORE running this:

    1. Upload a document to the real S3 bucket.
    2. Make sure S3 event notifications point to the SQS queue.
    3. Run this test.

    Unlike the unit tests above, this test contacts AWS.
    """

    messages = receive_messages(
        max_messages=1
    )

    assert len(messages) > 0

    message = messages[0]

    events = parse_s3_events_from_message(
        message
    )

    assert len(events) > 0

    event = events[0]

    assert "bucket" in event
    assert "key" in event

    print(
        "\nReceived S3 event:"
    )

    print(
        "Bucket:",
        event["bucket"],
    )

    print(
        "Key:",
        event["key"],
    )