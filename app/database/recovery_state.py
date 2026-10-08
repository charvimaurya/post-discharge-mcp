"""Read and save recovery plans in DynamoDB and record medication or task completion."""

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone, date

import boto3

from app import config
from app.clock import get_current_datetime
from app.database.event_history import (
    append_event,
    build_idempotency_key,
    get_events,
)
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


def _medication_occurrence_count(medication: dict) -> int:
    """How many doses of a medication are due in one day."""

    # PRN medicines should not be expanded into guessed
    # scheduled doses.
    if medication.get("as_needed"):
        return 1

    # DynamoDB returns numbers as Decimal, which
    # range() does not accept.
    return max(
        int(medication.get("times_per_day") or 0),
        len(medication.get("time_of_day") or []),
        1,
    )


def _parse_date(value) -> date | None:
    """Parse "YYYY-MM-DD" (or an ISO timestamp); None if invalid."""

    if not value:
        return None

    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _is_before_discharge(
    state: dict,
    date_text: str,
) -> bool:
    """
    True when date_text falls before the plan's discharge_date.

    No occurrences exist before the patient goes home. A missing
    or invalid discharge_date (or requested date) keeps the
    existing behaviour, so this returns False.
    """

    discharge = _parse_date(state.get("discharge_date"))
    requested = _parse_date(date_text)

    if discharge is None or requested is None:
        return False

    return requested < discharge


def get_medications(
    patient_id: str,
    date: str | None = None,
) -> list[dict]:
    """
    Return medication occurrences for the requested day.

    Repeated scheduled medicines become separate daily
    occurrences, such as morning, midday, evening and bedtime.

    PRN medicines remain as a single untimed occurrence.
    """

    state = get_recovery_state(
        patient_id
    )

    if not state:
        return []

    if not date:
        raise ValueError(
            "date is required when building medication occurrences"
        )

    # Nothing is due before the patient is discharged.
    if _is_before_discharge(state, date):
        return []

    # -------------------------------------------------
    # READ COMPLETED MEDICATION OCCURRENCES
    # -------------------------------------------------

    events = get_events(
        patient_id
    )

    completed = {}

    for event in events:

        if event.get("event_type") != "medication_taken":
            continue

        details = event.get(
            "details",
            {},
        )

        occurrence_id = details.get(
            "occurrence_id"
        )

        if not occurrence_id:
            # Ignore older pre-occurrence medication events.
            continue

        completed[
            occurrence_id
        ] = (
            details.get("completed_at")
            or event.get("recorded_at")
        )

    # -------------------------------------------------
    # EXPAND MEDICATIONS INTO DAILY OCCURRENCES
    # -------------------------------------------------

    occurrences = []

    for medication in state.get(
        "medications",
        [],
    ):

        time_of_day = (
            medication.get("time_of_day")
            or []
        )

        occurrence_count = _medication_occurrence_count(
            medication
        )

        for index in range(
            occurrence_count
        ):

            occurrence_number = (
                index + 1
            )

            occurrence_id = build_occurrence_id(
                medication["id"],
                date,
                occurrence_number,
            )

            occurrence = dict(
                medication
            )

            occurrence[
                "medication_id"
            ] = medication["id"]

            occurrence[
                "occurrence_id"
            ] = occurrence_id

            occurrence[
                "occurrence_number"
            ] = occurrence_number

            occurrence[
                "occurrence_total"
            ] = occurrence_count

            occurrence[
                "time_of_day_label"
            ] = (
                time_of_day[index]
                if index < len(time_of_day)
                else None
            )

            if occurrence_id in completed:

                occurrence[
                    "status"
                ] = "completed"

                occurrence[
                    "completed_at"
                ] = completed[
                    occurrence_id
                ]

            else:

                occurrence[
                    "status"
                ] = "pending"

                occurrence.pop(
                    "completed_at",
                    None,
                )

            occurrences.append(
                occurrence
            )

    return occurrences


def build_occurrence_id(
    item_id: str,
    date_text: str,
    occurrence_number: int,
) -> str:
    """
    Build a stable ID for one occurrence on one day.

    Example:

    task_de859a844c#2026-10-23#1
    """
    return (
        f"{item_id}"
        f"#{date_text}"
        f"#{occurrence_number}"
    )


def parse_occurrence_id(
    occurrence_id: str,
) -> tuple[str, str, int]:
    """
    Split an occurrence ID back into:

    base item ID
    date
    occurrence number
    """
    try:
        item_id, date_text, number_text = (
            occurrence_id.rsplit("#", 2)
        )
        occurrence_number = int(
            number_text
        )
    except (AttributeError, ValueError):
        raise ValueError(
            f"Invalid occurrence id: {occurrence_id}"
        ) from None

    if not item_id or not date_text or occurrence_number < 1:
        raise ValueError(
            f"Invalid occurrence id: {occurrence_id}"
        )

    return item_id, date_text, occurrence_number


