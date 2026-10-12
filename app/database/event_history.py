"""Store patient action history in DynamoDB, reject duplicate event keys, and read saved events."""

import hashlib

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app import config
from app.clock import system_now_utc


dynamodb = boto3.resource(
    "dynamodb",
    region_name=config.REGION,
)

event_table = dynamodb.Table(
    config.EVENT_HISTORY_TABLE
)


def build_idempotency_key(
    patient_id: str,
    item_id: str,
    occurrence_key: str,
) -> str:
    return f"{patient_id}#{item_id}#{occurrence_key}"


def get_events(
    patient_id: str,
) -> list[dict]:
    """Return one query page of Event History for debugging and tests.

    Event History uses patient_id as its partition key and timestamp as its
    sort key. DynamoDB returns items in timestamp-key order. New events use
    deterministic hashed IDs in that key, so this is not chronological order;
    recorded_at contains their actual write time.
    """
    response = event_table.query(
        KeyConditionExpression=Key("patient_id").eq(patient_id)
    )
    return response.get("Items", [])


def append_event(
    patient_id: str,
    event_type: str,
    details: dict,
    idempotency_key: str,
) -> dict:
    """Write once per patient/idempotency key and report creation or duplication.

    The existing timestamp sort key stores a deterministic event identifier;
    recorded_at records the actual write time. Callers must use distinct keys
    for distinct occurrences, and reuse the same key for retries.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")

    event_key = "event#" + hashlib.sha256(
        idempotency_key.encode("utf-8")
    ).hexdigest()
    # When the event was really written (an audit time, not the demo clock).
    now = system_now_utc().isoformat()

    item = {
        "patient_id": patient_id,
        "timestamp": event_key,
        # Keep the actual event time separately.
        "recorded_at": now,
        "event_type": event_type,
        "details": details,
        "idempotency_key": idempotency_key,
    }

    try:
        event_table.put_item(
            Item=item,
            ConditionExpression=(
                "attribute_not_exists(patient_id) "
                "AND attribute_not_exists(#ts)"
            ),
            ExpressionAttributeNames={
                "#ts": "timestamp",
            },
        )
        return {
            "created": True,
            "duplicate": False,
            "event": item,
        }
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            return {
                "created": False,
                "duplicate": True,
                "event": None,
            }
        raise
