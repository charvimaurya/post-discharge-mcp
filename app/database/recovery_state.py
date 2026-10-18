"""Read and save recovery plans in DynamoDB and record medication or task completion."""

import re
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta

import boto3
from botocore.exceptions import ClientError

from app import config
from app.medication_safety import medication_withdrawn
from app.clock import DEFAULT_TIMEZONE, get_current_date, get_current_datetime
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
        },
        ConsistentRead=True,
    )

    return response.get("Item")


def save_pending_checkin(
    patient_id: str,
    pending_checkin: dict,
    checkin_key: str,
    *,
    today: str | None = None,
    max_per_day: int | None = None,
    scheduled_checkins: list | None = None,
) -> bool:
    """
    Atomically store a check-in unless the rules forbid it.

    Always: last_checkin_key must differ from checkin_key.

    With `today` (the proactive engine), the same single write also
    requires that no check-in is waiting, that checkin_key was not
    already used today, and that fewer than max_per_day were made
    today; it records checkin_key in today's list. If
    scheduled_checkins is given, it replaces the stored list (the
    fired entry removed).

    Returns True when written, False when a condition failed.
    """

    values = {":pending": pending_checkin, ":checkin_key": checkin_key}
    sets = ["pending_checkin = :pending", "last_checkin_key = :checkin_key"]
    conditions = ["(attribute_not_exists(last_checkin_key) OR last_checkin_key <> :checkin_key)"]

    if today is not None:
        values.update({":today": today, ":one": [checkin_key], ":null": "NULL"})
        conditions.append(
            "(attribute_not_exists(pending_checkin) OR attribute_type(pending_checkin, :null))"
        )

        # Today's list of check-ins: append, or start a new day.
        # (DynamoDB rejects any value the expressions do not use, so :max is
        # added only on the branch that checks it.)
        continuing = None
        try:
            current = table.get_item(
                Key={"patient_id": patient_id},
                ProjectionExpression="checkins_today_date",
            ).get("Item") or {}
            continuing = current.get("checkins_today_date") == today
        except ClientError:
            continuing = False

        if continuing:
            sets.append("checkins_today_ids = list_append(checkins_today_ids, :one)")
            limit = ""
            if max_per_day is not None:
                values[":max"] = max_per_day
                limit = " AND size(checkins_today_ids) < :max"
            conditions.append(
                f"(checkins_today_date = :today AND NOT contains(checkins_today_ids, :checkin_key){limit})"
            )
        else:
            sets.extend(["checkins_today_ids = :one", "checkins_today_date = :today"])
            conditions.append("(attribute_not_exists(checkins_today_date) OR checkins_today_date <> :today)")

    if scheduled_checkins is not None:
        values[":scheduled"] = scheduled_checkins
        sets.append("scheduled_checkins = :scheduled")

    try:
        table.update_item(
            Key={
                "patient_id": patient_id,
            },
            UpdateExpression="SET " + ", ".join(sets),
            ConditionExpression=" AND ".join(conditions) if today is not None else (
                "attribute_not_exists(last_checkin_key) "
                "OR last_checkin_key <> :checkin_key"
            ),
            ExpressionAttributeValues=values,
        )

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")

        if error_code == "ConditionalCheckFailedException":
            return False

        raise

    return True


def add_scheduled_checkin(patient_id: str, entry: dict) -> None:
    """Add one {checkin_id, due_at, type, text, occurrence_id} for the engine to fire later."""

    table.update_item(
        Key={"patient_id": patient_id},
        UpdateExpression=(
            "SET scheduled_checkins = list_append(if_not_exists(scheduled_checkins, :empty), :entry)"
        ),
        ExpressionAttributeValues={":entry": [entry], ":empty": []},
    )


def record_chat_activity(patient_id: str, at_utc_iso: str) -> None:
    """When she last spoke to AfterWard (real time), so no check-in interrupts her."""

    table.update_item(
        Key={"patient_id": patient_id},
        UpdateExpression="SET last_chat_at = :at",
        ExpressionAttributeValues={":at": at_utc_iso},
    )


