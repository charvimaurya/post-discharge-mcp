"""
Reset the AfterWard demo patient to a clean "nothing done yet" state.

Used by scripts/reset_demo_patient.py and the bridge's POST /reset route.

What this does (demo_patient_001 ONLY):

1. Deletes today's task/medication completion rows, across all
   query pages.
2. Resets legacy fields inside the current RecoveryState:
   - tasks        → status="pending", completed_at removed
   - medications  → status="pending", completed_at removed
3. Clears pending_checkin, last_checkin_key, last_chat_at, today's
   check-in list and scheduled check-ins, so reminders can fire again.
4. Sets first_name="Margaret" (synthetic demo patient) if the plan has
   no name yet, so the reminder greets her by name.
5. Updates last_updated using the shared clock (app.clock).

What this does NOT do:

- re-run extraction or upload a PDF
- change document_id, medications, tasks, appointments,
  restrictions, warning signs, monitoring or RAG vectors
- set DEMO_FIXED_NOW
"""

import os
from datetime import datetime, timedelta, timezone

from boto3.dynamodb.conditions import Key

from app.alexa import feed as alexa_feed
from app.clock import (
    DEFAULT_TIMEZONE, allows_test_hooks, get_current_date, get_current_datetime, system_now_utc,
)
from app.database.event_history import event_table
from app.database.recovery_state import (
    get_recovery_state,
    save_recovery_state,
)


# Hard-coded on purpose: this must never touch a real patient.
PATIENT_ID = "demo_patient_001"

# Synthetic demo patient (Margaret Ellis). Read by the reminder Lambda.
DEMO_FIRST_NAME = "Margaret"


class NoPlanToReset(Exception):
    """The demo patient has no RecoveryState yet, so there is nothing to reset."""


def delete_event_history(patient_id: str, today: str) -> int:
    """
    Delete completion rows for one patient on the supplied clock date.

    Pages through the query with LastEvaluatedKey so more than
    one page (1 MB) of events is still fully deleted.
    """

    deleted = 0

    query_kwargs = {
        "KeyConditionExpression": Key("patient_id").eq(patient_id),
        # Only the key attributes are needed to delete.
        # "timestamp" is a DynamoDB reserved word.
        "ProjectionExpression": "patient_id, #ts, event_type, details",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
    }

    with event_table.batch_writer() as batch:

        while True:
            response = event_table.query(**query_kwargs)

            for item in response.get("Items", []):
                if item.get("event_type") not in {"task_completed", "medication_taken"}:
                    continue
                details = item.get("details") or {}
                occurrence_id = str(details.get("occurrence_id") or "")
                if len(occurrence_id.split("#")) < 3 or occurrence_id.split("#")[-2] != today:
                    continue
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


def reset_items(items: list[dict]) -> int:
    """Set each item back to pending and drop completed_at."""

    for item in items:
        item["status"] = "pending"
        item.pop("completed_at", None)

    return len(items)


def reset_recovery_state(patient_id: str) -> tuple[int, int]:
    """
    Reset completion fields inside the current RecoveryState.

    Everything else in the item, including document_id and the
    plan contents, is written back unchanged.
    """

    state = get_recovery_state(patient_id)

    if not state:
        raise NoPlanToReset(f"No RecoveryState found for {patient_id}; nothing to reset.")

    tasks_reset = reset_items(state.get("tasks") or [])
    medications_reset = reset_items(state.get("medications") or [])

    state["pending_checkin"] = None
    state.pop("last_checkin_key", None)

    # A clean start for check-ins too: no "she just chatted", no record of
    # today's check-ins, nothing scheduled.
    for field in ("last_chat_at", "checkins_today_date", "checkins_today_ids", "scheduled_checkins"):
        state.pop(field, None)

    # The name read from the letter is kept; the demo name is only a fallback
    # for a plan saved before names were read.
    state["first_name"] = state.get("first_name") or DEMO_FIRST_NAME

    state["last_updated"] = get_current_datetime().isoformat()
    # Real time, so the idle reset below knows this is a fresh start.
    state["demo_reset_at"] = system_now_utc().isoformat()

    save_recovery_state(state)

    return tasks_reset, medications_reset


def reset_demo_patient() -> dict:
    """
    Reset demo_patient_001: delete today's completions and clear completion state.

    Raises NoPlanToReset when there is no plan yet. Returns the counts.
    """

    state = get_recovery_state(PATIENT_ID)

    if not state:
        raise NoPlanToReset(f"No RecoveryState found for {PATIENT_ID}; nothing to reset.")

    today = get_current_date(state.get("timezone") or DEFAULT_TIMEZONE)
    events_deleted = delete_event_history(PATIENT_ID, today)
    tasks_reset, medications_reset = reset_recovery_state(PATIENT_ID)
    # The /demo screen's Alexa conversation starts again too.
    alexa_feed.clear()

    return {
        "events_deleted": events_deleted,
        "tasks_reset": tasks_reset,
        "medications_reset": medications_reset,
    }


# The demo clock is frozen (always 07:00 on the same day), so yesterday's ticks
# and reminders would still look like "today". After this many real hours with
# no chat and no reset, the next visit starts fresh. 0 turns it off.
IDLE_RESET_HOURS = 0


def idle_reset_hours() -> float:
    """Opt-in demo expiry. Missing/invalid settings never delete saved progress."""

    try:
        return float(os.getenv("DEMO_IDLE_RESET_HOURS", IDLE_RESET_HOURS))
    except ValueError:
        return IDLE_RESET_HOURS


def last_active_at(state: dict) -> datetime | None:
    """The later of her last chat and the last reset (both real time), or None."""

    times = []

    for field in ("last_chat_at", "demo_reset_at"):
        try:
            at = datetime.fromisoformat(str(state[field]))
        except (KeyError, ValueError):
            continue
        times.append(at if at.tzinfo else at.replace(tzinfo=timezone.utc))

    return max(times, default=None)


def reset_if_idle(now_utc: datetime | None = None) -> bool:
    """
    Reset the demo patient if nobody has used the demo for idle_reset_hours().

    Never in production, and never when there is no plan. A record with no
    chat or reset time yet counts as idle. Returns True if it reset.
    """

    hours = idle_reset_hours()

    if hours <= 0 or not allows_test_hooks():
        return False

    state = get_recovery_state(PATIENT_ID)

    if not state:
        return False

    last = last_active_at(state)
    now = now_utc or system_now_utc()

    if last is not None and now - last < timedelta(hours=hours):
        return False

    reset_demo_patient()
    return True
