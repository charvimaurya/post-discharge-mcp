"""
Persistence helpers for proactive reminders.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError

from app import config


_dynamodb = boto3.resource(
    "dynamodb",
    region_name=config.REGION,
)

_recovery_table = _dynamodb.Table(
    config.RECOVERY_STATE_TABLE
)


def save_pending_checkin(
    patient_id: str,
    checkin: dict[str, Any],
) -> bool:
    """
    Atomically create a reminder for one occurrence.

    The occurrence_id itself is the idempotency key.

    Returns:
        True  -> reminder was written
        False -> this occurrence was already reminded
    """
    occurrence_id = checkin["occurrence_id"]

    try:
        _recovery_table.update_item(
            Key={
                "patient_id": patient_id,
            },
            UpdateExpression=(
                "SET pending_checkin = :pending, "
                "last_checkin_key = :checkin_key"
            ),
            ConditionExpression=(
                "attribute_not_exists(last_checkin_key) "
                "OR last_checkin_key <> :checkin_key"
            ),
            ExpressionAttributeValues={
                ":pending": checkin,
                ":checkin_key": occurrence_id,
            },
        )

        return True

    except ClientError as exc:
        error_code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if error_code == "ConditionalCheckFailedException":
            return False

        raise


def clear_pending_checkin(
    patient_id: str,
) -> None:
    """
    Clear the currently waiting reminder.

    last_checkin_key is intentionally NOT removed.

    This prevents the same occurrence from being reminded again after
    the patient responds.
    """
    _recovery_table.update_item(
        Key={
            "patient_id": patient_id,
        },
        UpdateExpression="REMOVE pending_checkin",
    )


def get_pending_checkin(
    patient_id: str,
) -> dict[str, Any] | None:
    response = _recovery_table.get_item(
        Key={
            "patient_id": patient_id,
        },
        ProjectionExpression="pending_checkin",
    )

    item = response.get("Item") or {}

    return item.get("pending_checkin")