def _occurrence_count(task: dict) -> int:
    """How many times a task is due in one day (at least once)."""
    times_per_day = task.get("times_per_day")

    if times_per_day:
        return max(int(times_per_day), 1)

    return max(
        len(task.get("clock_times") or []),
        len(task.get("time_of_day") or []),
        1,
    )


def _completed_task_occurrences(
    patient_id: str,
    date_text: str,
) -> dict[str, str]:
    """
    Return {occurrence_id: completed_at} for one day,
    rebuilt from Event History.

    Events written before occurrences existed have no
    occurrence_id and are ignored.
    """
    completed = {}

    for event in get_events(patient_id):

        if event.get("event_type") != "task_completed":
            continue

        details = event.get("details") or {}
        occurrence_id = details.get("occurrence_id")

        if not occurrence_id:
            continue

        if details.get("date") != date_text:
            continue

        # New events carry the demo-clock completed_at;
        # older events fall back to the real write time.
        completed[
            occurrence_id
        ] = (
            details.get("completed_at")
            or event.get("recorded_at")
        )

    return completed


def get_today_tasks(
    patient_id: str,
    date: str | None = None,
) -> list[dict]:
    """
    Build today's task occurrences from the base RecoveryState.

    A task due multiple times a day becomes multiple
    occurrences.

    Example:

        walk twice daily

    becomes:

        walk occurrence 1 of 2
        walk occurrence 2 of 2

    The base task itself stays unchanged in RecoveryState.
    Completion comes from Event History, per occurrence.
    """

    state = get_recovery_state(
        patient_id
    )

    if not state:
        return []

    # Use the supplied application-controlled date.
    #
    # The caller currently gets this from app.clock, so
    # the browser/patient is not allowed to choose the date.
    if date is None:
        date = datetime.now(
            timezone.utc
        ).date().isoformat()

    # Nothing is due before the patient is discharged.
    if _is_before_discharge(state, date):
        return []

    completed = _completed_task_occurrences(
        patient_id,
        date,
    )

    occurrences = []

    for task in state.get("tasks", []):

        total = _occurrence_count(task)
        clock_times = task.get("clock_times") or []
        time_of_day = task.get("time_of_day") or []

        for index in range(total):

            occurrence_number = index + 1

            occurrence_id = build_occurrence_id(
                task["id"],
                date,
                occurrence_number,
            )

            occurrence = dict(task)

            occurrence["task_id"] = task["id"]
            occurrence["occurrence_id"] = occurrence_id
            occurrence["occurrence_number"] = occurrence_number
            occurrence["occurrence_total"] = total

            occurrence[
                "clock_time"
            ] = (
                clock_times[index]
                if index < len(
                    clock_times
                )
                else None
            )

            occurrence[
                "time_of_day_label"
            ] = (
                time_of_day[index]
                if index < len(
                    time_of_day
                )
                else None
            )

            # Completion belongs to the occurrence,
            # not the base task.
            if occurrence_id in completed:
                occurrence[
                    "status"
                ] = "completed"
                occurrence[
                    "completed_at"
                ] = completed[
                    occurrence_id
                ]
            else:
                occurrence[
                    "status"
                ] = "pending"
                occurrence.pop(
                    "completed_at",
                    None,
                )

            occurrences.append(
                occurrence
            )

    return occurrences


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


def _find_occurrence(
    occurrences: list[dict],
    occurrence_id: str,
) -> dict | None:
    """Find one occurrence in a reader's result by its ID."""

    return next(
        (
            item
            for item in occurrences
            if item.get("occurrence_id") == occurrence_id
        ),
        None,
    )


