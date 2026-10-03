import json
import sys
from pathlib import Path

# Direct script execution needs the project root to import local packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import boto3

from app import config
from app.aws.sqs_service import (
    receive_messages,
)


# ---------------------------------------------------------
# CREATE AWS CLIENTS
# ---------------------------------------------------------

s3 = boto3.client(
    "s3",
    region_name=config.REGION,
)

sqs = boto3.client(
    "sqs",
    region_name=config.REGION,
)


# ---------------------------------------------------------
# 1. SHOW CURRENT CONFIG
# ---------------------------------------------------------

print("\n=== AFTERWARD AWS CONFIG ===")

print(
    "Region:",
    config.REGION,
)

print(
    "S3 bucket:",
    config.DOCUMENT_BUCKET,
)

print(
    "SQS queue URL:",
    config.DOCUMENT_QUEUE_URL,
)


# ---------------------------------------------------------
# 2. CHECK S3 EVENT NOTIFICATION CONFIGURATION
# ---------------------------------------------------------

print("\n=== S3 EVENT NOTIFICATIONS ===")

notification_config = (
    s3.get_bucket_notification_configuration(
        Bucket=config.DOCUMENT_BUCKET
    )
)

# S3 stores SQS notification rules here.
queue_configs = notification_config.get(
    "QueueConfigurations",
    [],
)

if not queue_configs:
    print(
        "❌ No SQS event notification is configured "
        "on this S3 bucket."
    )

else:
    print(
        f"✅ Found {len(queue_configs)} SQS "
        "notification configuration(s)"
    )

    for queue_config in queue_configs:

        print("\nNotification rule:")

        print(
            "ID:",
            queue_config.get("Id")
        )

        print(
            "Queue ARN:",
            queue_config.get("QueueArn")
        )

        print(
            "Events:",
            queue_config.get("Events")
        )

        print(
            "Filter:",
            json.dumps(
                queue_config.get(
                    "Filter",
                    {}
                ),
                indent=2,
            )
        )


# ---------------------------------------------------------
# 3. CHECK SQS QUEUE POLICY
# ---------------------------------------------------------

print("\n=== SQS QUEUE POLICY ===")

attributes = sqs.get_queue_attributes(
    QueueUrl=config.DOCUMENT_QUEUE_URL,
    AttributeNames=[
        "QueueArn",
        "Policy",
    ],
)

queue_arn = (
    attributes["Attributes"]
    .get("QueueArn")
)

queue_policy = (
    attributes["Attributes"]
    .get("Policy")
)

print(
    "Queue ARN:",
    queue_arn,
)

if not queue_policy:
    print(
        "❌ Queue has no access policy."
    )

else:
    print(
        "✅ Queue has an access policy:"
    )

    print(
        json.dumps(
            json.loads(queue_policy),
            indent=2,
        )
    )


# ---------------------------------------------------------
# 4. SEND A MANUAL TEST MESSAGE DIRECTLY TO SQS
# ---------------------------------------------------------
#
# This DOES NOT test S3.
#
# It only proves:
#
# Python → SQS → Python receive
#
# If this works, your queue URL and receive code are good.
# ---------------------------------------------------------

print("\n=== MANUAL SQS TEST ===")

test_body = {
    "test": True,
    "message": "Afterward direct SQS test"
}

sqs.send_message(
    QueueUrl=config.DOCUMENT_QUEUE_URL,
    MessageBody=json.dumps(
        test_body
    ),
)

print(
    "Sent manual message directly to SQS."
)

print(
    "Trying to receive it..."
)

messages = receive_messages(
    max_messages=10
)

if not messages:
    print(
        "❌ Could not receive manual SQS message."
    )

else:
    print(
        f"✅ Received {len(messages)} "
        "message(s) from SQS."
    )

    for message in messages:

        print(
            "\nMessage body:"
        )

        print(
            message["Body"]
        )