def record_greeting(patient_id: str, local_date: str) -> None:
    """The patient-local day AfterWard last greeted her, so a return visit says "Welcome back".
    A new letter saves a fresh record, so the next visit is a first greeting again."""

    table.update_item(
        Key={"patient_id": patient_id},
        UpdateExpression="SET greeted_on = :day",
        ExpressionAttributeValues={":day": local_date},
    )


def clear_pending_checkin(
    patient_id: str,
) -> None:
    """
    Remove the waiting reminder.

    last_checkin_key is kept on purpose, so the same occurrence is
    not reminded again after the patient responds.
    """

    table.update_item(
        Key={
            "patient_id": patient_id,
        },
        UpdateExpression="REMOVE pending_checkin",
    )


def get_pending_checkin(
    patient_id: str,
) -> dict | None:
    """Return the waiting reminder, or None."""

    response = table.get_item(
        Key={
            "patient_id": patient_id,
        },
        ProjectionExpression="pending_checkin",
    )

    return (response.get("Item") or {}).get("pending_checkin")


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


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fourteen": 14, "twenty": 20, "twenty-one": 21,
    "twenty-eight": 28, "thirty": 30,
}

# "for 14 days", "Stop after 5 days.", "for 6 weeks". Only an explicit
# number from the letter sets an end; "Continue as directed" never does.
_DURATION = re.compile(
    r"\b(?:for|after)\s+(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(days?|weeks?)\b",
    re.IGNORECASE,
)


def plan_end_date(item: dict, state: dict) -> date | None:
    """
    The last day an item applies, from its duration_text and the
    discharge date, or None if the letter gives no end.

    The discharge day counts as day 1, so "Stop after 5 days" from
    16 October covers 16 to 20 October.
    """

    explicit_end = _parse_date(item.get("end_date"))
    if explicit_end is not None:
        return explicit_end

    discharge = _parse_date(state.get("discharge_date"))
    match = _DURATION.search(str(item.get("duration_text") or ""))

    if discharge is None or match is None:
        return None

    number, unit = match.groups()
    count = int(number) if number.isdigit() else _NUMBER_WORDS[number.lower()]
    days = count * 7 if unit.lower().startswith("week") else count

    if days < 1:
        return None

    return discharge + timedelta(days=days - 1)


def _has_ended(item: dict, state: dict, date_text: str) -> bool:
    """True when date_text is after the item's last day."""

    end = plan_end_date(item, state)
    requested = _parse_date(date_text)

    return end is not None and requested is not None and requested > end


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

    if date is None:
        date = get_current_date(state.get("timezone") or DEFAULT_TIMEZONE)

    # Nothing is due before the patient is discharged.
    if _is_before_discharge(state, date):
        return []

    # -------------------------------------------------
    # READ COMPLETED MEDICATION OCCURRENCES
    # -------------------------------------------------

    completed = _completed(_completion_rounds(get_events(patient_id), "medication"))

    # -------------------------------------------------
    # EXPAND MEDICATIONS INTO DAILY OCCURRENCES
    # -------------------------------------------------

    occurrences = []

    for medication in state.get(
        "medications",
        [],
    ):

        # Not listed after the end the letter gives ("Stop after 5 days").
        if medication_withdrawn(medication) or _has_ended(medication, state, date):
            continue

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


# Completion and undo events, per kind of item. Event History is
# append-only: an undo is a new event, never a deletion.
_EVENT_TYPES = {
    "medication": ("medication_taken", "medication_undone"),
    "task": ("task_completed", "task_undone"),
}


