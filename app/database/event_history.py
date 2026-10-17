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


def delete_events(
    patient_id: str,
) -> int:
    """Delete every Event History row for one patient and return how many.

    Event History is otherwise append-only. This is the one exception: a
    newly uploaded discharge letter starts the plan again, so what was
    recorded against the previous letter must not carry over. Pages
    through the query so more than one page (1 MB) is fully deleted.
    """

    if not patient_id or not patient_id.strip():
        raise ValueError("patient_id must not be empty")

    deleted = 0

    query_kwargs = {
        "KeyConditionExpression": Key("patient_id").eq(patient_id),
        # Only the key attributes are needed to delete.
        # "timestamp" is a DynamoDB reserved word.
        "ProjectionExpression": "patient_id, #ts",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
    }

    with event_table.batch_writer() as batch:

        while True:
            response = event_table.query(**query_kwargs)

            for item in response.get("Items", []):
                batch.delete_item(
                    Key={
                        "patient_id": item["patient_id"],
                        "timestamp": item["timestamp"],
                    }
                )
                deleted += 1

            last_key = response.get("LastEvaluatedKey")

            if not last_key:
                break

            query_kwargs["ExclusiveStartKey"] = last_key

    return deleted


def get_complete_patient_events(patient_id: str) -> list[dict]:
    """Read every patient event page strongly consistently, without any writes.

    The hashed sort key cannot be used for a chronological range. Weekly callers
    filter explicit local dates after this complete read. Multiple pages are not
    an atomic snapshot if concurrent writers modify history during pagination.
    """
    if not patient_id or not patient_id.strip():
        raise ValueError("patient_id must not be empty")
    kwargs = {"KeyConditionExpression": Key("patient_id").eq(patient_id), "ConsistentRead": True}
    items = []
    while True:
        response = event_table.query(**kwargs)
        items.extend(item for item in response.get("Items", []) if item.get("patient_id") == patient_id)
        last = response.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last
