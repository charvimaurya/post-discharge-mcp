"""AWS Lambda entry point for proactive recovery reminders."""

from app.clock import get_patient_datetime, parse_demo_now

from app.database.recovery_state import (
    get_medications,
    get_recovery_state,
    get_today_tasks,
    save_pending_checkin,
)

from app.reminders.selector import find_due_reminder
from app.reminders.text import build_reminder_text


DEMO_PATIENT_ID = "demo_patient_001"


def _first_name(state: dict) -> str:
    """
    Resolve the patient's first name from RecoveryState.

    Adjust this helper only if your state uses a different existing field.
    """
    if state.get("first_name"):
        return state["first_name"]

    if state.get("patient_name"):
        return str(state["patient_name"]).split()[0]

    return "there"


def handler(event, context):
    # Manual test runs may pass demo_now; scheduled runs never do,
    # so they always use the real shared clock.
    demo_now = None

    if event.get("demo_now"):
        try:
            demo_now = parse_demo_now(str(event["demo_now"]))
        except ValueError as exc:
            return {
                "created": False,
                "reason": "invalid_demo_now",
                "error": str(exc),
            }

    patient_id = event.get(
        "patient_id",
        DEMO_PATIENT_ID,
    )

    state = get_recovery_state(patient_id)

    if not state:
        return {
            "created": False,
            "reason": "patient_not_found",
        }

    # Plan clock times are local, so "now" and "today" must be too.
    now = get_patient_datetime(
        state.get("timezone") or "Europe/London",
        now=demo_now,
    )

    today = now.date().isoformat()

    tasks = get_today_tasks(
        patient_id,
        today,
    )

    medications = get_medications(
        patient_id,
        today,
    )

    reminder = find_due_reminder(
        tasks=tasks,
        medications=medications,
        now=now,
    )

    if reminder is None:
        return {
            "created": False,
            "reason": "nothing_due",
        }

    text = build_reminder_text(
        first_name=_first_name(state),
        item=reminder,
        now=now,
    )

    # Reminder identity is the occurrence, so one occurrence is
    # reminded at most once.
    occurrence_id = reminder["occurrence_id"]
    checkin_key = f"{today}#{occurrence_id}"

    pending_checkin = {
        "checkin_id": checkin_key,
        "occurrence_id": occurrence_id,
        "item_type": reminder["item_type"],
        "date": today,
        "clock_time": reminder["clock_time"],
        "text": text,
        "created_at": now.isoformat(),
    }

    created = save_pending_checkin(
        patient_id,
        pending_checkin,
        checkin_key,
    )

    if not created:
        return {
            "created": False,
            "reason": "already_reminded",
            "checkin_id": checkin_key,
        }

    return {
        "created": True,
        "pending_checkin": pending_checkin,
    }