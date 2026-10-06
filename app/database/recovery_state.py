"""Read and save recovery plans in DynamoDB and record medication or task completion."""

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone, date

import boto3

from app import config
from app.database.event_history import append_event, build_idempotency_key
from app.models.recovery_model import RecoveryState


dynamodb = boto3.resource(
    "dynamodb",
    region_name=config.REGION,
)

table = dynamodb.Table(
    config.RECOVERY_STATE_TABLE
)


def save_recovery_state(
    state: RecoveryState | dict,
) -> None:
    """Save a RecoveryState dataclass or an existing DynamoDB dictionary."""
    if is_dataclass(state):
        item = asdict(state)
    elif isinstance(state, dict):
        item = state
    else:
        raise TypeError("state must be a RecoveryState dataclass or dictionary")

    table.put_item(
        Item=item
    )


def get_recovery_state(
    patient_id: str,
) -> dict | None:

    response = table.get_item(
        Key={
            "patient_id": patient_id
        }
    )

    return response.get("Item")


def get_medications(
    patient_id: str,
    date: str | None = None,
) -> list[dict]:
    """
    Return the patient's medications from their current
    RecoveryState.

    `date` is accepted now because the service will later
    support date/occurrence filtering.

    For the current MVP, medications are stored as part of
    the current RecoveryState, so we return the list as-is.
    """
    # Read the patient's current state from DynamoDB.
    state = get_recovery_state(
        patient_id
    )
    # Patient does not have a RecoveryState yet.
    if not state:
        return []
    # Return medications.
    # Using .get(..., []) safely handles a missing medications field.
    return state.get(
        "medications",
        [],
    )


def get_today_tasks(
    patient_id: str,
    date: str | None = None,
) -> list[dict]:
    """
    Return the patient's current recovery tasks.

    Later we can interpret scheduling fields such as
    "daily", "morning", etc.

    For the current MVP, return the current task list.
    """
    # Load the current RecoveryState.
    state = get_recovery_state(
        patient_id
    )
    # No state means no tasks.
    if not state:
        return []
    return state.get(
        "tasks",
        [],
    )


def _find_medication(
    state: dict,
    medication_id: str,
) -> dict | None:
    """Find one medication inside RecoveryState by its ID."""
    medications = state.get("medications", [])
    for medication in medications:
        if medication.get("id") == medication_id:
            return medication
    return None


def _find_task(
    state: dict,
    task_id: str,
) -> dict | None:
    """Find one recovery task inside RecoveryState by ID."""
    tasks = state.get("tasks", [])
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def mark_medication_taken(
    patient_id: str,
    medication_id: str,
    idempotency_key: str,
) -> dict:
    """Complete a current medication, persist state, and record its history."""
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")
    state = get_recovery_state(patient_id)
    if not state:
        raise ValueError(f"No RecoveryState found for patient {patient_id}")

    medication = _find_medication(state, medication_id)

    if medication is None:
        raise ValueError(f"Medication not found: {medication_id}")

    old_status = medication.get("status", "pending")
    if old_status == "completed":
        return {
            "success": True,
            "already_completed": True,
            "medication": medication,
            "event": None,
        }

    completed_at = datetime.now(timezone.utc).isoformat()
    medication["status"] = "completed"
    medication["completed_at"] = completed_at
    state["last_updated"] = completed_at
    save_recovery_state(state)

    event = append_event(
        patient_id=patient_id,
        event_type="medication_taken",
        details={
            "medication_id": medication_id,
            "name": medication.get("name"),
            "old_status": old_status,
            "new_status": "completed",
            "completed_at": completed_at,
        },
        idempotency_key=idempotency_key,
    )
    return {
        "success": True,
        "already_completed": False,
        "medication": medication,
        "event": event,
    }


def mark_task_completed(
    patient_id: str,
    task_id: str,
    occurrence_key: str | None = None,
    *,
    idempotency_key: str | None = None,
) -> dict:
    """Complete a current task, persist state, and append its history event."""
    if idempotency_key is not None and not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")
    state = get_recovery_state(patient_id)
    if not state:
        raise ValueError("Recovery state not found")

    task = _find_task(state, task_id)

    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    old_status = task.get("status", "pending")
    if old_status == "completed":
        return {
            "success": True,
            "already_completed": True,
            "task": task,
            "event": None,
        }

    if idempotency_key is None:
        if occurrence_key is None:
            occurrence_key = date.today().isoformat()
        idempotency_key = build_idempotency_key(patient_id, task_id, occurrence_key)

    completed_at = datetime.now(timezone.utc).isoformat()
    task["status"] = "completed"
    task["completed_at"] = completed_at
    state["last_updated"] = completed_at

    save_recovery_state(state)

    event = append_event(
        patient_id=patient_id,
        event_type="task_completed",
        details={
            "task_id": task_id,
            "description": task.get("description"),
            "old_status": old_status,
            "new_status": "completed",
            "completed_at": completed_at,
        },
        idempotency_key=idempotency_key,
    )
    return {
        "success": True,
        "already_completed": False,
        "task": task,
        "event": event,
    }