def mark_medication_taken(
    patient_id: str,
    occurrence_id: str,
    today: str,
) -> dict:
    """
    Record exactly one medication occurrence as taken.

    The base medication in RecoveryState is not marked
    completed. Completion is stored in Event History.
    """

    state = get_recovery_state(
        patient_id
    )

    if not state:
        raise ValueError(
            f"No RecoveryState found for patient {patient_id}"
        )

    # -------------------------------------------------
    # PARSE OCCURRENCE
    # -------------------------------------------------

    (
        medication_id,
        occurrence_date,
        occurrence_number,
    ) = parse_occurrence_id(
        occurrence_id
    )

    # -------------------------------------------------
    # THE OCCURRENCE MUST BE DUE TODAY
    #
    # Use the same reader the patient sees, so a forged ID
    # (wrong day, before discharge, unknown medicine, or a
    # dose number that does not exist) can never be written.
    # -------------------------------------------------

    occurrence = _find_occurrence(
        get_medications(patient_id, today),
        occurrence_id,
    )

    if occurrence is None:
        raise ValueError(
            "There is no matching dose scheduled for today."
        )

    # -------------------------------------------------
    # ONE EVENT PER OCCURRENCE
    #
    # The occurrence is the idempotency key, so reporting
    # the same dose twice is safe.
    # -------------------------------------------------

    idempotency_key = build_idempotency_key(
        patient_id,
        medication_id,
        f"{occurrence_date}#{occurrence_number}",
    )

    # Use the shared clock so DEMO_FIXED_NOW also controls
    # the time the patient sees.
    completed_at = get_current_datetime().isoformat()

    event_result = append_event(
        patient_id=patient_id,
        event_type="medication_taken",
        details={
            "medication_id": medication_id,
            "occurrence_id": occurrence_id,
            "occurrence_number": occurrence_number,
            "occurrence_total": occurrence["occurrence_total"],
            "date": occurrence_date,
            "name": occurrence.get("name"),
            "completed_at": completed_at,
        },
        idempotency_key=idempotency_key,
    )

    # -------------------------------------------------
    # REBUILD TODAY'S OCCURRENCES
    #
    # get_medications() reads Event History, so this gives
    # us the authoritative state after the write.
    # -------------------------------------------------

    taken_occurrence = _find_occurrence(
        get_medications(patient_id, occurrence_date),
        occurrence_id,
    )

    return {
        "success": True,
        "already_completed": event_result[
            "duplicate"
        ],
        "medication": taken_occurrence,
        "event": event_result,
    }


def mark_task_completed(
    patient_id: str,
    occurrence_id: str,
    today: str,
) -> dict:
    """
    Record ONE task occurrence as completed.

    Only Event History is written. The base task in
    RecoveryState is left unchanged; get_today_tasks()
    rebuilds each occurrence's status from these events,
    so completing walk 1 never completes walk 2.
    """

    # -------------------------------------------------
    # 1. PARSE THE OCCURRENCE ID
    # -------------------------------------------------
    task_id, occurrence_date, occurrence_number = (
        parse_occurrence_id(occurrence_id)
    )

    # -------------------------------------------------
    # 2. LOAD CURRENT RECOVERY STATE
    # -------------------------------------------------
    state = get_recovery_state(patient_id)
    if not state:
        raise ValueError("Recovery state not found")

    # -------------------------------------------------
    # 3-5. THE OCCURRENCE MUST BE DUE TODAY
    #
    # Use the same reader the patient sees, so a forged ID
    # (wrong day, before discharge, unknown task, or an
    # occurrence number that does not exist) can never be
    # written.
    # -------------------------------------------------
    occurrence = _find_occurrence(
        get_today_tasks(patient_id, today),
        occurrence_id,
    )

    if occurrence is None:
        raise ValueError(
            "There is no matching task scheduled for today."
        )

    # -------------------------------------------------
    # 6. ONE EVENT PER OCCURRENCE
    #
    # The occurrence is the idempotency key, so reporting
    # the same occurrence twice is safe.
    # -------------------------------------------------
    idempotency_key = build_idempotency_key(
        patient_id,
        task_id,
        f"{occurrence_date}#{occurrence_number}",
    )

    # Use the shared clock so DEMO_FIXED_NOW also controls
    # the completion time the patient sees.
    completed_at = get_current_datetime().isoformat()

    event_result = append_event(
        patient_id=patient_id,
        event_type="task_completed",
        details={
            "task_id": task_id,
            "occurrence_id": occurrence_id,
            "occurrence_number": occurrence_number,
            "occurrence_total": occurrence["occurrence_total"],
            "date": occurrence_date,
            "description": occurrence.get(
                "description"
            ),
            "completed_at": completed_at,
        },
        idempotency_key=idempotency_key,
    )

    # -------------------------------------------------
    # 7. REBUILD TODAY'S OCCURRENCES
    #
    # get_today_tasks() reads Event History, so this gives
    # us the authoritative state after the write.
    # -------------------------------------------------
    completed_occurrence = _find_occurrence(
        get_today_tasks(patient_id, occurrence_date),
        occurrence_id,
    )

    return {
        "success": True,
        "already_completed": event_result[
            "duplicate"
        ],
        "task": completed_occurrence,
        "event": event_result,
    }
