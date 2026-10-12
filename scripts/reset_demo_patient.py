"""
Reset the AfterWard demo patient to a clean "nothing done yet" state.

What this does (demo_patient_001 ONLY):

1. Deletes today's task/medication completion rows, across all
   query pages. Task and medication completion now lives here,
   so this clears today's recorded occurrences.
2. Resets legacy fields inside the current RecoveryState:
   - tasks        → status="pending", completed_at removed
   - medications  → status="pending", completed_at removed
3. Clears pending_checkin, last_checkin_key, last_chat_at, today's
   check-in list and scheduled check-ins, so reminders can fire again.
4. Sets first_name="Margaret" (synthetic demo patient), so the
   reminder greets her by name. Re-uploading a letter replaces the
   whole record and removes it, so run this script after an upload.
5. Updates last_updated using the shared clock (app.clock).

What this does NOT do:

- re-run extraction or upload a PDF
- change document_id, medications, tasks, appointments,
  restrictions, warning signs, monitoring or RAG vectors
- set DEMO_FIXED_NOW

Usage:

    python scripts/reset_demo_patient.py --confirm
"""

import argparse
import sys
from pathlib import Path

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from boto3.dynamodb.conditions import Key

from app import config
from app.clock import DEFAULT_TIMEZONE, get_current_date, get_current_datetime
from app.database.event_history import event_table
from app.database.recovery_state import (
    get_recovery_state,
    save_recovery_state,
)


# Hard-coded on purpose: this script must never touch a real patient.
PATIENT_ID = "demo_patient_001"

# Synthetic demo patient (Margaret Ellis). Read by the reminder Lambda.
DEMO_FIRST_NAME = "Margaret"


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
        raise SystemExit(
            f"No RecoveryState found for {patient_id}; nothing to reset."
        )

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

    save_recovery_state(state)

    return tasks_reset, medications_reset


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Reset {PATIENT_ID}: delete current-date completions and "
            "clear completion state. The recovery plan is kept."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Without it, nothing is changed.",
    )
    args = parser.parse_args()

    if not args.confirm:
        print(
            f"This will delete current-date completions for {PATIENT_ID} "
            f"in {config.EVENT_HISTORY_TABLE} and reset completion "
            f"state in {config.RECOVERY_STATE_TABLE}.\n"
            "Nothing was changed. Re-run with --confirm:\n\n"
            "    python scripts/reset_demo_patient.py --confirm"
        )
        sys.exit(1)

    state = get_recovery_state(PATIENT_ID)
    if not state:
        raise SystemExit(f"No RecoveryState found for {PATIENT_ID}; nothing to reset.")
    today = get_current_date(state.get("timezone") or DEFAULT_TIMEZONE)
    events_deleted = delete_event_history(PATIENT_ID, today)
    tasks_reset, medications_reset = reset_recovery_state(PATIENT_ID)

    print(f"Patient reset:               {PATIENT_ID}")
    print(f"Event History items deleted: {events_deleted}")
    print(f"Tasks reset:                 {tasks_reset}")
    print(f"Medications reset:           {medications_reset}")


if __name__ == "__main__":
    main()
