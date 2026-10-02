import time
import uuid
import sys
from pathlib import Path

# Direct script execution needs the project root to import local packages.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.services.s3_service import upload_document
from app.aws.sqs_service import (
    receive_messages,
    parse_s3_events_from_message,
)


PATIENT_ID = "demo_patient_001"


def main():
    # Create a unique document ID every run.
    # This guarantees a brand-new S3 object and therefore
    # should generate a new ObjectCreated event.
    document_id = f"test_{uuid.uuid4().hex[:8]}"

    print("Uploading test file...")

    result = upload_document(
        file_path=str(PROJECT_ROOT / "test_data" / "doc_001.pdf"),
        patient_id=PATIENT_ID,
        document_id=document_id,
    )

    expected_key = result["key"]

    print("Uploaded:")
    print(expected_key)

    print("\nWaiting for S3 → SQS event...")

    # Keep checking for up to 30 seconds.
    #
    # We don't want to assume the event arrives instantly.
    timeout_seconds = 30

    # Time when we should stop checking.
    end_time = time.time() + timeout_seconds

    while time.time() < end_time:

        print("Polling SQS...")

        # Long polling may itself wait up to 20 seconds,
        # depending on your receive_messages() implementation.
        messages = receive_messages(
            max_messages=10
        )

        # If we received messages, inspect them.
        for message in messages:

            try:
                events = parse_s3_events_from_message(
                    message
                )

            except ValueError:
                # Ignore messages that aren't valid S3 events.
                continue

            for event in events:

                print(
                    "Saw SQS event for:",
                    event["key"],
                )

                # Check whether this event belongs to
                # the exact file we just uploaded.
                if event["key"] == expected_key:

                    print("\n✅ S3 → SQS works")

                    print(
                        "Bucket:",
                        event["bucket"],
                    )

                    print(
                        "Key:",
                        event["key"],
                    )

                    return

        # Small pause before checking again.
        time.sleep(2)

    print("\n❌ No matching S3 → SQS event received within 30 seconds")


if __name__ == "__main__":
    main()
