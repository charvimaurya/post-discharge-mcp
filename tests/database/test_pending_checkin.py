"""Pending check-in persistence, against an in-memory stand-in for DynamoDB."""

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

with patch("boto3.resource"):
    from app.database import recovery_state


PATIENT_ID = "demo_patient_001"
KEY_A = "2026-10-23#task_abc#2026-10-23#1"
KEY_B = "2026-10-23#task_abc#2026-10-23#2"


class FakeTable:
    """Applies the two update expressions the check-in helpers send."""

    def __init__(self):
        self.items = {PATIENT_ID: {"patient_id": PATIENT_ID, "tasks": ["kept"]}}
        self.calls = []

    def update_item(self, Key, UpdateExpression, **kwargs):
        self.calls.append({"UpdateExpression": UpdateExpression, **kwargs})
        item = self.items.setdefault(Key["patient_id"], dict(Key))

        if UpdateExpression == "REMOVE pending_checkin":
            item.pop("pending_checkin", None)
            return

        values = kwargs["ExpressionAttributeValues"]

        if item.get("last_checkin_key") == values[":checkin_key"]:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}},
                "UpdateItem",
            )

        item["pending_checkin"] = values[":pending"]
        item["last_checkin_key"] = values[":checkin_key"]


@pytest.fixture
def table(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(recovery_state, "table", fake)
    return fake


def _checkin(key):
    return {"checkin_id": key, "text": "Reminder"}


def test_first_write_succeeds(table):
    assert recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A) is True

    item = table.items[PATIENT_ID]
    assert item["pending_checkin"] == _checkin(KEY_A)
    assert item["last_checkin_key"] == KEY_A


def test_write_is_conditional_on_the_key(table):
    recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)

    call = table.calls[0]
    assert call["ConditionExpression"] == (
        "attribute_not_exists(last_checkin_key) "
        "OR last_checkin_key <> :checkin_key"
    )
    assert call["UpdateExpression"] == (
        "SET pending_checkin = :pending, last_checkin_key = :checkin_key"
    )


def test_same_key_second_write_returns_false(table):
    recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)

    assert recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A) is False


def test_different_key_succeeds(table):
    recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)

    assert recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_B), KEY_B) is True
    assert table.items[PATIENT_ID]["last_checkin_key"] == KEY_B


def test_other_client_errors_are_raised(table, monkeypatch):
    def throttled(**kwargs):
        raise ClientError({"Error": {"Code": "ThrottlingException"}}, "UpdateItem")

    monkeypatch.setattr(table, "update_item", throttled)

    with pytest.raises(ClientError):
        recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)


def test_clear_removes_pending_checkin_and_keeps_key(table):
    recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)

    recovery_state.clear_pending_checkin(PATIENT_ID)

    item = table.items[PATIENT_ID]
    assert "pending_checkin" not in item
    assert item["last_checkin_key"] == KEY_A
    assert item["tasks"] == ["kept"]


def test_cleared_key_still_blocks_a_repeat(table):
    recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A)
    recovery_state.clear_pending_checkin(PATIENT_ID)

    assert recovery_state.save_pending_checkin(PATIENT_ID, _checkin(KEY_A), KEY_A) is False


# ---------- The proactive rules: every value sent must be used (DynamoDB rejects unused ones) ----------

import re as _re


class StrictTable:
    """Rejects a request whose ExpressionAttributeValues are not all used, like DynamoDB."""

    def __init__(self, stored_date=None):
        self.stored_date = stored_date
        self.requests = []

    def get_item(self, Key, ProjectionExpression):
        return {"Item": {"checkins_today_date": self.stored_date}} if self.stored_date else {}

    def update_item(self, Key, UpdateExpression, ConditionExpression=None, ExpressionAttributeValues=None, **_):
        used = set(_re.findall(r":[a-z_]+", f"{UpdateExpression} {ConditionExpression or ''}"))
        unused = set(ExpressionAttributeValues or {}) - used
        if unused:
            raise ClientError({"Error": {"Code": "ValidationException",
                                         "Message": f"unused in expressions: {sorted(unused)}"}}, "UpdateItem")
        self.requests.append((UpdateExpression, ConditionExpression))


@pytest.mark.parametrize("stored_date", [None, "2026-10-22", "2026-10-23"])
def test_proactive_save_uses_every_value_on_every_branch(monkeypatch, stored_date):
    table = StrictTable(stored_date)
    monkeypatch.setattr(recovery_state, "table", table)

    assert recovery_state.save_pending_checkin(
        PATIENT_ID, _checkin(KEY_A), KEY_A, today="2026-10-23", max_per_day=6,
    ) is True

    update, condition = table.requests[0]
    assert "attribute_not_exists(pending_checkin)" in condition
    if stored_date == "2026-10-23":
        assert "size(checkins_today_ids) < :max" in condition
    else:
        assert "checkins_today_date = :today" in update