def _completion_rounds(events: list[dict], kind: str, date_text: str | None = None) -> dict[str, dict]:
    """
    {occurrence_id: {"taken": n, "undone": m, "completed_at": ...}} from Event History.

    An occurrence is done when it has more "taken" events than "undone"
    ones. Each save after an undo is a new round with its own key.
    """

    taken_type, undone_type = _EVENT_TYPES[kind]
    rounds: dict[str, dict] = {}

    for event in events:
        event_type = event.get("event_type")

        if event_type not in (taken_type, undone_type):
            continue

        details = event.get("details") or {}
        occurrence_id = details.get("occurrence_id")

        if not occurrence_id:
            # Older pre-occurrence events are ignored.
            continue

        if date_text is not None and details.get("date") not in (None, date_text):
            continue

        entry = rounds.setdefault(occurrence_id, {"taken": 0, "undone": 0, "completed_at": None})

        if event_type == taken_type:
            entry["taken"] += 1
            stamp = details.get("completed_at") or event.get("recorded_at")
            if stamp and (entry["completed_at"] is None or str(stamp) > str(entry["completed_at"])):
                entry["completed_at"] = stamp
        else:
            entry["undone"] += 1

    return rounds


def _completed(rounds: dict[str, dict]) -> dict[str, str]:
    """{occurrence_id: completed_at} for occurrences done right now."""

    return {
        occurrence_id: entry["completed_at"]
        for occurrence_id, entry in rounds.items()
        if entry["taken"] > entry["undone"]
    }


def _round_key(occurrence_date: str, occurrence_number, rounds: dict[str, dict], occurrence_id: str) -> str:
    """The save key for this round: the plain key first, then '#r1', '#r2' after each undo."""

    undone = rounds.get(occurrence_id, {}).get("undone", 0)
    base = f"{occurrence_date}#{occurrence_number}"

    return f"{base}#r{undone}" if undone else base


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
    return _completed(_completion_rounds(get_events(patient_id), "task", date_text))


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
        date = get_current_date(state.get("timezone") or DEFAULT_TIMEZONE)

    # Nothing is due before the patient is discharged.
    if _is_before_discharge(state, date):
        return []

    completed = _completed_task_occurrences(
        patient_id,
        date,
    )

    occurrences = []

    for task in state.get("tasks", []):

        if _has_ended(task, state, date):
            continue

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
        _round_key(
            occurrence_date,
            occurrence_number,
            _completion_rounds(get_events(patient_id), "medication"),
            occurrence_id,
        ),
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
        _round_key(
            occurrence_date,
            occurrence_number,
            _completion_rounds(get_events(patient_id), "task"),
            occurrence_id,
        ),
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


def undo_completion(
    patient_id: str,
    occurrence_id: str,
    today: str,
) -> dict:
    """
    Change one of today's saved reports back to not done.

    Event History keeps everything: this appends an "undone" event
    and deletes nothing. Undoing twice is safe (same key).
    """

    # A medicine dose or a task: look in today's medicines first, then tasks.
    occurrence = _find_occurrence(get_medications(patient_id, today), occurrence_id)
    kind, read_today = "medication", get_medications

    if occurrence is None:
        occurrence = _find_occurrence(get_today_tasks(patient_id, today), occurrence_id)
        kind, read_today = "task", get_today_tasks

    if occurrence is None:
        raise ValueError("There is nothing matching scheduled for today.")

    if occurrence.get("status") != "completed":
        return {"undone": False, "was_completed": False, "item": occurrence}

    item_id, occurrence_date, occurrence_number = parse_occurrence_id(occurrence_id)
    rounds = _completion_rounds(get_events(patient_id), kind)
    undo_round = rounds.get(occurrence_id, {}).get("undone", 0)

    event_result = append_event(
        patient_id=patient_id,
        event_type=_EVENT_TYPES[kind][1],
        details={
            "occurrence_id": occurrence_id,
            "date": occurrence_date,
            "occurrence_number": occurrence_number,
            "name": occurrence.get("name") or occurrence.get("description"),
            "undone_at": get_current_datetime().isoformat(),
        },
        idempotency_key=build_idempotency_key(
            patient_id,
            item_id,
            f"{occurrence_date}#{occurrence_number}#undo#{undo_round}",
        ),
    )

    return {
        "undone": True,
        "was_completed": True,
        "item": _find_occurrence(read_today(patient_id, today), occurrence_id),
        "event": event_result,
    }
